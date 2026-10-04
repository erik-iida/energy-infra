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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from common.store import Store

from . import fundamentals as FU
from . import metrics as M
from . import signals as S

# CEE / SEE focus (same set as the site's selector), plus DE-LU as the neighbour everybody compares with
FOCUS = ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "GR", "BA", "ME", "MK", "EE", "LV", "LT"]
CONTEXT = ["DE-LU"]
COLS = ["baseload", "tb2", "tb4", "neg_hours", "wind_share_load", "solar_share_load", "spark_top4"]
# full names in the text (feedback #1: always write country names out); multi-zone countries say which part
ZONE_NAME = {"AL": "Albania", "AT": "Austria", "BA": "Bosnia and Herzegovina", "BE": "Belgium", "BG": "Bulgaria",
             "CH": "Switzerland", "CZ": "Czechia", "DE-LU": "Germany-Luxembourg", "DK1": "West Denmark", "DK2": "East Denmark",
             "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "Great Britain", "GR": "Greece",
             "HR": "Croatia", "HU": "Hungary", "IE(SEM)": "Ireland (all-island)", "LT": "Lithuania", "LV": "Latvia",
             "ME": "Montenegro", "MK": "North Macedonia", "NL": "the Netherlands", "PL": "Poland", "PT": "Portugal",
             "RO": "Romania", "RS": "Serbia", "SI": "Slovenia", "SK": "Slovakia", "UA-IPS": "Ukraine",
             "NO1": "Norway (Oslo, NO1)", "NO2": "Norway (south-west, NO2)", "NO3": "Norway (central, NO3)",
             "NO4": "Norway (north, NO4)", "NO5": "Norway (west, NO5)", "SE1": "Sweden (SE1)", "SE2": "Sweden (SE2)",
             "SE3": "Sweden (Stockholm, SE3)", "SE4": "Sweden (Malmö, SE4)", "IT-North": "Northern Italy",
             "IT-Centre-North": "Central-Northern Italy", "IT-Centre-South": "Central-Southern Italy", "IT-South": "Southern Italy",
             "IT-Calabria": "Calabria", "IT-Sicily": "Sicily", "IT-Sardinia": "Sardinia"}


def zn(z: str) -> str:
    return ZONE_NAME.get(z, z)


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> list[str]:
    return [str(p) for p in pd.period_range(a.tz_convert("UTC"), b.tz_convert("UTC"), freq="M")]


def load_window(day: pd.Timestamp, back: int = S.WINDOW_DAYS + 3) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def load_window_all(day: pd.Timestamp, back: int = S.WINDOW_DAYS + 3):
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


def build_facts(da: pd.DataFrame, ga: pd.DataFrame, day: pd.Timestamp, srmc: pd.Series | None = None,
                carbon: bool = False, fuel_note: str | None = None, fund_data: tuple | None = None,
                ld: pd.DataFrame | None = None, fl: pd.DataFrame | None = None) -> dict:
    metrics = M.all_metrics(da, ga, srmc, ld, fl)
    focus, ctx = FOCUS + CONTEXT, CONTEXT
    sigs = S.evaluate(metrics, day)
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
    # zone p90 of TB4 for the chart
    start = day - pd.Timedelta(days=S.WINDOW_DAYS)
    h4 = metrics[(metrics["metric"] == "tb4") & (metrics["day"] >= start) & (metrics["day"] < day)]
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
    dec = decoupling(da, fl, day, focus)
    return {
        "day": day.strftime("%Y-%m-%d"), "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "focus": FOCUS, "context": ctx, "window_days": S.WINDOW_DAYS, "price_zones_in_store": len(prices_seen),
        "fundamentals": fund, "fundamentals_stats": fstats, "decoupling": dec, "zone_names": {z: zn(z) for z in focus},
        "table": table, "signals": sigs, "tomorrow": tomorrow_block(da, metrics, day, focus), "notes": notes,
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


def _ord(p: float) -> str:
    n = int(round(p * 100))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


# daily capture rates are not quoted (feedback #1: a day is too short to separate them from the baseload); TB spreads
# only when nothing else fired
TEXT_SKIP = ("cr_",)
TB = ("tb2", "tb4")


def _i(v) -> int:
    """Whole number for the brief (feedback 3 Oct 2026: no decimals); -0 prints as 0."""
    import math
    return int(math.floor(float(v) + 0.5))  # half up (Python's round() rounds 34.5 to 34)


def _sig_text(s: dict) -> str:
    unit = "%" if s["unit"] == "%" else f" {s['unit'].replace('EUR/MWh', '€/MWh')}"
    p = round(s["pct"] * 100)
    rank = (f"the {'highest' if s['side'] == 'high' else 'lowest'} of its last {s['n_hist']} days" if p in (0, 100)
            else f"{'higher' if s['side'] == 'high' else 'lower'} than on {p if s['side'] == 'high' else 100 - p} % of its last {s['n_hist']} days")
    return f"{zn(s['zone'])}: {s['label']} at {_i(s['value'])}{unit}, {rank}."


def draft_brief(f: dict) -> str:
    """Short on purpose (feedback #1): one signal in the headline, the widest price split between connected zones, the
    auction for tomorrow, wind and solar as share of load. Country names in full; no daily capture rates."""
    day = datetime.strptime(f["day"], "%Y-%m-%d")
    t = f["table"]
    g = lambda v: "-" if v is None else f"{_i(v)}"
    lines = [f"# GridEconomics daily - {day:%a %-d %b %Y}", ""]
    fs = [s for s in f["signals"] if s["zone"] in f["focus"] + f["context"] and not s["metric"].startswith(TEXT_SKIP)]
    lead = [s for s in fs if s["metric"] not in TB] or fs
    if lead:
        lines += ["**Headline.** " + _sig_text(lead[0]), ""]
    else:
        lines += [f"**Headline.** No CEE/SEE metric left its own {f['window_days']}-day normal range on {day:%-d %b}.", ""]
    dec = f.get("decoupling") or []
    if dec:
        d = dec[0]
        txt = (f"**Price decoupling.** The widest price gap between connected zones was {zn(d['high'])} and {zn(d['low'])}: "
               f"average power price {_i(d['base_high'])} against {_i(d['base_low'])} €/MWh, {_i(d['rel'])} % apart, with prices split in "
               f"{d['hours_apart']} of {d['hours']} hours. In coupled markets prices only separate when the cross-border "
               "capacity is fully used, so the border was the bottleneck in those hours.")
        if len(dec) > 1:
            txt += f" Next: {zn(dec[1]['high'])} and {zn(dec[1]['low'])} ({_i(dec[1]['rel'])} % apart)."
        lines += [txt, ""]
    tm = f["tomorrow"]
    if tm["zones"]:
        tz = tm["zones"]
        wide = max(tz, key=lambda r: r["tb4"])
        neg = [zn(r["zone"]) for r in tz if r["neg_hours"] > 0]
        txt = (f"**Next 24 h.** Tomorrow's auction puts {zn(wide['zone'])} at the widest TB4, {_i(wide['tb4'])} €/MWh "
               f"(peak {_i(wide['max'])} at {wide['max_at']} CET, low {_i(wide['min'])} at {wide['min_at']}).")
        txt += (" Negative hours expected in " + ", ".join(neg) + ".") if neg else " No negative-price hours in the CEE/SEE zones."
        lines += [txt, ""]
    else:
        lines += ["**Next 24 h.** Tomorrow's day-ahead prices are not in the store yet (results arrive ~12:45 CET).", ""]
    fr = f.get("fundamentals", [])
    fw = sorted([r for r in fr if r.get("wind_share") is not None], key=lambda r: -r["wind_share"])
    fsol = sorted([r for r in fr if r.get("solar_share") is not None], key=lambda r: -r["solar_share"])
    if fw or fsol:
        txt = "**Fundamentals (last 30 days).**"
        if fw:
            txt += " Wind output covered the largest share of consumption in " + ", ".join(f"{zn(r['zone'])} ({_i(r['wind_share'])} %)" for r in fw[:3]) + "."
        if fsol:
            txt += " Solar did in " + ", ".join(f"{zn(r['zone'])} ({_i(r['solar_share'])} %)" for r in fsol[:3]) + "."
        st = f.get("fundamentals_stats")
        if st and st.get("spearman_vre_neg_hours") is not None:
            txt += (f" Across {st['n']} zones the rank correlation of the wind + solar share of consumption with negative hours is "
                    f"{st['spearman_vre_neg_hours']:+g}" + (f" and with the mean TB4 {st['spearman_vre_tb4']:+g}." if st.get("spearman_vre_tb4") is not None else "."))
        lines += [txt, ""]
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
    lines += ["", "Prices €/MWh. TB2/TB4: mean of the 2/4 highest minus 2/4 lowest hourly day-ahead prices of the CET day. "
              "Source: ENTSO-E Transparency Platform."]
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
<title>GridEconomics daily {f['day']}</title><style>
:root{{--bg:#fff;--fg:#1a1d21;--mut:#5b6470;--bar:#1f5f99;--p90:#c2410c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171b;--fg:#e8eaed;--mut:#9aa4b0;--bar:#6aaef0;--p90:#fb923c}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;max-width:700px;margin:0 auto;padding:16px}}
.lbl,.val{{font-size:12px;fill:var(--fg)}}.bar{{fill:var(--bar)}}.p90{{stroke:var(--p90);stroke-width:2}}
svg{{width:100%;height:auto}}.mut{{color:var(--mut);font-size:13px}}</style></head><body>
<h1 style="font-size:20px">GridEconomics daily - {f['day']}</h1>{body}
<h2 style="font-size:16px">TB4 storage spread, EUR/MWh <span class="mut">(orange tick = zone's 90th percentile, last {f['window_days']} days)</span></h2>
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
        days = pd.date_range(day - pd.Timedelta(days=S.WINDOW_DAYS + 3), day + pd.Timedelta(days=1))
        srmc, carbon = fuel.srmc_by_day(days, fuel.load_ttf(), fuel.load_eua())
    except Exception as e:  # fuel prices are optional: the brief is still useful without spark spreads
        fuel_note = None if a.no_fuel else f"Spark spreads unavailable today (fuel price fetch failed: {type(e).__name__})."
        if fuel_note:
            print(fuel_note)
    f = build_facts(da, ga, day, srmc, carbon, fuel_note, fund_data=load_fund(day), ld=ld, fl=fl)
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
