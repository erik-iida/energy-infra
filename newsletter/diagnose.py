"""Diagnose a fired signal: the Flags-panel drill-down as a function (spec 4). For one zone, day and signal it says which
hours the event sat in, what wind, solar, gas, load, residual load and imports did in those hours against the day, what
else was unusual (the CONTEXT rows beyond P90 / P10, same rule and order as the panel), what the neighbours did (price,
difference, net flow, hours the prices split) and which candidate drivers an explicit rule table found. `render_text`
turns the structured dict into a short factual block; every number in the text is a value from the dict (tested).

Pure functions on DataFrames: no store, file or network access in here, no knowledge of web/. The callers are
`build.build_facts` (facts.json, the newsletter draft) and later the Flags export ("copy context as text").

Wording rules (STYLE.md): co-occurrence, not causation ("coincided with", never "caused"); no fuel prices or spark
spreads; country names in full; whole numbers; "% of consumption". No congestion claims until NTC is in the store.

Day frame per zone (`day_frames`): one row per UTC hour of the CET day (23 / 24 / 25 with DST), columns price (EUR/MWh),
load, solar, wind_onshore, wind_offshore, gas, total (MW, hourly means), net_import (MW, + = into the zone, over the
borders with data) and one `x|<partner>` column per border. Residual load = load - wind - solar over the hours that have
load and at least one of the three (the panel's definition).
"""
from __future__ import annotations

import math

import pandas as pd

from . import metrics as M
from . import signals as S
from .zones import NON_EUR, PRICE_LABEL, zn

# order of the "what else was unusual" rows: the panel's FXUNU (js/features/flags/drilldown.js); keep the two in step
UNUSUAL_ORDER = ["baseload", "price_max", "price_min", "neg_hours", "tb4", "gen_wind_onshore", "gen_wind_offshore", "gen_solar",
                 "wind_share_load", "solar_share_load", "vre_share", "gas_share", "load_mean", "res_mean", "res_peak", "res_min",
                 "import_share", "net_import"]
PRIVATE = ("spark_",)          # never in a diagnosis (fuel-price derived)
VRE = ["solar", "wind_onshore", "wind_offshore"]
PSR = {"B16": "solar", "B18": "wind_offshore", "B19": "wind_onshore", M.GAS: "gas", M.TOTAL: "total"}
# generation mix classes for "what was happening next door" (site technology groups); columns m|<class> in the day frame
MIX = {"B14": "nuclear", "B02": "coal", "B05": "coal", "B03": "gas", "B04": "gas", "B06": "oil", "B10": "pumped", "B11": "hydro",
       "B12": "hydro", "B01": "biomass", "B17": "biomass", "B16": "solar", "B19": "wind_onshore", "B18": "wind_offshore",
       "B07": "other", "B08": "other", "B09": "other", "B13": "other", "B15": "other", "B20": "other", "B25": "other"}
MIX_LABEL = {"nuclear": "nuclear", "coal": "coal and lignite", "gas": "gas", "oil": "oil", "pumped": "pumped storage", "hydro": "hydro",
             "biomass": "biomass and waste", "solar": "solar", "wind_onshore": "onshore wind", "wind_offshore": "offshore wind", "other": "other"}
SPLIT_EUR = 1.0                # hours with a larger price difference count as "split" (build.decoupling uses the same)
# thresholds of the driver rule table (first version, Cowork's proposal; Erik's market knowledge decides, see DEVNOTES)
TH = {"share_hi": 30.0,        # % of consumption that makes wind or solar "the" story of an hour block
      "share_x": 1.5,          # ... or this multiple of the day's share
      "gas_pts": 10.0,         # gas share in the block at least this many points above the day's
      "flow_pts": 5.0,         # net import in the block at least this % of load away from the day mean
      "price_gap": 10.0,       # a neighbour counts as cheaper / pricier beyond this (EUR/MWh)
      "load_x": 0.9}           # load in negative hours below this share of the day mean = "low load"


# ---------------------------------------------------------------- day frames
def _hours_of_day(day: pd.Timestamp) -> pd.DatetimeIndex:
    a = day.tz_localize(M.CET).tz_convert("UTC")
    b = (day + pd.Timedelta(days=1)).tz_localize(M.CET).tz_convert("UTC")
    return pd.date_range(a, b, freq="h", inclusive="left")


def hour_labels(idx: pd.DatetimeIndex) -> list[str]:
    """CET hour labels; the repeated hour of the autumn DST day is marked with a prime, as on the page (02, 02′)."""
    out, seen = [], set()
    for h in idx:
        s = h.tz_convert(M.CET).strftime("%H")
        out.append(s + "′" if s in seen else s)
        seen.add(s)
    return out


def day_frames(hp: pd.DataFrame, ga: pd.DataFrame, hl: pd.DataFrame, hf: pd.DataFrame, day: pd.Timestamp,
               ga_full: pd.DataFrame | None = None) -> dict:
    """{zone: DataFrame} for the CET `day` (see module doc). hp = metrics.hourly_prices (EUR, GB converted), ga = raw or
    slimmed gen_actual rows, hl = metrics.hourly_load, hf = metrics.hourly_flows. Zones = union of the four sources.
    `ga_full` = the day's unslimmed gen_actual rows (every production type): adds the generation mix columns m|<class>, so a
    neighbour's story ("nuclear and hydro supplied ...") can be told. Without it the mix is simply absent."""
    hours = _hours_of_day(day)
    a, b = hours[0], hours[-1] + pd.Timedelta(hours=1)
    cols = {}
    if hp is not None and not hp.empty:
        p = hp[(hp["h"] >= a) & (hp["h"] < b)]
        for z, g in p.groupby("zone"):
            cols.setdefault(z, {})["price"] = g.set_index("h")["price"]
    if ga is not None and not ga.empty:
        g = ga[(ga["dir"] == "gen") & ga["psr"].isin(PSR) & (ga["ts"] >= a) & (ga["ts"] < b)]
        g = g.assign(h=g["ts"].dt.floor("h"), mw=g["mw"].clip(lower=0), tech=g["psr"].map(PSR))
        for (z, t), x in g.groupby(["zone", "tech"]):
            cols.setdefault(z, {})[t] = x.groupby("h")["mw"].mean()
    if ga_full is not None and not ga_full.empty:
        g = ga_full[(ga_full["dir"] == "gen") & ga_full["psr"].isin(MIX) & (ga_full["ts"] >= a) & (ga_full["ts"] < b)]
        g = g.assign(h=g["ts"].dt.floor("h"), mw=g["mw"].clip(lower=0), cls=g["psr"].map(MIX))
        hm = g.groupby(["zone", "psr", "h"])["mw"].mean().reset_index().assign(cls=lambda x: x["psr"].map(MIX))
        for (z, c), x in hm.groupby(["zone", "cls"]):
            cols.setdefault(z, {})["m|" + c] = x.groupby("h")["mw"].sum()
    if hl is not None and not hl.empty:
        l = hl[(hl["h"] >= a) & (hl["h"] < b)]
        for z, g in l.groupby("zone"):
            cols.setdefault(z, {})["load"] = g.set_index("h")["mw"]
    if hf is not None and not hf.empty:
        f = hf[(hf["h"] >= a) & (hf["h"] < b)]
        inn = f.rename(columns={"to_zone": "zone", "from_zone": "partner"})
        out = f.rename(columns={"from_zone": "zone", "to_zone": "partner"}).assign(mw=-f["mw"])
        for (z, pz), g in pd.concat([inn, out]).groupby(["zone", "partner"]):
            cols.setdefault(z, {})["x|" + pz] = g.groupby("h")["mw"].sum()
    frames = {}
    for z, c in cols.items():
        d = pd.DataFrame(c).reindex(hours)
        for k in ["price", "load", "gas", "total"] + VRE:
            if k not in d:
                d[k] = float("nan")
        xb = [k for k in d.columns if k.startswith("x|")]
        d["net_import"] = d[xb].sum(axis=1, min_count=1) if xb else float("nan")
        vre = d[VRE].sum(axis=1, min_count=1)
        d["res"] = (d["load"] - vre).where(d["load"].notna() & vre.notna())
        frames[z] = d
    return frames


# ---------------------------------------------------------------- event hours (as the panel shades them)
def event_hours(metric: str, Z: pd.DataFrame) -> dict:
    """Indices (positions in the day frame) of the hours the panel shades for this signal type, plus the numbers the panel's
    caption quotes. Mirrors fxEvents in js/features/flags/drilldown.js: ties are broken the same way (stable sort)."""
    P = list(Z["price"]) if Z is not None else []
    R = list(Z["res"]) if Z is not None else []
    ok = lambda v: v is not None and not (isinstance(v, float) and math.isnan(v))
    if metric in ("tb2", "tb4"):
        k = 4 if metric == "tb4" else 2
        s = sorted([(v, i) for i, v in enumerate(P) if ok(v)])
        if len(s) < 2 * k:
            return {}
        lo, hi = s[:k], s[-k:]
        mh, ml = sum(v for v, _ in hi) / k, sum(v for v, _ in lo) / k
        return {"hi": sorted(i for _, i in hi), "lo": sorted(i for _, i in lo), "hi_label": f"{k} priciest hours",
                "lo_label": f"{k} cheapest hours", "k": k, "mean_hi": mh, "mean_lo": ml, "spread": mh - ml}
    if metric == "neg_hours":
        return {"lo": [i for i, v in enumerate(P) if ok(v) and v < 0], "lo_label": "negative hours"}
    if metric in ("res_peak", "res_min"):
        s = sorted([(v, i) for i, v in enumerate(R) if ok(v)], key=lambda q: q[0])
        if not s:
            return {}
        v, i = s[-1] if metric == "res_peak" else s[0]
        return {"hi": [i], "hi_label": "hour of the highest residual load", "res": v} if metric == "res_peak" else {"lo": [i], "lo_label": "hour of the lowest residual load", "res": v}
    if metric == "res_ramp3":
        best = None
        for i in range(3, len(R)):
            if ok(R[i]) and ok(R[i - 3]) and (best is None or R[i] - R[i - 3] > best[0]):
                best = (R[i] - R[i - 3], i)
        return {"hi": [best[1] - 3, best[1] - 2, best[1] - 1, best[1]], "hi_label": "steepest 3-hour rise", "rise": best[0]} if best else {}
    return {}


# ---------------------------------------------------------------- block statistics
def _r(v, nd=1):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def _mean(s: pd.Series):
    s = s.dropna()
    return float(s.mean()) if len(s) else None


def block_stats(Z: pd.DataFrame, idx: list[int] | None = None) -> dict:
    """Numbers for a block of hours (idx = positions; None = the whole day): mean price, load, residual load and net
    import, wind / solar share of consumption (energy over the hours with both), gas share of generation, hours covered."""
    d = Z if idx is None else Z.iloc[idx]
    wind = d[["wind_onshore", "wind_offshore"]].sum(axis=1, min_count=1)
    share = lambda g: _r(g.sum() / d.loc[g.notna() & d["load"].notna(), "load"].sum() * 100) if (g.notna() & d["load"].notna()).any() and d.loc[g.notna() & d["load"].notna(), "load"].sum() > 0 else None
    gs = None
    gt = d.loc[d["gas"].notna() & d["total"].notna()]
    if len(gt) and gt["total"].sum() > 0:
        gs = _r(gt["gas"].sum() / gt["total"].sum() * 100)
    return {"hours": int(len(d)), "price": _r(_mean(d["price"])), "load": _r(_mean(d["load"]), 0), "res": _r(_mean(d["res"]), 0),
            "net_import": _r(_mean(d["net_import"]), 0), "wind_share": share(wind.where(d["load"].notna())),
            "solar_share": share(d["solar"].where(d["load"].notna())), "gas_share": gs,
            "wind_mw": _r(_mean(wind), 0), "solar_mw": _r(_mean(d["solar"]), 0),
            "price_hours": int(d["price"].notna().sum()), "gen_hours": int((d[VRE + ["gas", "total"]].notna().any(axis=1)).sum()),
            "load_hours": int(d["load"].notna().sum()), "flow_hours": int(d["net_import"].notna().sum())}


def mix_stats(Z: pd.DataFrame, idx: list[int] | None = None, top: int = 3) -> list[dict]:
    """Generation mix of a block of hours (energy shares of all m|<class> columns), largest first: [{cls, label, share, mw}]."""
    cols = [c for c in Z.columns if c.startswith("m|")]
    if not cols:
        return []
    d = Z if idx is None else Z.iloc[idx]
    e = d[cols].sum(min_count=1)
    tot = e.sum()
    if not tot or pd.isna(tot) or tot <= 0:
        return []
    out = [{"cls": c[2:], "label": MIX_LABEL.get(c[2:], c[2:]), "share": _r(e[c] / tot * 100), "mw": _r(d[c].mean(), 0)} for c in cols if pd.notna(e[c]) and e[c] > 0]
    return sorted(out, key=lambda r: -r["share"])[:top]


# ---------------------------------------------------------------- unusual rows and neighbours
def unusual_rows(scan_rows: list[dict], zone: str, skip_metric: str | None = None) -> list[dict]:
    """CONTEXT / RULES rows of the zone at or beyond P90 / P10 and beyond the P90 / P10 value itself (the panel's rule:
    a tie with a history of zeros is not unusual), in the panel's order."""
    by = {r["metric"]: r for r in scan_rows if r["zone"] == zone}
    out = []
    for m in UNUSUAL_ORDER:
        r = by.get(m)
        if not r or m == skip_metric or m.startswith(PRIVATE) or r.get("pct") is None:
            continue
        p, v = r["pct"], r["value"]
        hi = p >= 0.9 and (r.get("p90") is None or v > r["p90"])
        lo = p <= 0.1 and (r.get("p10") is None or v < r["p10"])
        if hi or lo:
            out.append({"metric": m, "label": r["label"], "unit": r["unit"], "value": v, "pct100": round(p * 100),
                        "side": "high" if hi else "low", "median": r.get("median"), "p10": r.get("p10"), "p90": r.get("p90")})
    return out


# the neighbour's own unusual rows worth a clause: what its plants and demand did (not its prices or spreads)
NB_UNUSUAL = ("gen_wind_onshore", "gen_wind_offshore", "gen_solar", "wind_share_load", "solar_share_load", "vre_share", "gas_share",
              "load_mean", "res_peak", "res_min", "neg_hours")


def neighbours(zone: str, frames: dict, idx: list[int] | None = None, scan_rows: list[dict] | None = None) -> list[dict]:
    """The zone's borders with flow data on the day, ordered by mean |net flow|: net flow (+ = into the zone), the
    neighbour's mean price and the difference (zone minus neighbour), hours with the two prices more than SPLIT_EUR apart,
    and (for `idx`, the event hours) the neighbour's mean price and the net flow in those hours. What was happening next
    door: the neighbour's generation mix (`mix`, event hours or day), its wind / solar share of consumption then
    (`stats`), and its own unusual rows (`unusual`, from `scan_rows`, generation and demand metrics only)."""
    Z = frames.get(zone)
    if Z is None:
        return []
    out = []
    for c in [k for k in Z.columns if k.startswith("x|")]:
        n = c[2:]
        flow = Z[c]
        if flow.notna().sum() == 0:
            continue
        N = frames.get(n)
        r = {"zone": n, "name": zn(n), "net_import": _r(_mean(flow), 0), "price": None, "diff": None, "hours_split": None,
             "hours": None, "price_label": PRICE_LABEL.get(n), "price_na": None, "same_all_day": False, "fired": []}
        if idx is not None:
            r["net_import_event"] = _r(_mean(flow.iloc[idx]), 0)
        r["mix"] = mix_stats(N, idx) if N is not None else []
        r["stats"] = block_stats(N, idx) if N is not None else None
        r["unusual"] = [u for u in unusual_rows(scan_rows or [], n) if u["metric"] in NB_UNUSUAL]
        if n in NON_EUR:
            r["price_na"] = f"published in {NON_EUR[n]}, not converted"
        elif N is None or N["price"].notna().sum() == 0:
            r["price_na"] = "no price in the store"
        else:
            j = pd.concat([Z["price"].rename("a"), N["price"].rename("b")], axis=1).dropna()
            r["price"] = _r(_mean(N["price"]))
            if len(j):
                r["diff"] = _r(float((j["a"] - j["b"]).mean()))
                r["hours_split"] = int(((j["a"] - j["b"]).abs() > SPLIT_EUR).sum())
                r["hours"] = int(len(j))
                r["same_all_day"] = r["hours_split"] == 0
            if idx is not None:
                r["price_event"] = _r(_mean(N["price"].iloc[idx]))
                r["neg_hours_shared"] = int((N["price"].iloc[idx] < 0).sum())
        out.append(r)
    return sorted(out, key=lambda r: -abs(r["net_import"] or 0))


# ---------------------------------------------------------------- the diagnosis
def _hours_text(labels: list[str], idx: list[int]) -> str:
    if not idx:
        return ""
    idx = sorted(idx)
    if idx == list(range(idx[0], idx[-1] + 1)) and len(idx) > 1:
        return f"{labels[idx[0]]}:00–{labels[idx[-1]]}:59 CET"
    return ", ".join(f"{labels[i]}:00" for i in idx) + " CET"


def diagnose(sig: dict, day: pd.Timestamp, frames: dict, scan_rows: list[dict], fired: list[dict] | None = None) -> dict:
    """Structured diagnosis of one fired signal (a row of signals.evaluate). `frames` = day_frames(...) for `day`,
    `scan_rows` = signals.scan(metrics, day, RULES + CONTEXT), `fired` = every fired signal of the day (for 'neighbours
    also fired'). Missing data is stated in `data`, never filled."""
    zone, metric = sig["zone"], sig["metric"]
    Z = frames.get(zone)
    labels = hour_labels(Z.index) if Z is not None else []
    ev = event_hours(metric, Z) if Z is not None else {}
    hi, lo = ev.get("hi", []), ev.get("lo", [])
    d = {"zone": zone, "name": zn(zone), "day": day.strftime("%Y-%m-%d"), "metric": metric, "label": sig["label"],
         "unit": "€/MWh" if sig["unit"] == "EUR/MWh" else sig["unit"], "side": sig["side"], "value": sig["value"],
         "pct100": round(sig["pct"] * 100), "n_hist": sig["n_hist"], "median": sig.get("median"), "p10": sig.get("p10"), "p90": sig.get("p90"),
         "price_label": PRICE_LABEL.get(zone), "streak": int(sig.get("streak") or 1),
         "events": {k: v for k, v in ev.items()}, "hours_hi": [labels[i] for i in hi], "hours_lo": [labels[i] for i in lo],
         "hours_hi_text": _hours_text(labels, hi), "hours_lo_text": _hours_text(labels, lo),
         "day_stats": block_stats(Z) if Z is not None else None,
         "hi_stats": block_stats(Z, hi) if Z is not None and hi else None,
         "lo_stats": block_stats(Z, lo) if Z is not None and lo else None,
         "unusual": unusual_rows(scan_rows, zone, metric),
         "neighbours": neighbours(zone, frames, (hi or lo) or None, scan_rows),
         "data": None, "drivers": []}
    for k in ("mean_hi", "mean_lo", "spread", "res", "rise"):
        if k in d["events"]:
            d["events"][k] = _r(d["events"][k])
    if Z is None:
        d["data"] = {"hours": len(_hours_of_day(day)), "notes": ["no hourly data for this zone and day in the store"]}
    else:
        st = d["day_stats"]
        notes = []
        n = st["hours"]
        if st["gen_hours"] < n:
            notes.append(f"generation {st['gen_hours']} of {n} hours published" if st["gen_hours"] else "generation not published yet for this day")
        if st["load_hours"] < n:
            notes.append(f"load {st['load_hours']} of {n} hours published" if st["load_hours"] else "actual load not published yet")
        if st["price_hours"] < n:
            notes.append(f"day-ahead price {st['price_hours']} of {n} hours")
        if st["flow_hours"] == 0:
            notes.append("no cross-border flows in the store for this day")
        d["data"] = {"hours": n, "gen_hours": st["gen_hours"], "load_hours": st["load_hours"], "price_hours": st["price_hours"],
                     "flow_hours": st["flow_hours"], "borders": len(d["neighbours"]), "notes": notes}
    if fired:
        nb = {r["zone"] for r in d["neighbours"]}
        same = [s["zone"] for s in fired if s["zone"] in nb and s["metric"] == metric and s["side"] == sig["side"]]
        for r in d["neighbours"]:
            r["fired"] = [s["metric"] for s in fired if s["zone"] == r["zone"] and not s["metric"].startswith(PRIVATE)]
        d["same_signal_neighbours"] = same
    d["drivers"] = drivers(d, Z)
    return d


# ---------------------------------------------------------------- driver rule table
def _pct_text(r: dict) -> str:
    return (f"higher than on {r['pct100']} %" if r["side"] == "high" else f"lower than on {100 - r['pct100']} %") + " of the last days"


def _names(zones: list[str], limit: int = 4) -> str:
    """'Hungary, Bulgaria and 2 others', capitalised for the start of a sentence ('the Netherlands' -> 'The Netherlands')."""
    names = [zn(z) for z in zones]
    txt = ", ".join(names[:limit]) + (f" and {len(names) - limit} others" if len(names) > limit else "")
    return txt[0].upper() + txt[1:]


# plain labels for a neighbour's unusual rows inside a sentence
NB_LABEL = {"gen_wind_onshore": "onshore wind output", "gen_wind_offshore": "offshore wind output", "gen_solar": "solar output",
            "wind_share_load": "wind share of consumption", "solar_share_load": "solar share of consumption", "vre_share": "wind and solar share of consumption",
            "gas_share": "gas share of generation", "load_mean": "demand", "res_peak": "peak residual load", "res_min": "lowest residual load",
            "neg_hours": "count of negative-price hours"}


def _there(r: dict) -> tuple[str, dict]:
    """What was happening in neighbour `r` in the event hours: its generation mix (top three classes) and its most unusual
    generation / demand metric of the day (shares below 10 % are too small to be the story). '' when the store has nothing."""
    nums = {}
    mix = r.get("mix") or []
    if not mix:
        return f"no generation data for {r['name']} in the store that day", nums
    txt = f"in {r['name']} that was " + ", ".join(f"{m['label']} {_i(m['share'])} %" for m in mix[:3]) + " of generation"
    nums.update({f"mix_{m['cls']}": m["share"] for m in mix[:3]})
    un = [u for u in (r.get("unusual") or []) if not (u["unit"] == "%" and abs(u["value"]) < 10)]
    un = sorted(un, key=lambda u: -abs(u["pct100"] - 50))
    if un:
        u = un[0]
        txt += f"; its {NB_LABEL.get(u['metric'], u['label'])} ({_i(u['value'])}{' %' if u['unit'] == '%' else ' ' + u['unit'].replace('EUR/MWh', '€/MWh')}) was {_pct_text(u).replace('the last days', 'its last days')}"
        nums.update(nb_unusual_value=u["value"], nb_unusual_pct100=u["pct100"])
    return txt, nums


def _counterparty(d: dict, into: bool, event: bool = True):
    """The neighbour that carried most of the flow (into the zone if `into`, else out of it) in the event hours (or over the
    day), with the clause on what was happening there: (neighbour row, 'mostly from X (N MW); in X that was ...', numbers)."""
    NB = d["neighbours"]
    key = "net_import_event" if event and any(r.get("net_import_event") is not None for r in NB) else "net_import"
    cands = [r for r in NB if r.get(key) is not None and (r[key] > 0 if into else r[key] < 0)]
    if not cands:
        return None, "", {}
    t = max(cands, key=lambda r: abs(r[key]))
    there, nums = _there(t)
    nums["counterparty_mw"] = abs(t[key])
    return t, f"mostly {'from' if into else 'to'} {t['name']} ({_i(abs(t[key]))} MW); {there}", nums


def _streak_text(n: int) -> str:
    if not n or n <= 1:
        return ""
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f", the {n}{suf} day running"


def _flow_phrase(v) -> str:
    return f"took {_i(v)} MW" if v > 0 else f"sent {_i(-v)} MW" if v < 0 else "was balanced"


def _flow_shift(block, day, load) -> bool:
    """The block's net flow is far enough from the day mean to be worth a sentence: TH['flow_pts'] % of load, or
    without load data a change of at least half the larger of the two and 100 MW."""
    day = day or 0.0
    if load:
        return abs(block - day) >= TH["flow_pts"] / 100 * load
    return abs(block - day) >= 0.5 * max(abs(block), abs(day)) and abs(block) >= 100


def drivers(d: dict, Z: pd.DataFrame | None) -> list[dict]:
    """Ordered candidate drivers for the signal, each with the numbers that support it. Every check is a condition on
    the numbers already in `d` (block stats, unusual rows, neighbours); the phrases state co-occurrence only.
    FIRST VERSION: the checks, thresholds (TH) and phrases are Cowork's proposal from spec 4; Erik's review on real days
    decides what stays (DEVNOTES "Spec 4 step 1")."""
    out = []
    m, side = d["metric"], d["side"]
    D, H, L = d["day_stats"], d["hi_stats"], d["lo_stats"]
    U = {u["metric"]: u for u in d["unusual"]}
    NB = d["neighbours"]
    add = lambda key, text, **num: out.append({"key": key, "text": text, "numbers": {k: v for k, v in num.items() if v is not None}})
    name = d["name"]
    if D is None:
        return out
    fam = ("spread" if m in ("tb2", "tb4") and side == "high" else "neg" if m == "neg_hours" else "res_peak" if m == "res_peak"
           else "res_min" if m == "res_min" else "ramp" if m == "res_ramp3" else "imp" if m == "import_share" else "base" if m == "baseload"
           else "capture" if m.startswith("cr_") else None)
    ev = d["events"]
    hi_t, lo_t = d["hours_hi_text"], d["hours_lo_text"]

    def wind_solar(S, when):
        if S and S["wind_share"] is not None and S["solar_share"] is not None:
            return f"wind covered {_i(S['wind_share'])} % and solar {_i(S['solar_share'])} % of consumption {when}", {"wind_share": S["wind_share"], "solar_share": S["solar_share"]}
        return None, {}

    if fam == "spread" and H and L:
        # 1. the priciest hours took in the residual-load peak
        if Z is not None and Z["res"].notna().any():
            pk = int(Z["res"].values.argmax()) if Z["res"].notna().all() else int(Z["res"].fillna(-1e18).values.argmax())
            if pk in ev.get("hi", []):
                ws, nums = wind_solar(H, "in those hours")
                lab = hour_labels(Z.index)[pk]
                add("peak_residual", f"The {ev['k']} priciest hours ({hi_t}) took in the residual-load peak of {_i(Z['res'].iloc[pk])} MW at {lab}:00"
                    + (f"; {ws}" if ws else "") + ".", res_peak=_r(Z["res"].iloc[pk], 0), **nums)
        # 2. the cheapest hours fell in the solar / wind peak
        for k, lbl in (("solar_share", "solar"), ("wind_share", "wind")):
            if L[k] is not None and D[k] is not None and (L[k] >= TH["share_hi"] or (D[k] > 0 and L[k] >= TH["share_x"] * D[k])) and L[k] > D[k]:
                add(f"cheap_{lbl}", f"The {ev['k']} cheapest hours ({lo_t}) fell in the {lbl} peak: {lbl} covered {_i(L[k])} % of consumption against "
                    f"{_i(D[k])} % over the day, and the price averaged {_i(L['price'])} €/MWh.", **{k: L[k], k + "_day": D[k], "price_lo": L["price"]})
        # 3. a wind-poor day
        if "wind_share_load" in U and U["wind_share_load"]["side"] == "low":
            u = U["wind_share_load"]
            add("low_wind_day", f"Wind covered only {_i(u['value'])} % of consumption over the day, {_pct_text(u)}.", wind_share_day=u["value"], pct100=u["pct100"])
        # 4. gas in the peak
        if H["gas_share"] is not None and D["gas_share"] is not None and H["gas_share"] >= D["gas_share"] + TH["gas_pts"]:
            add("gas_in_peak", f"Gas supplied {_i(H['gas_share'])} % of generation in the priciest hours against {_i(D['gas_share'])} % over the day.",
                gas_share_hi=H["gas_share"], gas_share_day=D["gas_share"])
        # 5. imports in the peak / exports in the trough
        dn = D["net_import"] or 0
        if H["net_import"] is not None and H["net_import"] > 0 and H["net_import"] > dn and _flow_shift(H["net_import"], dn, D["load"]):
            _, cp, cn = _counterparty(d, into=True)
            add("imports_in_peak", f"In the priciest hours {name} took {_i(H['net_import'])} MW from its neighbours (over the day it {_flow_phrase(dn)})"
                + (f", {cp}" if cp else "") + ".", net_import_hi=H["net_import"], net_import_day=abs(dn), **cn)
        if L["net_import"] is not None and L["net_import"] < 0 and L["net_import"] < dn and _flow_shift(L["net_import"], dn, D["load"]):
            _, cp, cn = _counterparty(d, into=False)
            add("exports_in_trough", f"In the cheapest hours {name} sent {_i(-L['net_import'])} MW to its neighbours (over the day it {_flow_phrase(dn)})"
                + (f", {cp}" if cp else "") + ".", net_export_lo=_r(-L["net_import"], 0), net_import_day=abs(dn), **cn)
    elif fam == "neg" and L:
        nn = len(ev.get("lo", []))
        ws, nums = wind_solar(L, "in those hours")
        if ws:
            add("vre_in_neg", f"In the {nn} negative hours ({lo_t}) {ws}.".replace(" in those hours.", "."), n=nn, **nums)
        if L["net_import"] is not None and L["net_import"] < 0:
            _, cp, cn = _counterparty(d, into=False)
            add("exports_in_neg", f"{name} sent {_i(-L['net_import'])} MW to its neighbours on average in those hours" + (f", {cp}" if cp else "") + ".",
                net_export=_r(-L["net_import"], 0), **cn)
        elif L["net_import"] is not None and L["net_import"] > 0:
            _, cp, cn = _counterparty(d, into=True)
            add("imports_in_neg", f"{name} still took {_i(L['net_import'])} MW from its neighbours in those hours, so the surplus was regional, not only local"
                + (f"; {cp}" if cp else "") + ".", net_import=L["net_import"], **cn)
        if L["load"] and D["load"] and L["load"] < TH["load_x"] * D["load"]:
            add("low_load", f"Load in those hours was {_i(L['load'])} MW against a day mean of {_i(D['load'])} MW.", load_neg=L["load"], load_day=D["load"])
        shared = [r for r in NB if r.get("neg_hours_shared")]
        if shared:
            add("neighbours_negative", _names([r["zone"] for r in shared]) + (" was" if len(shared) == 1 else " were") + " also below zero in some of those hours.")
        if "res_min" in U:
            add("res_min", f"Residual load bottomed at {_i(U['res_min']['value'])} MW, {_pct_text(U['res_min'])}.", res_min=U["res_min"]["value"], pct100=U["res_min"]["pct100"])
    elif fam in ("res_peak", "res_min") and (H or L):
        P = H or L
        lab = (hi_t or lo_t).replace(":00 CET", "")
        ws, nums = wind_solar(P, "in that hour")
        add("hour", f"Residual load {'peaked' if fam == 'res_peak' else 'bottomed out'} at {_i(ev['res'])} MW at {lab}:00 CET with load at {_i(P['load'])} MW"
            + (f"; {ws}" if ws else "") + ".", res=ev["res"], load=P["load"], **nums)
        if fam == "res_peak" and "load_mean" in U and U["load_mean"]["side"] == "high":
            add("high_load", f"Load over the day averaged {_i(U['load_mean']['value'])} MW, {_pct_text(U['load_mean'])}.", load_mean=U["load_mean"]["value"], pct100=U["load_mean"]["pct100"])
        if fam == "res_peak" and "wind_share_load" in U and U["wind_share_load"]["side"] == "low":
            u = U["wind_share_load"]
            add("low_wind_day", f"Wind covered only {_i(u['value'])} % of consumption over the day, {_pct_text(u)}.", wind_share_day=u["value"], pct100=u["pct100"])
        if fam == "res_min" and "vre_share" in U and U["vre_share"]["side"] == "high":
            u = U["vre_share"]
            add("high_vre_day", f"Wind and solar together covered {_i(u['value'])} % of consumption over the day, {_pct_text(u)}.", vre_share_day=u["value"], pct100=u["pct100"])
        if P["price"] is not None and D["price"] is not None:
            add("price_then", f"The day-ahead price in that hour was {_i(P['price'])} €/MWh against a day mean of {_i(D['price'])}.", price_hour=P["price"], price_day=D["price"])
        if P["net_import"] is not None and P["net_import"] > 0:
            _, cp, cn = _counterparty(d, into=True)
            add("imports_then", f"{name} took {_i(P['net_import'])} MW from its neighbours in that hour" + (f", {cp}" if cp else "") + ".", net_import=P["net_import"], **cn)
        elif P["net_import"] is not None and P["net_import"] < 0:
            _, cp, cn = _counterparty(d, into=False)
            add("exports_then", f"{name} sent {_i(-P['net_import'])} MW to its neighbours in that hour" + (f", {cp}" if cp else "") + ".", net_export=_r(-P["net_import"], 0), **cn)
    elif fam == "ramp" and H and Z is not None:
        i0, i1 = ev["hi"][0], ev["hi"][-1]
        row0, row1 = Z.iloc[i0], Z.iloc[i1]
        wind0 = row0[["wind_onshore", "wind_offshore"]].sum(min_count=1)
        wind1 = row1[["wind_onshore", "wind_offshore"]].sum(min_count=1)
        dl, ds, dw = _r(row1["load"] - row0["load"], 0), _r(row0["solar"] - row1["solar"], 0), _r(wind0 - wind1, 0)
        parts, small = [], 0.05 * abs(ev["rise"])
        if dl is not None and abs(dl) >= small:
            parts.append(f"load {'rose' if dl >= 0 else 'fell'} {_i(abs(dl))} MW")
        if ds is not None and abs(ds) >= small:
            parts.append(f"solar {'fell' if ds >= 0 else 'rose'} {_i(abs(ds))} MW")
        if dw is not None and abs(dw) >= small:
            parts.append(f"wind {'fell' if dw >= 0 else 'rose'} {_i(abs(dw))} MW")
        lab = hour_labels(Z.index)
        add("ramp_parts", f"Between {lab[i0]}:00 and {lab[i1]}:00 CET residual load rose {_i(ev['rise'])} MW: " + ", ".join(parts) + ".",
            rise=ev["rise"], d_load=abs(dl) if dl is not None else None, d_solar=abs(ds) if ds is not None else None, d_wind=abs(dw) if dw is not None else None)
        if pd.notna(row0["price"]) and pd.notna(row1["price"]):
            add("ramp_price", f"The day-ahead price went from {_i(row0['price'])} to {_i(row1['price'])} €/MWh over the same hours.", price_start=_r(row0["price"]), price_end=_r(row1["price"]))
    elif fam == "imp":
        imp = side == "high"
        top = [r for r in NB if r["net_import"] is not None and ((r["net_import"] > 0) if imp else (r["net_import"] < 0))]
        if top:
            t = top[0]
            flow = abs(t["net_import"])
            txt = f"Most of it came from {t['name']} ({_i(flow)} MW on average)" if imp else f"Most of it went to {t['name']} ({_i(flow)} MW on average)"
            nums = {"flow": flow}
            if t["price"] is not None and t["diff"] is not None:
                rel = "lower" if t["diff"] > 0 else "higher"
                txt += f", which priced {_i(abs(t['diff']))} €/MWh {rel} on average"
                nums["diff"] = abs(t["diff"])
                if t["hours_split"] is not None:
                    txt += f", the two prices split in {t['hours_split']} of {t['hours']} hours"
                    nums.update(hours_split=t["hours_split"], hours=t["hours"])
            there, tn = _there(t)
            nums.update(tn)
            add("top_border", txt + f"; {there}.", **nums)
        if "wind_share_load" in U:
            u = U["wind_share_load"]
            add("wind_day", f"Wind covered {_i(u['value'])} % of consumption over the day, {_pct_text(u)}.", wind_share_day=u["value"], pct100=u["pct100"])
        if "gas_share" in U:
            u = U["gas_share"]
            add("gas_day", f"Gas supplied {_i(u['value'])} % of generation, {_pct_text(u)}.", gas_share_day=u["value"], pct100=u["pct100"])
    elif fam == "base":
        for k, lbl in (("gas_share", "Gas supplied {v} % of generation"), ("wind_share_load", "Wind covered {v} % of consumption"),
                       ("solar_share_load", "Solar covered {v} % of consumption"), ("load_mean", "Load averaged {v} MW")):
            if k in U:
                u = U[k]
                add(k, lbl.format(v=_i(u["value"])) + f" over the day, {_pct_text(u)}.", value=u["value"], pct100=u["pct100"])
        near = [r for r in NB if r["diff"] is not None and abs(r["diff"]) <= TH["price_gap"]]
        if near:
            add("moved_with", _names([r["zone"] for r in near]) + f" priced within {_i(TH['price_gap'])} €/MWh of {name} on average: the level was regional.", gap=TH["price_gap"])
        if D["net_import"] is not None and D["load"] and abs(D["net_import"]) >= TH["flow_pts"] / 100 * D["load"]:
            v = D["net_import"]
            _, cp, cn = _counterparty(d, into=v > 0, event=False)
            add("net_flow", f"{name} {'took' if v > 0 else 'sent'} {_i(abs(v))} MW {'from' if v > 0 else 'to'} its neighbours on average" + (f", {cp}" if cp else "") + ".", net=abs(v), **cn)
    elif fam == "capture" and Z is not None:
        tech = m[3:]
        g = Z[tech] if tech in Z else None
        if g is not None and g.notna().any() and Z["price"].notna().any():
            j = pd.concat([g.clip(lower=0).rename("g"), Z["price"].rename("p")], axis=1).dropna()
            if len(j) and j["g"].sum() > 0:
                cap = float((j["g"] * j["p"]).sum() / j["g"].sum())
                cheap = sorted(range(len(j)), key=lambda i: (j["p"].iloc[i], i))[:4]
                share4 = float(j["g"].iloc[cheap].sum() / j["g"].sum() * 100)
                lbl = {"solar": "Solar", "wind_onshore": "Onshore wind", "wind_offshore": "Offshore wind"}[tech]
                add("capture", f"{lbl} earned {_i(cap)} €/MWh on average against a day mean of {_i(D['price'])} €/MWh; {_i(share4)} % of its output came in the 4 cheapest hours.",
                    capture=_r(cap), price_day=D["price"], share_cheap4=_r(share4))
    # neighbours with the same signal (all families)
    same = d.get("same_signal_neighbours") or []
    if same:
        add("neighbours_same", _names(same) + f" also had an unusually {side} {d['label']} that day.")
    return out


# ---------------------------------------------------------------- text
def _i(v) -> int:
    """Whole number (half up; STYLE.md: no decimals). -0 prints as 0."""
    n = int(math.floor(float(v) + 0.5))
    return 0 if n == 0 else n


def signal_phrase(d: dict) -> str:
    """'4-hour storage spread (TB4) 256 €/MWh'; a negative net import share reads as a net export share."""
    label, v, u = d["label"], d["value"], d["unit"]
    if d["metric"] == "import_share" and v < 0:
        label, v = "net export share of load", -v
    return f"{label} {_i(v)}{' %' if u == '%' else ' ' + u}"


def render_text(d: dict) -> str:
    """The context block: signal, event hours, what happened in them, what else was unusual, next door, data notes,
    drivers. Every number comes from `d` (tests/test_diagnose.py parses them back)."""
    day = pd.Timestamp(d["day"])
    u = d["unit"]
    rank = (f"the {'highest' if d['side'] == 'high' else 'lowest'} of its last {d['n_hist']} days" if d["pct100"] in (0, 100)
            else f"{'higher' if d['side'] == 'high' else 'lower'} than on {d['pct100'] if d['side'] == 'high' else 100 - d['pct100']} % of its last {d['n_hist']} days")
    lines = [f"{d['name']}, {day:%a %-d %b %Y}: {signal_phrase(d)}, {rank}{_streak_text(d.get('streak'))}"
             + (f" (typical {_i(d['median'])}, P10 {_i(d['p10'])}, P90 {_i(d['p90'])})" if d.get("median") is not None else "") + "."]
    ev, H, L, D = d["events"], d["hi_stats"], d["lo_stats"], d["day_stats"]
    if d.get("price_label"):
        lines.append(f"Price = {d['price_label']} (an index of trades, not an auction result), converted to €/MWh.")
    if "k" in ev and H and L:
        lines.append(f"The {ev['k']} priciest hours ({d['hours_hi_text']}) averaged {_i(ev['mean_hi'])} €/MWh, the {ev['k']} cheapest ({d['hours_lo_text']}) {_i(ev['mean_lo'])}: "
                     f"a spread of {_i(ev['spread'])} €/MWh.")
    elif d["metric"] == "neg_hours" and L:
        lines.append(f"{len(d['hours_lo'])} hours below zero ({d['hours_lo_text']}), averaging {_i(L['price'])} €/MWh.")
    elif d["metric"] == "res_ramp3" and H:
        lines.append(f"Steepest 3-hour rise of residual load: {_i(ev['rise'])} MW, {d['hours_hi_text']}.")

    def block(S, what):
        if not S:
            return None
        parts = []
        if S["price"] is not None and "k" not in ev:
            parts.append(f"price {_i(S['price'])} €/MWh")
        if S["wind_share"] is not None:
            parts.append(f"wind {_i(S['wind_share'])} % of consumption")
        if S["solar_share"] is not None:
            parts.append(f"solar {_i(S['solar_share'])} %")
        if S["gas_share"] is not None:
            parts.append(f"gas {_i(S['gas_share'])} % of generation")
        if S["load"] is not None:
            parts.append(f"load {_i(S['load'])} MW")
        if S["res"] is not None:
            parts.append(f"residual load {_i(S['res'])} MW")
        if S["net_import"] is not None:
            v = S["net_import"]
            parts.append(f"{'imports' if v >= 0 else 'exports'} {_i(abs(v))} MW")
        return f"{what}: " + ", ".join(parts) + "." if parts else None

    for S, what in ((H, "In the " + ev.get("hi_label", "event hours")), (L, "In the " + ev.get("lo_label", "event hours")), (D, "Over the day")):
        t = block(S, what)
        if t:
            lines.append(t)
    if d["unusual"]:
        lines.append("Also unusual that day: " + "; ".join(
            f"{r['label']} {_i(r['value'])}{'%' if r['unit'] == '%' else ' ' + r['unit'].replace('EUR/MWh', '€/MWh')} (P{r['pct100']}, {r['side']})" for r in d["unusual"]) + ".")
    if d["neighbours"]:
        nb = []
        for r in d["neighbours"][:5]:
            flow = r["net_import"]
            f = f"{d['name']} took {_i(flow)} MW" if flow is not None and flow > 0 else f"{d['name']} sent {_i(-flow)} MW" if flow is not None else "no flow data"
            mix = (" (" + ", ".join(f"{m['label']} {_i(m['share'])} %" for m in r["mix"][:2]) + ")") if r.get("mix") else ""
            if r["price_na"]:
                nb.append(f"{r['name']}: price n/a ({r['price_na']}); {f}{mix}")
            else:
                pl = f" ({r['price_label']})" if r.get("price_label") else ""
                diff = "" if r["diff"] is None else (" the same" if abs(r["diff"]) < 0.5 else f" {_i(abs(r['diff']))} {'lower' if r['diff'] > 0 else 'higher'}")
                split = "" if r["hours_split"] is None else (", priced identically all day" if r["same_all_day"] else f", prices split in {r['hours_split']} of {r['hours']} hours")
                nb.append(f"{r['name']} {_i(r['price'])} €/MWh{pl},{diff}{split}; {f}{mix}")
        lines.append("Next door (mix in the event hours): " + " · ".join(nb) + ".")
    if d["data"] and d["data"]["notes"]:
        lines.append("Data: " + "; ".join(d["data"]["notes"]) + ".")
    if d["drivers"]:
        lines.append("Candidate drivers (co-occurrence, not causation): " + " ".join(f"({k + 1}) {x['text']}" for k, x in enumerate(d["drivers"])))
    return "\n".join(lines)


def numbers_in(obj) -> set:
    """Every number a rendered text may quote, as whole numbers (half up), from the dict: the audit set for the tests."""
    out = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)) and x is not None and not (isinstance(x, float) and math.isnan(x)):
            out.add(_i(x))
            out.add(_i(abs(x)))
            if 0 <= x <= 100:
                out.add(100 - _i(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
            if isinstance(x, list):
                out.add(len(x))
        elif isinstance(x, str) and x[:2].isdigit():
            out.add(int(x[:2]))
    walk(obj)
    return out
