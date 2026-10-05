"""newsletter/diagnose.py on synthetic day data (no store, no network).   python -m tests.test_diagnose

Covers: event hours reproduce TB4 / TB2 / negative hours / residual peak / ramp; a 25-hour DST day (25 Oct 2026, 02 and 02');
a day with a missing price hour; a zone with no generation (late TSO data); a neighbour without an EUR price (UA-IPS) and
one outside the store; GB labelled Market Index; the audit rule (every number in the text is a value of the dict); no fuel
or spark figures; the driver table on a tight-evening day and a solar-glut day."""
import re

import numpy as np
import pandas as pd

from newsletter import diagnose as DG, metrics as M, signals as S

CET = M.CET


def hours(day):
    return DG._hours_of_day(pd.Timestamp(day))


def mk_price(zone, day, f, currency="EUR"):
    h = hours(day)
    return pd.DataFrame({"zone": zone, "h": h, "price": [f(i) for i in range(len(h))]}) if currency == "EUR" else pd.DataFrame(columns=["zone", "h", "price"])


def mk_gen(zone, day, psr, f):
    h = hours(day)
    ts = pd.DatetimeIndex(np.repeat(h, 4)) + pd.to_timedelta(np.tile([0, 15, 30, 45], len(h)), "min")
    return pd.DataFrame({"zone": zone, "ts": ts, "res_min": 15, "psr": psr, "dir": "gen", "mw": [f(i // 4) for i in range(len(ts))]})


def mk_load(zone, day, f):
    h = hours(day)
    return pd.DataFrame({"zone": zone, "h": h, "mw": [f(i) for i in range(len(h))]})


def mk_flow(a, b, day, f):
    h = hours(day)
    return pd.DataFrame({"from_zone": a, "to_zone": b, "h": h, "mw": [f(i) for i in range(len(h))]})


def sig(zone, metric, value, side="high", pct=0.95, label=None, unit="EUR/MWh"):
    lab = {r.metric: (r.label, r.unit) for r in S.RULES}.get(metric, (label or metric, unit))
    return {"zone": zone, "metric": metric, "label": lab[0], "unit": lab[1], "side": side, "value": value, "pct": pct,
            "n_hist": 90, "median": value * 0.6, "p10": value * 0.4, "p90": value * 0.9, "score": 1.0}


def audit(d, text):
    """Every number in the text must be a value of the dict (whole numbers, half up). Dates and clock times are skipped."""
    allowed = DG.numbers_in(d)
    body = re.sub(r"\b\d{1,2}′?:\d{2}\b", " ", text)               # 18:00, 02′:59
    body = re.sub(r"\b\d{1,2} [A-Z][a-z]{2} \d{4}\b", " ", body)   # 2 Oct 2026
    body = body.replace("P10", " ").replace("P90", " ").replace("P50", " ")
    body = re.sub(r"\(\d+\) ", " ", body)                         # (1) (2) driver numbering
    nums = [int(x) for x in re.findall(r"-?\d+", body)]
    bad = [n for n in nums if n not in allowed and abs(n) not in allowed]
    assert not bad, (bad, text)


# ---------------------------------------------------------------- a tight evening in RO with neighbours
DAY = pd.Timestamp("2026-10-02")
price = lambda i: 60 + (200 if 18 <= i <= 21 else 0) - (50 if 11 <= i <= 14 else 0) + i * 0.1
hp = pd.concat([mk_price("RO", DAY, price), mk_price("HU", DAY, lambda i: 90 + i * 0.1), mk_price("BG", DAY, lambda i: price(i) - 5)])
ga = pd.concat([mk_gen("RO", DAY, "B16", lambda i: 3000 if 9 <= i <= 16 else 0), mk_gen("RO", DAY, "B19", lambda i: 200),
                mk_gen("RO", DAY, "B04", lambda i: 1500 if 18 <= i <= 21 else 500), mk_gen("RO", DAY, "B14", lambda i: 1400),
                mk_gen("HU", DAY, "B16", lambda i: 1000 if 9 <= i <= 16 else 0)])
ga = M.slim_gen(ga)
hl = pd.concat([mk_load("RO", DAY, lambda i: 7000 + (1500 if 18 <= i <= 21 else 0)), mk_load("HU", DAY, lambda i: 5000)])
hf = pd.concat([mk_flow("HU", "RO", DAY, lambda i: 800 if 18 <= i <= 21 else 100), mk_flow("RO", "BG", DAY, lambda i: 300),
                mk_flow("UA-IPS", "RO", DAY, lambda i: 400), mk_flow("MD", "RO", DAY, lambda i: 50)])
frames = DG.day_frames(hp, ga, hl, hf, DAY)
Z = frames["RO"]
assert len(Z) == 24 and DG.hour_labels(Z.index)[0] == "00" and DG.hour_labels(Z.index)[23] == "23"
assert abs(Z["total"].iloc[19] - (3000 * 0 + 200 + 1500 + 1400)) < 1e-6, Z["total"].iloc[19]
assert abs(Z["net_import"].iloc[19] - (800 - 300 + 400 + 50)) < 1e-6
assert abs(Z["res"].iloc[12] - (7000 - 3000 - 200)) < 1e-6

# event hours = the metric's own hours
ev = DG.event_hours("tb4", Z)
v = sorted(Z["price"])
assert ev["hi"] == [18, 19, 20, 21] and ev["lo"] == [11, 12, 13, 14]
assert abs(ev["spread"] - (sum(v[-4:]) / 4 - sum(v[:4]) / 4)) < 1e-9
ev2 = DG.event_hours("tb2", Z)
assert len(ev2["hi"]) == 2 and abs(ev2["spread"] - (sum(v[-2:]) / 2 - sum(v[:2]) / 2)) < 1e-9
assert DG.event_hours("res_peak", Z)["hi"] == [21], DG.event_hours("res_peak", Z)   # tied peak hours: the last one, as fxEvents (stable ascending sort, last element)
assert DG.event_hours("res_min", Z)["lo"] == [9]
rp = DG.event_hours("res_ramp3", Z)
assert rp["hi"] == [15, 16, 17, 18] and abs(rp["rise"] - (Z["res"].iloc[18] - Z["res"].iloc[15])) < 1e-9

# scan rows: build a 90-day history so the percentiles exist
rows = []
for k in range(1, 91):
    d = DAY - pd.Timedelta(days=k)
    for m, val in (("baseload", 70), ("tb4", 60), ("wind_share_load", 0.03), ("gas_share", 0.08), ("load_mean", 7000), ("res_peak", 7000), ("net_import", 500)):
        rows.append(("RO", d, m, val + (k % 7) * 0.01 * val))
for m, val in (("baseload", 85), ("tb4", 250), ("wind_share_load", 0.028), ("gas_share", 0.12), ("load_mean", 7600), ("res_peak", 8300), ("net_import", 500)):
    rows.append(("RO", DAY, m, val))
metrics = pd.DataFrame(rows, columns=["zone", "day", "metric", "value"])
scan = S.scan(metrics, DAY, S.RULES + S.CONTEXT)
fired = S.evaluate(metrics, DAY)
assert any(f["metric"] == "tb4" for f in fired)
s4 = next(f for f in fired if f["metric"] == "tb4")
d = DG.diagnose(s4, DAY, frames, scan, fired)
t = DG.render_text(d)
print(t, "\n")
assert d["hours_hi"] == ["18", "19", "20", "21"] and d["hours_hi_text"] == "18:00–21:59 CET"
assert d["hi_stats"]["gas_share"] > d["day_stats"]["gas_share"] and d["hi_stats"]["net_import"] > d["day_stats"]["net_import"]
um = [u["metric"] for u in d["unusual"]]
assert "gas_share" in um and "load_mean" in um and "res_peak" in um and "tb4" not in um, um  # the flag itself is not repeated
assert um == [m for m in DG.UNUSUAL_ORDER if m in um], "panel order"
nb = {r["zone"]: r for r in d["neighbours"]}
assert nb["UA-IPS"]["price_na"] and "UAH" in nb["UA-IPS"]["price_na"] and nb["MD"]["price_na"] == "no price in the store"
assert nb["HU"]["price"] is not None and nb["HU"]["diff"] is not None and nb["HU"]["hours_split"] == 24
assert nb["BG"]["hours_split"] == 24 and nb["HU"]["net_import_event"] == 800
assert [r["zone"] for r in d["neighbours"]][0] == "UA-IPS", "ordered by mean |net flow|"
keys = [x["key"] for x in d["drivers"]]
assert keys[:1] == ["peak_residual"] and "gas_in_peak" in keys and "imports_in_peak" in keys and "cheap_solar" in keys, keys
assert "caused" not in t and "congest" not in t and "spark" not in t.lower() and "TTF" not in t
assert "Romania" in t and "Hungary" in t and "Ukraine" in t and "price n/a" in t
audit(d, t)

# ---------------------------------------------------------------- GR solar glut: negative hours, exports, neighbour negative too
GR = pd.Timestamp("2026-10-02")
hp2 = pd.concat([mk_price("GR", GR, lambda i: -5 if 10 <= i <= 15 else 120), mk_price("BG", GR, lambda i: -1 if 12 <= i <= 13 else 130)])
ga2 = M.slim_gen(pd.concat([mk_gen("GR", GR, "B16", lambda i: 5000 if 9 <= i <= 16 else 0), mk_gen("GR", GR, "B19", lambda i: 1500)]))
hl2 = mk_load("GR", GR, lambda i: 5500)
hf2 = mk_flow("GR", "BG", GR, lambda i: 900 if 10 <= i <= 15 else 100)
fr2 = DG.day_frames(hp2, ga2, hl2, hf2, GR)
sn = sig("GR", "neg_hours", 6, pct=1.0)
d2 = DG.diagnose(sn, GR, fr2, [], [sn])
t2 = DG.render_text(d2)
print(t2, "\n")
assert d2["hours_lo"] == ["10", "11", "12", "13", "14", "15"] and d2["lo_stats"]["net_import"] == -900
k2 = [x["key"] for x in d2["drivers"]]
assert k2[:2] == ["vre_in_neg", "exports_in_neg"] and "neighbours_negative" in k2, k2
assert "the highest of its last 90 days" in t2
audit(d2, t2)

# ---------------------------------------------------------------- DST day (25 Oct 2026: 25 hours), missing price hour, late generation
DST = pd.Timestamp("2026-10-25")
h25 = hours(DST)
assert len(h25) == 25
lab = DG.hour_labels(h25)
assert lab[2] == "02" and lab[3] == "02′" and lab[-1] == "23", lab
hp3 = mk_price("PL", DST, lambda i: 100 + (80 if i in (18, 19, 20, 21) else 0))
hp3 = hp3[hp3["h"] != h25[5]]                                   # one hour missing
fr3 = DG.day_frames(hp3, None, None, None, DST)
d3 = DG.diagnose(sig("PL", "tb4", 80), DST, fr3, [], [])
t3 = DG.render_text(d3)
print(t3, "\n")
assert d3["data"]["hours"] == 25 and d3["data"]["price_hours"] == 24 and "generation not published" in t3 and "day-ahead price 24 of 25 hours" in t3
assert d3["hi_stats"]["gas_share"] is None and d3["drivers"] == [] and d3["neighbours"] == []
audit(d3, t3)

# a zone with no data at all for the day
d4 = DG.diagnose(sig("SK", "tb4", 80), DST, fr3, [], [])
assert d4["day_stats"] is None and "no hourly data" in DG.render_text(d4)

# ---------------------------------------------------------------- GB: Market Index label, price already in EUR from metrics.hourly_prices
hp5 = pd.concat([mk_price("GB", DAY, lambda i: 90.0), mk_price("IE(SEM)", DAY, lambda i: 95.0)])
hf5 = mk_flow("GB", "IE(SEM)", DAY, lambda i: 400)
fr5 = DG.day_frames(hp5, None, None, hf5, DAY)
d5 = DG.diagnose(sig("IE(SEM)", "baseload", 95, pct=0.97), DAY, fr5, [], [])
t5 = DG.render_text(d5)
assert "Market Index" in t5 and d5["neighbours"][0]["price_label"] == "Market Index"
d6 = DG.diagnose(sig("GB", "baseload", 90, pct=0.97), DAY, fr5, [], [])
assert "Price = Market Index" in DG.render_text(d6)
audit(d5, t5)

# ---------------------------------------------------------------- the audit catches a number that is not in the dict
try:
    audit(d, t + " and 4711 €/MWh")
    raise AssertionError("audit must fail on a foreign number")
except AssertionError as e:
    assert "4711" in str(e)
print("diagnose tests passed")
