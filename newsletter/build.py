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

from collector.store import Store

from . import metrics as M
from . import signals as S

# CEE / SEE focus (same set as the site's selector), plus DE-LU as the neighbour everybody compares with
FOCUS = ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "GR", "BA", "ME", "MK", "EE", "LV", "LT"]
CONTEXT = ["DE-LU"]
COLS = ["baseload", "tb2", "tb4", "neg_hours", "cr_wind_onshore", "cr_solar"]


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> list[str]:
    return [str(p) for p in pd.period_range(a.tz_convert("UTC"), b.tz_convert("UTC"), freq="M")]


def load_window(day: pd.Timestamp, back: int = S.WINDOW_DAYS + 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """da_price and solar/wind gen_actual for [day-back, day+2) CET days, filtered while reading (gen_actual is big)."""
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
            ga.append(g[(g["ts"] >= a) & (g["ts"] < b) & (g["dir"] == "gen") & g["psr"].isin(M.TECH)])
    cat = lambda xs: pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()
    return cat(da), cat(ga)


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
            r[c] = _f(v * 100 if c.startswith("cr_") and v is not None else v, 0 if c.startswith("cr_") else 1)
        rows.append(r)
    return rows


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


def build_facts(da: pd.DataFrame, ga: pd.DataFrame, day: pd.Timestamp) -> dict:
    metrics = M.all_metrics(da, ga)
    focus, ctx = FOCUS + CONTEXT, CONTEXT
    sigs = S.evaluate(metrics, day)
    zones_day = set(metrics.loc[(metrics["day"] == day) & (metrics["metric"] == "baseload"), "zone"])
    prices_seen = set(da["zone"]) if not da.empty else set()
    notes = []
    missing_price = [z for z in focus if z not in zones_day]
    if missing_price:
        notes.append("No complete day-ahead price day for: " + ", ".join(missing_price))
    have_gen = set(metrics.loc[(metrics["day"] == day) & metrics["metric"].str.startswith("cr_"), "zone"])
    late = [z for z in focus if z in zones_day and z not in have_gen]
    if late:
        notes.append("No capture rates (generation data late or none): " + ", ".join(late))
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
    return {
        "day": day.strftime("%Y-%m-%d"), "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "focus": FOCUS, "context": ctx, "window_days": S.WINDOW_DAYS, "price_zones_in_store": len(prices_seen),
        "table": table, "signals": sigs, "tomorrow": tomorrow_block(da, metrics, day, focus), "notes": notes,
        "definitions": {"tb2": "mean of the 2 highest minus the 2 lowest hourly day-ahead prices of the CET day",
                        "tb4": "same with 4 hours", "cr": "capture price / baseload, generation-weighted by hour",
                        "pct": "share of the zone's own last days at or below the value"},
        "source": "ENTSO-E Transparency Platform (day-ahead prices A44, actual generation A75)",
    }


def _ord(p: float) -> str:
    n = int(round(p * 100))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _sig_text(s: dict) -> str:
    unit = "%" if s["unit"] == "%" else f" {s['unit']}"
    where = (f"the {'highest' if s['side'] == 'high' else 'lowest'} of its last {s['n_hist']} days"
             if s["pct"] >= 0.995 or s["pct"] <= 0.005
             else f"at the {_ord(s['pct'])} percentile of its last {s['n_hist']} days")
    return f"{s['zone']}: {s['label']} {s['value']:g}{unit}, {where} (median {s['median']:g}{unit})."


def draft_brief(f: dict) -> str:
    day = datetime.strptime(f["day"], "%Y-%m-%d")
    t = f["table"]
    lines = [f"# GridEconomics daily - {day:%a %-d %b %Y}", ""]
    focus_rows = [r for r in t if r["zone"] in f["focus"] and r.get("tb4") is not None]
    if focus_rows:
        top = max(focus_rows, key=lambda r: r["tb4"])
        med = sorted(r["tb4"] for r in focus_rows)[len(focus_rows) // 2]
        lines += [f"**Headline.** Storage spreads were widest in {top['zone']} on {day:%-d %b}: TB4 {top['tb4']:g} EUR/MWh "
                  f"(CEE/SEE median {med:g}), baseload {top['baseload']:g} EUR/MWh.", ""]
    else:
        lines += [f"**Headline.** No complete day-ahead price day for the CEE/SEE zones on {day:%-d %b} yet.", ""]
    fs = [s for s in f["signals"] if s["zone"] in f["focus"] + f["context"]]
    if fs:
        lines += ["**Outside its normal range.** " + " ".join(_sig_text(s) for s in fs[:2]), ""]
    else:
        lines += [f"**Outside its normal range.** No CEE/SEE metric left its own {f['window_days']}-day normal range.", ""]
    tm = f["tomorrow"]
    if tm["zones"]:
        tz = tm["zones"]
        wide = max(tz, key=lambda r: r["tb4"])
        neg = [r["zone"] for r in tz if r["neg_hours"] > 0]
        txt = (f"**Next 24 h.** Tomorrow's auction puts {wide['zone']} at the widest TB4, {wide['tb4']:g} EUR/MWh "
               f"(peak {wide['max']:g} at {wide['max_at']} CET, low {wide['min']:g} at {wide['min_at']}).")
        txt += (" Negative hours expected in " + ", ".join(neg) + ".") if neg else " No negative-price hours in the CEE/SEE zones."
        lines += [txt, ""]
    else:
        lines += ["**Next 24 h.** Tomorrow's day-ahead prices are not in the store yet (results arrive ~12:45 CET).", ""]
    if f["notes"]:
        lines += ["_Data notes: " + " ".join(f["notes"]) + "_", ""]
    lines += ["| Zone | Baseload | TB2 | TB4 | Neg. h | Wind on CR % | Solar CR % |", "|---|--:|--:|--:|--:|--:|--:|"]
    g = lambda v: "-" if v is None else f"{v:g}"
    for r in sorted(t, key=lambda r: -(r["tb4"] if r.get("tb4") is not None else -1e9)):
        lines.append(f"| {r['zone']} | {g(r['baseload'])} | {g(r['tb2'])} | {g(r['tb4'])} | {g(r['neg_hours'])} | "
                     f"{g(r.get('cr_wind_onshore'))} | {g(r.get('cr_solar'))} |")
    lines += ["", "Prices EUR/MWh. TB2/TB4: mean of the 2/4 highest minus 2/4 lowest hourly day-ahead prices of the CET day. "
              "CR = capture rate (generation-weighted price / baseload). Source: ENTSO-E Transparency Platform."]
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
    a = ap.parse_args(argv)
    today_cet = pd.Timestamp.now(tz=M.CET).tz_localize(None).normalize()
    day = pd.Timestamp(a.day) if a.day else today_cet - pd.Timedelta(days=1)
    da, ga = load_window(day)
    if da.empty:
        raise SystemExit("no da_price rows in the store for this window")
    f = build_facts(da, ga, day)
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
