"""Build the daily brief from the data store: facts.json (the contract), brief.md (draft text) and brief.html (one chart).

    python -m newsletter.build                       # yesterday (CET), reads the `store` release via gh
    python -m newsletter.build --day 2026-10-02 --out newsletter/out
    STORE_DIR=./store python -m newsletter.build     # a local copy of the store

The draft text is deterministic (numbers and fixed sentences only). It is meant to be read and polished by a human
or an LLM from facts.json - nothing here calls an API. Backwards-looking by design: yesterday's actuals plus what
tomorrow's day-ahead auction already says.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from common.store import Store

from . import diagnose as DG
from . import fundamentals as FU
from . import metrics as M
from . import signals as S

# CEE / SEE focus (same set as the site's selector), plus DE-LU as the neighbour everybody compares with
FOCUS = ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "GR", "BA", "ME", "MK", "EE", "LV", "LT"]
CONTEXT = ["DE-LU"]
COLS = ["baseload", "tb2", "tb4", "neg_hours", "wind_share_load", "solar_share_load", "spark_top4"]
# full names in the text live in newsletter/zones.py (shared with diagnose.py); ZONE_NAME / zn stay importable from here
from .zones import ZONE_NAME, zn  # noqa: E402,F401


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> list[str]:
    return [str(p) for p in pd.period_range(a.tz_convert("UTC"), b.tz_convert("UTC"), freq="M")]


# raw rows (prices, generation, load, flows) are read for the last RECENT_DAYS only; everything older comes from the stored
# daily metrics (metrics_daily, written by jobs.derive metrics) through load_history / with_history
RECENT_DAYS = 21


def load_history(day: pd.Timestamp, before: pd.Timestamp) -> pd.DataFrame:
    """Stored daily metrics (zone, day, metric, value) for every CET day < `before` up to the first month in the store."""
    st = Store()
    out = []
    for m in st.months("metrics_daily"):
        if m > before.strftime("%Y-%m"):
            continue
        d = st.read("metrics_daily", m)
        if d is not None and len(d):
            out.append(d.loc[d["day"] < before, ["zone", "day", "metric", "value"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["zone", "day", "metric", "value"])


def with_history(metrics: pd.DataFrame, day: pd.Timestamp, back: int = RECENT_DAYS, hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """The freshly computed metrics of the last `back` days before `day` plus the stored history before them: the frame
    the signal scan ranks against (all earlier days, signals.WINDOW_DAYS = None)."""
    cut = day - pd.Timedelta(days=back)
    if hist is None:
        hist = load_history(day, cut)
    else:
        hist = hist[hist["day"] < cut]
    if hist is None or hist.empty:
        return metrics
    hist = hist.astype({"value": "float64"})
    return pd.concat([hist, metrics[metrics["day"] >= cut]], ignore_index=True)


def load_window(day: pd.Timestamp, back: int = RECENT_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """da_price and gen_actual for [day-back, day+2) CET days, slimmed while reading (gen_actual is big): solar, wind, gas
    and the hourly total over all types (metrics.slim_gen)."""
    a = (day - pd.Timedelta(days=back)).tz_localize(M.CET).tz_convert("UTC")
    b = (day + pd.Timedelta(days=2)).tz_localize(M.CET).tz_convert("UTC")
    st = Store()
    da, ga = [], []
    for m in months_between(a, b):
        d = st.read("da_price", m)
        if d is not None:
            da.append(d[(d["ts"] >= a) & (d["ts"] < b)])
        g = st.read("gen_actual", m)
        if g is not None:
            ga.append(M.slim_gen(g[(g["ts"] >= a) & (g["ts"] < b)]))
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return cat(da), cat(ga)


def load_window_all(day: pd.Timestamp, back: int = RECENT_DAYS):
    """da_price, solar/wind gen_actual (as load_window) plus actual load and cross-border flows for the same window."""
    da, ga = load_window(day, back)
    a = (day - pd.Timedelta(days=back)).tz_localize(M.CET).tz_convert("UTC")
    b = (day + pd.Timedelta(days=2)).tz_localize(M.CET).tz_convert("UTC")
    st = Store()
    ld, fl = [], []
    for m in months_between(a, b):
        l = st.read("load", m)
        if l is not None:
            ld.append(l[(l["ts"] >= a) & (l["ts"] < b) & (l["kind"] == "actual")])
        f = st.read("flows", m)
        if f is not None:
            fl.append(f[(f["ts"] >= a) & (f["ts"] < b)])
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return da, ga, cat(ld), cat(fl)


def load_range(a: pd.Timestamp, b: pd.Timestamp):
    """da_price, solar/wind gen_actual, actual load and flows for the UTC range [a, b) (tz-aware)."""
    st = Store()
    out = {"da": [], "ga": [], "ld": [], "fl": []}
    for m in months_between(a, b - pd.Timedelta(seconds=1)):
        d = st.read("da_price", m)
        if d is not None:
            out["da"].append(d[(d["ts"] >= a) & (d["ts"] < b)])
        g = st.read("gen_actual", m)
        if g is not None:
            out["ga"].append(M.slim_gen(g[(g["ts"] >= a) & (g["ts"] < b)]))
        l = st.read("load", m)
        if l is not None:
            out["ld"].append(l[(l["ts"] >= a) & (l["ts"] < b) & (l["kind"] == "actual")])
        f = st.read("flows", m)
        if f is not None:
            out["fl"].append(f[(f["ts"] >= a) & (f["ts"] < b)])
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return cat(out["da"]), cat(out["ga"]), cat(out["ld"]), cat(out["fl"])


def load_day_gen(day: pd.Timestamp) -> pd.DataFrame:
    """Unslimmed gen_actual rows (every production type) for the CET `day` only: the generation mix of each zone for the
    diagnoses ("what was happening next door"). One day, so small."""
    a = day.tz_localize(M.CET).tz_convert("UTC")
    b = (day + pd.Timedelta(days=1)).tz_localize(M.CET).tz_convert("UTC")
    st = Store()
    ga = []
    for m in months_between(a, b - pd.Timedelta(seconds=1)):
        g = st.read("gen_actual", m)
        if g is not None:
            ga.append(g[(g["ts"] >= a) & (g["ts"] < b) & (g["dir"] == "gen")])
    return pd.concat(ga, ignore_index=True) if ga else pd.DataFrame()


def load_fund(day: pd.Timestamp, days: int = FU.PEAK_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All generation types and actual load for the `days` CET days ending on `day` (90 days: the capacity proxy is the
    highest hourly output in that window)."""
    b = (day + pd.Timedelta(days=1)).tz_localize(M.CET).tz_convert("UTC")
    a = b - pd.Timedelta(days=days)
    st = Store()
    ga, ld = [], []
    for m in months_between(a, b - pd.Timedelta(seconds=1)):
        g = st.read("gen_actual", m)
        if g is not None:
            ga.append(g[(g["ts"] >= a) & (g["ts"] < b) & (g["dir"] == "gen") & g["psr"].isin(FU.PSR_CLS)])
        l = st.read("load", m)
        if l is not None:
            ld.append(l[(l["ts"] >= a) & (l["ts"] < b) & (l["kind"] == "actual")])
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return cat(ga), cat(ld)


def _f(x, nd=1):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def table_for(metrics: pd.DataFrame, day: pd.Timestamp, zones: list[str]) -> list[dict]:
    m = metrics[(metrics["day"] == day) & metrics["zone"].isin(zones)]
    w = m.pivot(index="zone", columns="metric", values="value")
    rows = []
    for z in zones:
        if z not in w.index or "baseload" not in w.columns or pd.isna(w.loc[z].get("baseload")):
            continue
        r = {"zone": z}
        for c in COLS:
            v = w.loc[z].get(c) if c in w.columns else None
            pct = c.endswith("_share_load")
            r[c] = _f(v * 100 if pct and v is not None else v, 1)
        rows.append(r)
    return rows


def decoupling(da: pd.DataFrame, fl: pd.DataFrame | None, day: pd.Timestamp, zones: list[str], top: int = 3) -> list[dict]:
    """Connected zone pairs (a physical-flow border in the store) with at least one zone in `zones`, ranked by how far
    apart their baseload prices were on `day`: rel = |a - b| / max(|a|, |b|). Also the hours in which the two hourly
    prices differed by more than 1 EUR/MWh (in coupled markets prices only split when the border capacity is used up)."""
    if fl is None or fl.empty or da is None or da.empty:
        return []
    hp = M.hourly_prices(da)
    hp = hp[M._local_day(hp["h"]) == day]
    pairs = {tuple(sorted(p)) for p in fl[["from_zone", "to_zone"]].drop_duplicates().itertuples(index=False)}
    pz = {z: g.set_index("h")["price"] for z, g in hp.groupby("zone")}
    out = []
    for a, b in pairs:
        if a not in pz or b not in pz or not ({a, b} & set(zones)):
            continue
        j = pd.concat([pz[a].rename("a"), pz[b].rename("b")], axis=1, join="inner")
        if len(j) < M.MIN_PRICE_HOURS:
            continue
        ba, bb = float(j["a"].mean()), float(j["b"].mean())
        den = max(abs(ba), abs(bb))
        if den < 5:
            continue
        hi, lo = (a, b) if ba >= bb else (b, a)
        out.append({"high": hi, "low": lo, "base_high": _f(max(ba, bb)), "base_low": _f(min(ba, bb)),
                    "rel": _f(abs(ba - bb) / den * 100, 0), "hours_apart": int(((j["a"] - j["b"]).abs() > 1).sum()), "hours": int(len(j))})
    return sorted(out, key=lambda r: -r["rel"])[:top]


def tomorrow_block(da: pd.DataFrame, metrics: pd.DataFrame, day: pd.Timestamp, zones: list[str]) -> dict:
    nxt = day + pd.Timedelta(days=1)
    hp = M.hourly_prices(da)
    hp = hp.assign(day=M._local_day(hp["h"])) if not hp.empty else hp
    rows = []
    for z in zones:
        g = hp[(hp["zone"] == z) & (hp["day"] == nxt)] if not hp.empty else hp
        if len(g) < M.MIN_PRICE_HOURS:
            continue
        mx, mn = g.loc[g["price"].idxmax()], g.loc[g["price"].idxmin()]
        loc = lambda h: pd.Timestamp(h).tz_convert(M.CET).strftime("%H:%M")
        v = sorted(g["price"])
        rows.append({"zone": z, "baseload": _f(sum(v) / len(v)), "tb2": _f(sum(v[-2:]) / 2 - sum(v[:2]) / 2),
                     "tb4": _f(sum(v[-4:]) / 4 - sum(v[:4]) / 4), "neg_hours": int(sum(1 for x in v if x < 0)),
                     "max": _f(mx["price"]), "max_at": loc(mx["h"]), "min": _f(mn["price"]), "min_at": loc(mn["h"])})
    return {"day": nxt.strftime("%Y-%m-%d"), "zones": rows}


# story candidates for the diagnoses in facts.json and the brief. Erik, 6-7 Oct 2026: only metrics at the extremes of their own
# history reach the text (P0-P5 or P95-P100), not only spreads (so context metrics at the extremes count too), no daily capture
# rates, nothing fuel-derived, one signal per zone, at most SPREAD_MAX spread-family stories.
TEXT_PCT = 0.05            # a metric reaches the text only at or beyond P5 / P95 of the zone's own history
DIAG_N = 8
DIAG_SKIP = ("cr_", "spark_")
SPREAD = ("tb2", "tb4")
SPREAD_MAX = 3
CTX_SIDES = {"gen_wind_onshore": "high", "gen_wind_offshore": "high", "gen_solar": "high", "wind_share_load": "both",
             "solar_share_load": "high", "vre_share": "high", "gas_share": "high", "load_mean": "high"}  # low solar is just winter
VRE_GAP = 10.0             # percentage points of wind + solar share between two sides of a price gap that are worth a sentence
CTX_WEIGHT = 0.8           # context extremes rank below the fired rules


def extreme(p: float, side: str) -> bool:
    return p >= 1 - TEXT_PCT if side == "high" else p <= TEXT_PCT


def text_signals(sigs: list[dict], scan_rows: list[dict]) -> list[dict]:
    """Fired signals at the extremes (P0-P5 / P95-P100) plus context metrics (wind, solar, demand, gas share) at the extremes,
    strongest first. Same dict shape as signals.evaluate rows."""
    out = [dict(s) for s in sigs if s.get("pct") is not None and extreme(s["pct"], s["side"])]
    have = {(s["zone"], s["metric"]) for s in out}
    for r in scan_rows:
        want = CTX_SIDES.get(r["metric"])
        if not want or r.get("pct") is None or r["status"] != "ok" or (r["zone"], r["metric"]) in have:
            continue
        for side in (("high", "low") if want == "both" else (want,)):
            if extreme(r["pct"], side):
                out.append(dict(r, side=side, score=round(CTX_WEIGHT * (r["pct"] if side == "high" else 1 - r["pct"]), 4), streak=1))
                break
    return sorted(out, key=lambda s: -s["score"])


def story_candidates(sigs: list[dict], zones: list[str], n: int = DIAG_N) -> list[dict]:
    """One signal per focus zone (a non-spread one when the zone has both), strongest first, at most SPREAD_MAX spread-family."""
    ok = [s for s in sigs if s["zone"] in zones and not s["metric"].startswith(DIAG_SKIP)]
    best = {}
    for s in ok:  # already strongest first; a spread loses to any non-spread signal of the same zone
        cur = best.get(s["zone"])
        if cur is None or (cur["metric"] in SPREAD and s["metric"] not in SPREAD):
            best[s["zone"]] = s
    out, ns = [], 0
    for s in sorted(best.values(), key=lambda s: -s["score"]):
        if s["metric"] in SPREAD:
            if ns >= SPREAD_MAX:
                continue
            ns += 1
        out.append(s)
        if len(out) >= n:
            break
    return out


def pick_lead(cand: list[dict]) -> dict | None:
    """Headline = the strongest candidate that did NOT fire yesterday, if there is one (Erik, 5 Oct 2026); else the strongest."""
    new = [s for s in cand if s.get("streak", 1) == 1]
    return (new or cand or [None])[0]


def add_years(sigs: list[dict], metrics: pd.DataFrame, day: pd.Timestamp) -> list[dict]:
    """`years` on every signal: how many earlier days of the same zone reached or passed today's value (on its side) in the
    previous calendar year and so far in this one. 'A level seen on 12 days in 2025 and 31 days so far in 2026' reads better than
    a second percentage (Erik, 6 Oct 2026). Days, not hours: the store keeps daily metrics for the history."""
    for s in sigs:
        h = metrics[(metrics["zone"] == s["zone"]) & (metrics["metric"] == s["metric"]) & (metrics["day"] < day)]
        t = metrics[(metrics["zone"] == s["zone"]) & (metrics["metric"] == s["metric"]) & (metrics["day"] == day)]["value"]
        if h.empty or t.empty:
            continue
        v = float(t.iloc[0])
        beyond = (h["value"] >= v - 1e-9) if s["side"] == "high" else (h["value"] <= v + 1e-9)
        yr = h["day"].dt.year
        s["years"] = {"prev": int(day.year) - 1, "cur": int(day.year), "n_prev": int((beyond & (yr == day.year - 1)).sum()),
                      "n_cur": int((beyond & (yr == day.year)).sum()), "days_prev": int((yr == day.year - 1).sum())}
    return sigs


STREAK_DAYS = 7


def add_streaks(sigs: list[dict], metrics: pd.DataFrame, day: pd.Timestamp, back: int = STREAK_DAYS) -> list[dict]:
    """`streak` on every fired signal: the number of consecutive days (today included, up to `back` + 1) on which the same
    zone, metric and side fired. A signal that fires day after day is persistence, not news; the brief says so instead of
    repeating the sentence (Erik, 5 Oct 2026)."""
    prev = [{(r["zone"], r["metric"], r["side"]) for r in S.evaluate(metrics, day - pd.Timedelta(days=k))} for k in range(1, back + 1)]
    for s in sigs:
        key, n = (s["zone"], s["metric"], s["side"]), 1
        for p in prev:
            if key not in p:
                break
            n += 1
        s["streak"] = n
    return sigs


def diagnoses(cand: list[dict], scan: list[dict], sigs: list[dict], frames: dict, day: pd.Timestamp) -> list[dict]:
    """The structured diagnosis and its text block for each story candidate (newsletter/diagnose.py)."""
    out = []
    for s in cand:
        d = DG.diagnose(s, day, frames, scan, sigs)
        d["text"] = DG.render_text(d)
        out.append(d)
    return out


def decoupling_context(dec: list[dict], frames: dict) -> list[dict]:
    """What differed between the two sides of the widest price gaps, from the day frames only (no speculation): wind + solar
    share of consumption, net flow, own generation mix. `context` = [{key, text, numbers}] on each row."""
    for r in dec:
        hz, lz = frames.get(r["high"]), frames.get(r["low"])
        ctx = []
        if hz is not None and lz is not None:
            H, L = DG.block_stats(hz), DG.block_stats(lz)
            vs = lambda S: (S["wind_share"] or 0) + (S["solar_share"] or 0) if S["wind_share"] is not None or S["solar_share"] is not None else None
            vh, vl = vs(H), vs(L)
            if vh is not None and vl is not None and abs(vl - vh) >= VRE_GAP:
                hi_side, lo_side = (r["low"], r["high"]) if vl > vh else (r["high"], r["low"])
                ctx.append({"key": "vre_gap", "text": f"Wind and solar covered {DG._i(max(vl, vh))} % of consumption in {zn(hi_side)} against {DG._i(min(vl, vh))} % in {zn(lo_side)}.",
                            "numbers": {"vre_high": max(vl, vh), "vre_low": min(vl, vh)}})
            for z, S in ((r["low"], L), (r["high"], H)):
                if S["net_import"] is not None and S["load"] and abs(S["net_import"]) >= DG.TH["flow_pts"] / 100 * S["load"]:
                    ctx.append({"key": "flow_" + z, "text": f"{zn(z)} was a net {'importer' if S['net_import'] > 0 else 'exporter'} over the day, {DG._i(abs(S['net_import']))} MW on average.",
                                "numbers": {"net": abs(S["net_import"])}})
                    break
            mx = DG.mix_stats(lz, None)
            if mx:
                ctx.append({"key": "mix_low", "text": f"{zn(r['low'])}'s own output was mostly " + DG._join([m["label"] for m in mx[:3]]) + ".",
                            "numbers": {f"mix_{m['cls']}": m["share"] for m in mx[:3]}})
        r["context"] = ctx[:3]
    return dec


def build_facts(da: pd.DataFrame, ga: pd.DataFrame, day: pd.Timestamp, srmc: pd.Series | None = None,
                carbon: bool = False, fuel_note: str | None = None, fund_data: tuple | None = None,
                ld: pd.DataFrame | None = None, fl: pd.DataFrame | None = None, ga_day: pd.DataFrame | None = None,
                hist: pd.DataFrame | None = None) -> dict:
    """`hist`: stored daily metrics before the raw window (build.load_history); None = read them from the store."""
    metrics = with_history(M.all_metrics(da, ga, srmc, ld, fl), day, hist=hist)
    focus, ctx = FOCUS + CONTEXT, CONTEXT
    sigs = add_streaks(S.evaluate(metrics, day), metrics, day)
    scan_rows = S.scan(metrics, day, S.RULES + S.CONTEXT)
    tsigs = add_years(text_signals(sigs, scan_rows), metrics, day)
    add_years(sigs, metrics, day)
    zones_day = set(metrics.loc[(metrics["day"] == day) & (metrics["metric"] == "baseload"), "zone"])
    prices_seen = set(da["zone"]) if not da.empty else set()
    notes = []
    missing_price = [z for z in focus if z not in zones_day]
    if missing_price:
        notes.append("No complete day-ahead price day for " + ", ".join(zn(z) for z in missing_price) + ".")
    have_gen = set(metrics.loc[(metrics["day"] == day) & metrics["metric"].str.endswith("_share_load"), "zone"])
    late = [z for z in focus if z in zones_day and z not in have_gen]
    if late:
        notes.append("No wind and solar shares for " + ", ".join(zn(z) for z in late) + ": generation or load data is late.")
    if srmc is not None and day in srmc.index:
        notes.append("Spark spreads: day-ahead price minus the gas cost of a 55 % efficient CCGT at the TTF front-month "
                     + ("incl. carbon." if carbon else "price, FUEL ONLY (no carbon), so they read higher than a clean spark spread.")
                     + " Same reference cost in every zone; local gas premia are not included.")
    elif fuel_note:
        notes.append(fuel_note)
    hist_days = metrics.loc[metrics["metric"] == "baseload", "day"].nunique()
    if hist_days < S.MIN_HIST + 1:
        notes.append(f"Only {hist_days} days of price history in the store: percentile signals need {S.MIN_HIST}+ days.")
    # zone p90 of TB4 for the chart (same history as the signals)
    h4 = metrics[(metrics["metric"] == "tb4") & (metrics["day"] < day)]
    if S.WINDOW_DAYS:
        h4 = h4[h4["day"] >= day - pd.Timedelta(days=S.WINDOW_DAYS)]
    p90 = h4.groupby("zone")["value"].quantile(0.9).to_dict()
    table = table_for(metrics, day, focus)
    for r in table:
        r["tb4_p90"] = _f(p90.get(r["zone"])) if len(h4[h4["zone"] == r["zone"]]) >= S.MIN_HIST else None
    fund, fstats = [], None
    if fund_data is not None:
        fund = FU.fundamentals_table(fund_data[0], fund_data[1], metrics, day, focus, hp=M.hourly_prices(da))
        fstats = fund_stats(fund)
        if not fund:
            notes.append("No generation in the store for the 30-day window: fundamentals skipped.")
    cand = story_candidates(tsigs, focus)
    frames = DG.day_frames(M.hourly_prices(da), ga, M.hourly_load(ld), M.hourly_flows(fl), day, ga_full=ga_day)
    dec = decoupling_context(decoupling(da, fl, day, focus), frames)
    diag = diagnoses(cand, scan_rows, sigs, frames, day)
    lead = pick_lead(cand)
    return {
        "day": day.strftime("%Y-%m-%d"), "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "focus": FOCUS, "context": ctx, "window_days": S.WINDOW_DAYS, "price_zones_in_store": len(prices_seen),
        "fundamentals": fund, "fundamentals_stats": fstats, "decoupling": dec, "zone_names": {z: zn(z) for z in focus},
        "table": table, "signals": sigs, "diagnoses": diag, "lead": {"zone": lead["zone"], "metric": lead["metric"]} if lead else None, "tomorrow": tomorrow_block(da, metrics, day, focus), "notes": notes,
        "definitions": {"tb2": "mean of the 2 highest minus the 2 lowest hourly day-ahead prices of the CET day",
                        "tb4": "same with 4 hours", "share_load": "wind (onshore + offshore) or solar output / actual load, energy",
                        "cr_30d": "30-day capture rate: output-weighted price / mean price over the window",
                        "cf_30d": "mean output over 30 days / highest hourly output in 90 days (capacity proxy)",
                        "pct": "share of the zone's own last days at or below the value"},
        "source": "ENTSO-E Transparency Platform (day-ahead prices A44, actual generation A75, load A65, physical flows A11)",
    }


def fund_stats(fund: list[dict]) -> dict | None:
    """How the 30-day wind + solar share of load lines up with the window's price levels across zones (rank correlation)."""
    d = pd.DataFrame([r for r in fund if r.get("vre_share") is not None and r.get("tb4") is not None])
    if len(d) < 8:
        return None
    out = {"n": int(len(d)), "window_days": 30}
    for k in ("tb4", "neg_hours", "baseload"):
        x = d[["vre_share", k]].dropna()
        out["spearman_vre_" + k] = round(float(x["vre_share"].corr(x[k], method="spearman")), 2) if len(x) >= 8 else None
    return out


# daily capture rates are not quoted (feedback #1: a day is too short to separate them from the baseload)
TEXT_SKIP = ("cr_",)
TB = SPREAD
PREFER_NEW = True  # headline = the strongest signal that did NOT fire yesterday, if there is one (Erik, 5 Oct 2026)
FIGURES_MAX = 3    # numbers per story paragraph (Erik, 7 Oct 2026); the first sentence of a story is always kept


def _i(v) -> int:
    """Whole number for the brief (feedback 3 Oct 2026: no decimals); -0 prints as 0."""
    import math
    return int(math.floor(float(v) + 0.5))  # half up (Python's round() rounds 34.5 to 34)


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def figures(text: str) -> int:
    """Numbers a reader has to take in: every number except clock times (17:00) and years."""
    t = re.sub(r"\b\d{1,2}[′']?:\d{2}\b", " ", text)
    t = re.sub(r"\b20\d\d\b", " ", t)
    return len(re.findall(r"\d+", t))


def rank_phrase(d: dict) -> str:
    """How unusual the value is, without percentiles or day counts: where it has been reached before (days in the previous
    year and so far this year), else 'among the highest of the last N months' (Erik, 6-7 Oct 2026)."""
    y, hi = d.get("years"), d["side"] == "high"
    word = "reached or exceeded" if hi else "reached or undercut"
    if y and y["days_prev"] > 0:
        a, b = y["n_prev"], y["n_cur"]
        day = lambda n: f"{n} day{'' if n == 1 else 's'}"
        if a == 0 and b == 0:
            return f"a level not {'reached' if hi else 'seen'} on any day in {y['prev']} or so far in {y['cur']}"
        return f"a level {word} on {day(a)} in {y['prev']} and {day(b)} so far in {y['cur']}"
    months = max(1, round(d["n_hist"] / 30.4))
    return f"among the {'highest' if hi else 'lowest'} of the last {months} months"


def streak_phrase(n) -> str:
    return f", the {_ord(n)} day in a row" if n and n > 1 else ""


# story groups: the driver pattern behind a signal (spec 4 driver keys), in the order they are told when equally strong
GROUPS = {"tight": "Tight supply.", "surplus": "Wind and solar surplus.", "cheap_night": "Cheap overnight hours.",
          "imports": "Imports.", "other": "Also unusual."}
SURPLUS_CTX = {"gen_wind_onshore", "gen_wind_offshore", "gen_solar", "solar_share_load", "vre_share"}
KIND = {"tb2": "wide storage spreads", "tb4": "wide storage spreads", "neg_hours": "negative-price hours", "res_peak": "a high residual-load peak",
        "res_min": "very low residual load", "res_ramp3": "a steep residual-load ramp", "load_mean": "high demand", "gas_share": "a high gas share",
        "gen_wind_onshore": "strong onshore wind output", "gen_wind_offshore": "strong offshore wind output", "gen_solar": "strong solar output",
        "wind_share_load": "very high wind output", "solar_share_load": "very high solar output", "vre_share": "a very high wind and solar share"}
# order in which driver sentences are told, per group (the rest follow in the diagnosis order)
PRIORITY = {"tight": ["peak_residual", "imports_in_peak", "own_mix_peak", "low_wind_day", "gas_in_peak", "high_load", "hour", "imports_then", "ramp_parts"],
            "surplus": ["vre_in_neg", "exports_in_neg", "cheap_solar", "cheap_wind", "imports_in_neg", "low_load", "neighbours_negative", "res_min", "high_vre_day"],
            "cheap_night": ["cheap_night", "exports_in_trough"], "imports": ["top_border", "wind_day", "gas_day"], "other": []}
NOT_TOLD = ("neighbours_same", "price_then", "capture")  # the take names the zones already; price_then repeats the spread


def group_of(d: dict) -> str:
    m, side, keys = d["metric"], d["side"], {x["key"] for x in d["drivers"]}
    if m == "import_share":
        return "imports"
    if m in SURPLUS_CTX and side == "high":
        return "surplus"
    if m in SPREAD and "peak_residual" in keys:
        return "tight"  # the expensive evening is the story; the cheap midday is its other side
    if m in ("neg_hours", "res_min") or keys & {"cheap_solar", "cheap_wind"}:
        return "surplus"
    if "cheap_night" in keys and "peak_residual" not in keys:
        return "cheap_night"
    if m in (*SPREAD, "res_peak", "res_ramp3", "load_mean", "gas_share") or (m == "baseload" and side == "high") or (m in ("wind_share_load", "gen_wind_onshore") and side == "low"):
        return "tight"
    return "other"


def kind_of(d: dict) -> str:
    if d["metric"] == "import_share":
        return "heavy exports" if d["value"] < 0 else "heavy imports"
    if d["metric"] == "baseload":
        return "high prices" if d["side"] == "high" else "low prices"
    return KIND.get(d["metric"], DG.plain(d["label"]))


def _names_join(zones: list[str]) -> str:
    n = [zn(z) for z in zones]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]


def pick_sentences(d: dict, group: str, n: int) -> list[str]:
    """Up to `n` driver sentences of the diagnosis, in the group's priority order, while the paragraph stays within FIGURES_MAX
    numbers; the first is always kept."""
    pri = PRIORITY.get(group, [])
    ds = [x for x in d["drivers"] if x["key"] not in NOT_TOLD]
    ds = sorted(ds, key=lambda x: pri.index(x["key"]) if x["key"] in pri else len(pri))
    out, used = [], 0
    for x in ds:
        f = figures(x["text"])
        if out and (len(out) >= n or used + f > FIGURES_MAX):
            continue
        out.append(x["text"])
        used += f
    return out


def stories(f: dict, maxn: int = 3) -> list[dict]:
    """The diagnosed candidates grouped by driver pattern: [{group, title, members: [diagnosis], lead}], the group of the
    headline first (it gets the longest paragraph), the rest by their strongest member's score. At most `maxn`."""
    diag = f.get("diagnoses") or []
    if not diag:
        return []
    lead = f.get("lead") or {"zone": diag[0]["zone"], "metric": diag[0]["metric"]}
    by = {}
    for d in diag:
        by.setdefault(group_of(d), []).append(d)
    lead_g = next((g for g, ms in by.items() if any(m["zone"] == lead["zone"] and m["metric"] == lead["metric"] for m in ms)), None)
    order = sorted(by, key=lambda g: (g != lead_g, -max((m.get("score") or 0) for m in by[g])))
    out = []
    for g in order[:maxn]:
        ms = sorted(by[g], key=lambda m: (not (m["zone"] == lead["zone"] and m["metric"] == lead["metric"]), -(m.get("score") or 0)))
        out.append({"group": g, "title": GROUPS[g], "members": ms, "lead": ms[0]})
    return out


def story_text(st: dict, headline: bool) -> str:
    ms, ld = st["members"], st["lead"]
    kinds = []
    for m in ms:
        k = kind_of(m)
        if k not in kinds:
            kinds.append(k)
    zones = list(dict.fromkeys(m["zone"] for m in ms))
    take = f"{_names_join(zones)} stood out for {DG._join(kinds[:2])}."
    sents = pick_sentences(ld, st["group"], 3 if headline else 2)
    same = [m["zone"] for m in ms[1:] if m["drivers"] and ld["drivers"] and m["drivers"][0]["key"] == ld["drivers"][0]["key"]]
    if len(ms) > 1 and same:
        sents.append(f"The same pattern showed in {_names_join(list(dict.fromkeys(same)))}.")
    if not sents and not ld["unusual"]:
        sents.append(_sig_text(ld))
    if not sents:
        un = sorted(ld["unusual"], key=lambda r: -abs(r["pct100"] - 50))[:2]
        if un:
            sents.append(f"{ld['name']} was also unusual in " + DG._join([DG.plain(r["label"]) for r in un]) + ".")
    return f"**{st['title']}** {take} " + " ".join(sents)


def _sig_text(d: dict) -> str:
    return f"{d['name']}: {DG.signal_phrase(d)}, {rank_phrase(d)}{streak_phrase(d.get('streak'))}."


def tomorrow_why(r: dict) -> str:
    """One line on when the low and the peak fall (dayparts), with the usual daily shape; no causation claimed."""
    lo, hi = int(r["min_at"][:2]), int(r["max_at"][:2])
    bits = []
    if 10 <= lo < 16:
        bits.append("the low falls around midday, when solar output usually peaks")
    elif lo < 6 or lo >= 22:
        bits.append("the low falls overnight, when demand is lowest")
    if 16 <= hi < 22:
        bits.append("the peak comes in the evening ramp, after solar fades")
    return ("; ".join(bits)[0].upper() + "; ".join(bits)[1:] + ".") if bits else ""


def draft_brief(f: dict) -> str:
    """Stories, not a metrics dump (Erik, 6-7 Oct 2026): one headline signal, then at most three stories grouped by driver
    pattern (each paragraph answers why, at most FIGURES_MAX numbers, no percentiles / day counts / hour lists), the widest
    price gap with what differed, tomorrow's auction, the renewables leaders. Country names in full; no daily capture rates."""
    day = datetime.strptime(f["day"], "%Y-%m-%d")
    t = f["table"]
    g = lambda v: "-" if v is None else f"{_i(v)}"
    lines = [f"# Radial Economics daily - {day:%a %-d %b %Y}", ""]
    diag = f.get("diagnoses") or []
    lead = f.get("lead")
    dl = next((d for d in diag if lead and d["zone"] == lead["zone"] and d["metric"] == lead["metric"]), diag[0] if diag else None)
    if dl:
        lines += ["**Headline.** " + _sig_text(dl), ""]
        sts = stories(dict(f, lead={"zone": dl["zone"], "metric": dl["metric"]}))
        for i, st in enumerate(sts):
            lines += [story_text(st, headline=i == 0), ""]
    else:
        lines += [f"**Headline.** No CEE/SEE metric reached the extremes of its own history on {day:%-d %b}.", ""]
    dec = f.get("decoupling") or []
    if dec:
        d = dec[0]
        txt = (f"**Price decoupling.** The widest price gap between connected zones was {zn(d['high'])} and {zn(d['low'])}: "
               f"average power price {_i(d['base_high'])} against {_i(d['base_low'])} €/MWh, {_i(d['rel'])} % apart. Prices separated in "
               f"{d['hours_apart']} of {d['hours']} hours, which is typical when the border limit is reached.")
        if d.get("context"):
            txt += " " + " ".join(c["text"] for c in d["context"][:2])
        if len(dec) > 1:
            txt += f" The next-widest gap was between {zn(dec[1]['high'])} and {zn(dec[1]['low'])}."
        lines += [txt, ""]
    tm = f["tomorrow"]
    if tm["zones"]:
        tz = tm["zones"]
        told = {m["zone"] for st in stories(f) for m in st["members"] if m["metric"] in SPREAD} if diag else set()
        pool = [r for r in tz if r["zone"] not in told] or tz
        shown = len(pool) < len(tz)  # do not repeat the zone whose storage spread was told above
        wide = max(pool, key=lambda r: r["tb4"])
        neg = [f"{zn(r['zone'])} ({r['neg_hours']} h)" for r in tz if r["neg_hours"] > 0]
        txt = (f"**Next 24 h.** Tomorrow's auction puts {zn(wide['zone'])} at the widest 4-hour storage spread"
               f"{' of the zones not covered above' if shown else ''}, {_i(wide['tb4'])} €/MWh "
               f"(peak {_i(wide['max'])} at {wide['max_at']} CET, low {_i(wide['min'])} at {wide['min_at']}).")
        why = tomorrow_why(wide)
        txt += (" " + why) if why else ""
        txt += (" Negative hours expected in " + ", ".join(neg) + ".") if neg else " No negative-price hours in the CEE/SEE zones."
        lines += [txt, ""]
    else:
        lines += ["**Next 24 h.** Tomorrow's day-ahead prices are not in the store yet (results arrive ~12:45 CET).", ""]
    tw = sorted([r for r in t if r.get("wind_share_load") is not None], key=lambda r: -r["wind_share_load"])
    ts = sorted([r for r in t if r.get("solar_share_load") is not None], key=lambda r: -r["solar_share_load"])
    if tw or ts:
        txt = "**Renewables leaders in the last 24h.** Relative to average consumption,"
        if tw:
            txt += " wind output was highest in " + DG._join([f"{zn(r['zone'])} ({_i(r['wind_share_load'])} %)" for r in tw[:3]])
        if ts:
            txt += (";" if tw else "") + " solar output was highest in " + DG._join([f"{zn(r['zone'])} ({_i(r['solar_share_load'])} %)" for r in ts[:3]])
        lines += [txt + ".", ""]
    fr = f.get("fundamentals", [])
    if f["notes"]:
        lines += ["_Data notes: " + " ".join(f["notes"]) + "_", ""]
    sp = any(r.get("spark_top4") is not None for r in t)  # the spark column only exists when fuel prices were available
    lines += ["| Zone | Avg. power price | TB2 | TB4 | Neg. h | Wind % of consumption | Solar % of consumption |" + (" Spark top-4 |" if sp else ""),
              "|---|--:|--:|--:|--:|--:|--:|" + ("--:|" if sp else "")]
    for r in sorted(t, key=lambda r: -(r["tb4"] if r.get("tb4") is not None else -1e9)):
        lines.append(f"| {zn(r['zone'])} | {g(r['baseload'])} | {g(r['tb2'])} | {g(r['tb4'])} | {g(r['neg_hours'])} | "
                     f"{g(r.get('wind_share_load'))} | {g(r.get('solar_share_load'))} |" + (f" {g(r.get('spark_top4'))} |" if sp else ""))
    if fr:
        lines += ["", "| Zone (30 days) | Wind % of consumption | Solar % of consumption | Wind CF % | Solar CF % | Wind capture rate % | Solar capture rate % | Avg. power price | TB4 | Neg. h |",
                  "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for r in sorted(fr, key=lambda r: -(r["vre_share"] if r.get("vre_share") is not None else -1)):
            lines.append(f"| {zn(r['zone'])} | {g(r['wind_share'])} | {g(r['solar_share'])} | {g(r['wind_cf'])} | {g(r['solar_cf'])} | "
                         f"{g(r['cr_wind'])} | {g(r['cr_solar'])} | {g(r['baseload'])} | {g(r['tb4'])} | {g(r['neg_hours'])} |")
        lines += ["", "30-day window ending on the brief's day. Wind = onshore + offshore. Share of consumption = output / actual load (energy). "
                  "CF = mean output / the highest hourly output in the last 90 days (a proxy for installed capacity, so it reads higher "
                  "than a nameplate capacity factor). Capture rate = output-weighted day-ahead price / average power price. Avg. power price = mean hourly day-ahead price (baseload)."]
    lines += ["", "Prices €/MWh. Storage spread: the 2-hour (TB2) or 4-hour (TB4) spread is the mean of the 2/4 highest minus the 2/4 lowest hourly "
              "day-ahead prices of the CET day. Source: ENTSO-E Transparency Platform."]
    return "\n".join(lines) + "\n"


def chart_html(f: dict, md: str) -> str:
    rows = sorted([r for r in f["table"] if r.get("tb4") is not None], key=lambda r: -r["tb4"])
    if not rows:
        return ""
    W, L, R, bh = 640, 60, 20, 22
    mx = max(max(r["tb4"] for r in rows), max((r.get("tb4_p90") or 0) for r in rows), 1) * 1.08
    sx = lambda v: L + (W - L - R) * v / mx
    bars = []
    for i, r in enumerate(rows):
        y = 8 + i * (bh + 6)
        bars.append(f'<text x="{L - 8}" y="{y + bh * .7}" text-anchor="end" class="lbl">{r["zone"]}</text>'
                    f'<rect x="{L}" y="{y}" width="{max(sx(r["tb4"]) - L, 1):.1f}" height="{bh}" rx="3" class="bar"/>'
                    f'<text x="{sx(r["tb4"]) + 6:.1f}" y="{y + bh * .7}" class="val">{r["tb4"]:g}</text>')
        if r.get("tb4_p90"):
            bars.append(f'<line x1="{sx(r["tb4_p90"]):.1f}" x2="{sx(r["tb4_p90"]):.1f}" y1="{y - 2}" y2="{y + bh + 2}" class="p90"/>')
    H = 16 + len(rows) * (bh + 6)
    body = "".join(f"<p>{ln}</p>" if not ln.startswith(("|", "#")) else "" for ln in md.splitlines() if ln.strip())
    body = body.replace("**", "").replace("_", "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radial Economics daily {f['day']}</title><style>
:root{{--bg:#fff;--fg:#1a1d21;--mut:#5b6470;--bar:#1f5f99;--p90:#c2410c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171b;--fg:#e8eaed;--mut:#9aa4b0;--bar:#6aaef0;--p90:#fb923c}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;max-width:700px;margin:0 auto;padding:16px}}
.lbl,.val{{font-size:12px;fill:var(--fg)}}.bar{{fill:var(--bar)}}.p90{{stroke:var(--p90);stroke-width:2}}
svg{{width:100%;height:auto}}.mut{{color:var(--mut);font-size:13px}}</style></head><body>
<h1 style="font-size:20px">Radial Economics daily - {f['day']}</h1>{body}
<h2 style="font-size:16px">TB4 storage spread, EUR/MWh <span class="mut">(orange tick = zone's 90th percentile{(" over the last " + str(f['window_days']) + " days") if f['window_days'] else " over all earlier days in the store"})</span></h2>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="TB4 by zone">{''.join(bars)}</svg>
<p class="mut">Source: ENTSO-E Transparency Platform. Backwards-looking market data, not advice.</p></body></html>"""


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="CET delivery day YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--out", default="newsletter/out")
    ap.add_argument("--no-fuel", action="store_true", help="skip fuel prices / spark spreads (the public site build)")
    a = ap.parse_args(argv)
    today_cet = pd.Timestamp.now(tz=M.CET).tz_localize(None).normalize()
    day = pd.Timestamp(a.day) if a.day else today_cet - pd.Timedelta(days=1)
    da, ga, ld, fl = load_window_all(day)
    if da.empty:
        raise SystemExit("no da_price rows in the store for this window")
    srmc, carbon, fuel_note = None, False, None
    try:
        if a.no_fuel:
            raise RuntimeError("fuel prices switched off")
        from . import fuel
        days = pd.date_range(day - pd.Timedelta(days=RECENT_DAYS + 3), day + pd.Timedelta(days=1))  # spark metrics exist for the raw window only (never stored)
        srmc, carbon = fuel.srmc_by_day(days, fuel.load_ttf(), fuel.load_eua())
    except Exception as e:  # fuel prices are optional: the brief is still useful without spark spreads
        fuel_note = None if a.no_fuel else f"Spark spreads unavailable today (fuel price fetch failed: {type(e).__name__})."
        if fuel_note:
            print(fuel_note)
    f = build_facts(da, ga, day, srmc, carbon, fuel_note, fund_data=load_fund(day), ld=ld, fl=fl, ga_day=load_day_gen(day))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    md = draft_brief(f)
    (out / "facts.json").write_text(json.dumps(f, indent=1, default=str))
    (out / "brief.md").write_text(md)
    (out / "brief.html").write_text(chart_html(f, md))
    print(md)
    print(f"wrote {out}/facts.json, brief.md, brief.html")


if __name__ == "__main__":
    main()
