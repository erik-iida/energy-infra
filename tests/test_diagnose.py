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
# the full mix of the day (every production type) for "what was happening next door": HU runs nuclear + solar, RO solar + gas + nuclear
ga_full = pd.concat([mk_gen("HU", DAY, "B14", lambda i: 2000), mk_gen("HU", DAY, "B16", lambda i: 1000 if 9 <= i <= 16 else 0),
                     mk_gen("HU", DAY, "B12", lambda i: 50), mk_gen("RO", DAY, "B16", lambda i: 3000 if 9 <= i <= 16 else 0),
                     mk_gen("RO", DAY, "B04", lambda i: 1500 if 18 <= i <= 21 else 500), mk_gen("RO", DAY, "B14", lambda i: 1400)])
frames = DG.day_frames(hp, ga, hl, hf, DAY, ga_full=ga_full)
Z = frames["RO"]
assert "m|nuclear" in Z and abs(Z["m|nuclear"].iloc[3] - 1400) < 1e-6 and abs(frames["HU"]["m|hydro"].iloc[3] - 50) < 1e-6
mx = DG.mix_stats(frames["HU"], [18, 19, 20, 21])
assert mx[0]["cls"] == "nuclear" and abs(mx[0]["share"] - 2000 / 2050 * 100) < 0.1, mx
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
assert nb["HU"]["mix"][0]["cls"] == "nuclear" and nb["HU"]["stats"]["wind_share"] is None  # HU has no wind rows
imp = next(x for x in d["drivers"] if x["key"] == "imports_in_peak")
assert "mostly from Hungary; in Hungary the power came mostly from nuclear" in imp["text"], imp["text"]
assert "imported from 18:00 to 22:00" in imp["text"] and "MW" not in imp["text"], imp["text"]   # block of hours, no hour list, no MW clause
assert imp["numbers"]["counterparty_mw"] == 800 and "mix_nuclear" in imp["numbers"]
s4s = dict(s4, streak=3)
assert "the 3rd day running" in DG.render_text(DG.diagnose(s4s, DAY, frames, scan, fired))
keys = [x["key"] for x in d["drivers"]]
assert keys[:1] == ["peak_residual"] and "gas_in_peak" in keys and "imports_in_peak" in keys and "cheap_solar" in keys, keys
assert "took in" not in " ".join(x["text"] for x in d["drivers"]) and "coincided with the evening peak in residual load" in d["drivers"][0]["text"]
assert "other" not in " ".join(m["label"] for r in d["neighbours"] for m in r["mix"]), "no 'other 30 %' in a mix"
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
# hour phrases: never a list of clock times
labs = [f"{h:02d}" for h in range(24)]
assert DG.hours_phrase(labs, [17, 18, 19, 21]) == "from 17:00 to 22:00"
assert DG.hours_phrase(labs, [0, 1, 2, 3]) == "from 00:00 to 04:00"
assert DG.hours_phrase(labs, [1, 2, 12, 13, 19]) == "overnight, around midday and in the evening"
# "almost no wind or solar", and no 'wind peak' when the cheap hours have no more wind than the day
assert DG.vre_phrase({"wind_share": 0.2, "solar_share": 0.4}, "in those hours")[0] == "there was almost no wind or solar in those hours"
assert DG.vre_phrase({"wind_share": 1.0, "solar_share": 12.0}, "that day")[0].startswith("solar covered 12 %")

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

# ---------------------------------------------------------------- the brief: stories, not a metrics dump (Erik, 6-7 Oct 2026)
from newsletter import build as B  # noqa: E402
d["years"] = {"prev": 2025, "cur": 2026, "n_prev": 12, "n_cur": 31, "days_prev": 365}
d2["years"] = None
ff = {"day": "2026-10-02", "diagnoses": [d, d2], "lead": {"zone": "GR", "metric": "neg_hours"}, "focus": ["RO", "GR"], "context": [],
      "table": [{"zone": "RO", "baseload": 90, "tb2": 100, "tb4": 90, "neg_hours": 0, "wind_share_load": 3, "solar_share_load": 4},
                {"zone": "GR", "baseload": 60, "tb2": 100, "tb4": 90, "neg_hours": 6, "wind_share_load": 27, "solar_share_load": 91}],
      "tomorrow": {"day": "2026-10-03", "zones": [
          {"zone": "RO", "baseload": 80, "tb2": 120, "tb4": 110, "neg_hours": 0, "max": 200, "max_at": "19:00", "min": 40, "min_at": "13:00"},
          {"zone": "BG", "baseload": 70, "tb2": 90, "tb4": 80, "neg_hours": 2, "max": 150, "max_at": "19:00", "min": -5, "min_at": "13:00"}]},
      "decoupling": [{"high": "RO", "low": "HU", "base_high": 90, "base_low": 70, "rel": 22, "hours_apart": 16, "hours": 24, "context": []}],
      "fundamentals": [], "notes": []}
md = B.draft_brief(ff)
print(md[:2500])
head = md.split("**Headline.** ")[1].split("\n")[0]
assert "Greece" in head and "2025" not in head and head.count("%") == 0 and "of its last" not in head, head          # one signal, no percentile jargon
paras = [p_ for p_ in md.split("\n\n") if p_.startswith("**") and p_.split("**")[1] in B.GROUPS.values()]
assert len(paras) == 2 and paras[0].startswith("**Wind and solar surplus.**"), "the headline's story comes first"
for p_ in paras:
    assert B.figures(p_) <= B.FIGURES_MAX + 1, (B.figures(p_), p_)                                          # sentence 1 may overshoot, never the rest
assert "(P" not in md and "bottleneck" not in md and "took in" not in md and ", 1" not in md.split("**Next 24 h.**")[0], md
assert "prices separated in 16 of 24 hours, which is typical when the border limit is reached" in md.replace("Prices separated", "prices separated")
assert "**Renewables leaders in the last 24h.**" in md and "Fundamentals (last 30 days)" not in md
assert "Bulgaria (2 h)" in md and "TB4" not in md.split("| Zone |")[0]
assert "Romania" in md.split("**Next 24 h.**")[1].split("\n")[0] or "Bulgaria" in md.split("**Next 24 h.**")[1].split("\n")[0]
# rank wording
assert B.rank_phrase(d) == "a level reached or exceeded on 12 days in 2025 and 31 days so far in 2026"
assert B.rank_phrase(dict(d, years=None, n_hist=1000)) == "among the highest of the last 33 months"
assert B.streak_phrase(5) == ", the 5th day in a row"
# percentile gate: only P0-P5 / P95-P100 reach the text; a spread loses to a non-spread signal of its zone; at most 3 spread stories
sg = [dict(sig("PL", "tb4", 90, pct=0.97), streak=1), dict(sig("PL", "res_peak", 7000, pct=0.96), streak=1),
      dict(sig("CZ", "tb4", 90, pct=0.92), streak=1), dict(sig("HU", "tb4", 90, pct=0.99), streak=1)]
ok = [s_ for s_ in sg if B.extreme(s_["pct"], s_["side"])]
assert [s_["zone"] for s_ in ok] == ["PL", "PL", "HU"] and [s_["metric"] for s_ in B.story_candidates(ok, ["PL", "HU"]) if s_["zone"] == "PL"] == ["res_peak"]
# what differed across a price gap comes from the frames only
dec = B.decoupling_context([{"high": "RO", "low": "HU", "base_high": 90, "base_low": 70, "rel": 22, "hours_apart": 16, "hours": 24}], frames)
for c in dec[0]["context"]:
    assert all(int(n_) in DG.numbers_in(c["numbers"]) for n_ in re.findall(r"\d+", c["text"])), c

print("diagnose tests passed")
