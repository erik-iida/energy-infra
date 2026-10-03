"""Export the data store as small JSON files for the site's Flags and Data tabs (web/data/browse/).

    index.json         {generated, window, zones, groups, vars: [{id, name, grp, tech, unit, def}], avail: {zone: [var id]},
                        capacity: bool}
    ts/<zone>.json     {t0: first hour (unix s), step: 3600, cols: [{id, name, grp, tech, unit}], v: [[...] per col]}
    capacity.json      IRENA installed capacity per country + 30-day capacity factor (see capacity_export)
    flags.json         signals and the metric overview for the latest complete CET day (newsletter.signals)

One file per zone holding every variable, so the page can combine any variables and zones: hourly means of the
native-resolution rows (the store keeps 15/30/60-minute data untouched), UTC hour starts, last 30 days plus the days
ahead. Daily metrics (baseload, TB2/TB4, ...) are computed per CET day by newsletter/metrics.py and repeated on every
hour of that day. Not committed: the deploy job builds it from the `store` release (hourly.yml). STORE_DIR=<folder> reads
a local copy.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collector.store import Store  # noqa: E402
from newsletter import fundamentals as FU  # noqa: E402
from newsletter import metrics as M  # noqa: E402
from newsletter import registry as R  # noqa: E402
from newsletter import signals as SG  # noqa: E402
from pipeline.entsoe import PSR  # noqa: E402

OUT = ROOT / "web" / "data" / "browse"
DAYS_BACK, DAYS_FWD = 30, 2
TECH_KEY = {"nuclear": "nuc", "fossil_brown_coal_lignite": "coal", "fossil_hard_coal": "coal", "fossil_coal_derived_gas": "coal",
            "fossil_gas": "gas", "fossil_oil": "oil", "wind_onshore": "won", "wind_offshore": "woff", "solar": "sol",
            "hydro_run_of_river": "hyd", "hydro_water_reservoir": "hyd", "hydro_pumped_storage": "hyd",
            "biomass": "bio", "waste": "bio"}
G_PRICE, G_RES, G_GEN, G_FC, G_LOAD, G_FLOW = (
    "Prices & daily spreads", "Residual load & interconnection (daily)", "Actual generation",
    "Day-ahead forecast (wind & solar)", "Load", "Cross-border flows")
GROUPS = [G_PRICE, G_RES, G_GEN, G_FC, G_LOAD, G_FLOW]
DEFAULT_ON = {"p|price", "m|tb2", "m|tb4", "l|actual", "g|B16|gen", "g|B19|gen", "g|B18|gen"}
# daily metrics (newsletter/registry.py) repeated on every hour of the CET day; spark spreads are private and not in the registry export
PUB = [m for m in R.METRICS if not m.private]
DAILY = {m.id: (m.label if "daily" in m.label.lower() else m.label + ", daily", m.unit, m.scale) for m in PUB}
TECH_OF = {m.id: m.tech for m in PUB if m.tech}
GROUP_OF = {m.id: R.GROUP_OF[m.family] for m in PUB}


def read(st: Store, ds: str, months: list[str], a, b) -> pd.DataFrame:
    parts = []
    for m in months:
        d = st.read(ds, m)
        if d is not None:
            parts.append(d[(d["ts"] >= a) & (d["ts"] < b)])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def hourly(df: pd.DataFrame, col_of, value: str) -> dict[str, pd.DataFrame]:
    """zone -> wide frame (index UTC hour, one column per variable id) with hourly means."""
    df = df.assign(h=df["ts"].dt.floor("h"), col=col_of(df))
    wide = df.groupby(["zone", "h", "col"])[value].mean().unstack("col")
    return {z: g.droplevel("zone") for z, g in wide.groupby(level="zone")}


class Frames:
    """Per-zone wide frames plus the column metadata, filled dataset by dataset."""

    def __init__(self, idx: pd.DatetimeIndex):
        self.idx, self.frames, self.meta, self.catalog = idx, {}, {}, {}

    def add(self, zone: str, w: pd.DataFrame, meta: dict) -> None:
        w = w.reindex(self.idx).dropna(axis=1, how="all")
        if w.empty:
            return
        cur = self.frames.get(zone)
        self.frames[zone] = w if cur is None else cur.join(w, how="outer")
        for c in w.columns:
            m = meta[c]
            self.meta.setdefault(zone, {})[c] = m
            self.catalog.setdefault(c, m)

    def write(self) -> dict:
        avail = {}
        order = {g: i for i, g in enumerate(GROUPS)}
        for z, w in self.frames.items():
            cols = sorted(w.columns, key=lambda c: (order[self.meta[z][c]["grp"]], list(w.columns).index(c)))
            v = [[None if pd.isna(x) else round(float(x), 2) for x in w[c]] for c in cols]
            p = OUT / "ts" / f"{z}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"t0": int(self.idx[0].timestamp()), "step": 3600,
                                     "cols": [self.meta[z][c] for c in cols], "v": v}, separators=(",", ":")))
            avail[z] = cols
        return avail


CAP_CLS = [("solar", "Solar"), ("wind_onshore", "Onshore wind"), ("wind_offshore", "Offshore wind"), ("hydro", "Hydro (excl. pumped)"),
           ("pumped", "Pumped storage"), ("nuclear", "Nuclear"), ("fossil", "Fossil"), ("bio", "Bio & waste"),
           ("geothermal", "Geothermal"), ("other", "Other")]


def capacity_export(ga: pd.DataFrame, now: datetime) -> dict | None:
    """Installed capacity for every IRENA country (data/ref, latest year) and, where the store has all of the country's
    bidding zones, the 30-day capacity factor from ENTSO-E generation."""
    cc = FU.country_capacity()
    if cc.empty:
        return None
    end = pd.Timestamp(now).floor("D")
    start = end - pd.Timedelta(days=30)
    cf = FU.country_capacity_factors(ga, start, end)
    zones_of: dict[str, list] = {}
    for z, iso in FU.ZONE_ISO3.items():
        zones_of.setdefault(iso, []).append(z)
    cfm: dict[str, dict] = {}
    for r in cf.itertuples():
        v = FU.plausible_cf(r.cls, r.cf)
        if v is not None:
            cfm.setdefault(r.iso3, {})[r.cls] = round(100 * v, 1)
    rows = []
    for (iso, name, yr), g in cc.groupby(["iso3", "country", "year"]):
        rows.append({"id": iso, "name": name, "year": int(yr), "zones": sorted(zones_of.get(iso, [])),
                     "gw": {r.cls: round(r.cap_mw / 1000, 3) for r in g.itertuples()}, "cf": cfm.get(iso, {})})
    return {"classes": [{"id": k, "name": n} for k, n in CAP_CLS], "rows": rows,
            "cf_window": [start.strftime("%Y-%m-%d"), (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]}


FLAG_FOCUS = ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "GR", "BA", "ME", "MK", "EE", "LV", "LT", "DE-LU"]


def flags_export(now: datetime) -> dict | None:
    """Signals of the newsletter framework for the latest complete CET day, plus the overview of every rule metric per
    zone (value and percentile against the zone's own last 90 days). Spark spreads are never part of this file."""
    from newsletter import build as NB  # reads the store again, 93 days
    day = pd.Timestamp(now).tz_convert(M.CET).tz_localize(None).normalize() - pd.Timedelta(days=1)
    da, ga, ld, fl = NB.load_window_all(day)
    if da.empty:
        return None
    metrics = M.all_metrics(da, ga, None, ld, fl)
    rules = [r for r in SG.RULES if not r.metric.startswith("spark")]
    scan = SG.scan(metrics, day, rules)
    hist_days = int(metrics.loc[metrics["metric"] == "baseload", "day"].nunique())
    return {"day": day.strftime("%Y-%m-%d"), "generated": now.isoformat(timespec="seconds"), "window_days": SG.WINDOW_DAYS,
            "min_hist": SG.MIN_HIST, "hist_days": hist_days, "focus": FLAG_FOCUS,
            "rules": [{"metric": r.metric, "label": r.label, "unit": r.unit, "hi": r.hi, "lo": r.lo, "min_abs": r.min_abs}
                      for r in rules],
            "scan": [{k: r[k] for k in ("zone", "metric", "side", "value", "pct", "median", "p10", "p90", "n_hist", "status", "score")}
                     for r in scan]}


def main() -> None:
    now = datetime.now(timezone.utc)
    a = pd.Timestamp(now - timedelta(days=DAYS_BACK)).floor("D")
    b = pd.Timestamp(now + timedelta(days=DAYS_FWD)).floor("D")
    months = [str(p) for p in pd.period_range(a, b, freq="M")]
    st = Store()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    F = Frames(pd.date_range(a.floor("h"), b.floor("h"), freq="h", inclusive="left"))

    def meta(id_, name, grp, tech, unit):
        return {"id": id_, "name": name, "grp": grp, "tech": tech, "unit": unit, "def": id_ in DEFAULT_ON}

    # --- prices (seq 1 only) and the daily metrics built on them
    da = read(st, "da_price", months, a, b)
    ga = read(st, "gen_actual", months, a, b)
    if not da.empty:
        d = da[da["seq"] == 1]
        for cur, g in d.groupby("currency"):
            for z, w in hourly(g, lambda x: "p|price", "price").items():
                F.add(z, w, {"p|price": meta("p|price", "Day-ahead price", G_PRICE, "", f"{cur}/MWh")})
        ldm, flm = read(st, "load", months, a, b), read(st, "flows", months, a, b)
        dm = M.all_metrics(da, ga, None, ldm[ldm["kind"] == "actual"] if not ldm.empty else None, flm if not flm.empty else None)
        dm = dm[dm["metric"].isin(DAILY)]
        loc = pd.Series(F.idx.tz_convert(M.CET).tz_localize(None).normalize(), index=F.idx)
        for z, g in dm.groupby("zone"):
            cols, mm = {}, {}
            for k, gg in g.groupby("metric"):
                name, unit, fac = DAILY[k]
                cols[f"m|{k}"] = loc.map(gg.set_index("day")["value"] * fac)
                mm[f"m|{k}"] = meta(f"m|{k}", name, GROUP_OF[k], TECH_OF.get(k, ""), unit)
            F.add(z, pd.DataFrame(cols, index=F.idx), mm)
    # --- generation
    capx = capacity_export(ga, now) if not ga.empty else capacity_export(None, now)
    if not ga.empty:
        mt = {}
        for psr, (key, name) in PSR.items():
            t = TECH_KEY.get(key, "")
            mt[f"g|{psr}|gen"] = meta(f"g|{psr}|gen", name, G_GEN, t, "MW")
            mt[f"g|{psr}|cons"] = meta(f"g|{psr}|cons", name + " (consumption)", G_GEN, "", "MW")
        for z, w in hourly(ga, lambda x: "g|" + x["psr"] + "|" + x["dir"], "mw").items():
            F.add(z, w, mt)
    d = read(st, "gen_forecast", months, a, b)
    if not d.empty:
        mt = {f"f|{p}": meta(f"f|{p}", PSR.get(p, (p, p))[1] + " forecast", G_FC, TECH_KEY.get(PSR.get(p, ("", ""))[0], ""), "MW")
              for p in d["psr"].unique()}
        for z, w in hourly(d, lambda x: "f|" + x["psr"], "mw").items():
            F.add(z, w, mt)
    d = read(st, "load", months, a, b)
    if not d.empty:
        mt = {"l|actual": meta("l|actual", "Load, actual", G_LOAD, "", "MW"),
              "l|da_forecast": meta("l|da_forecast", "Load, day-ahead forecast", G_LOAD, "", "MW")}
        for z, w in hourly(d, lambda x: "l|" + x["kind"], "mw").items():
            F.add(z, w, mt)
    d = read(st, "flows", months, a, b)
    if not d.empty:
        out = d.rename(columns={"from_zone": "zone", "to_zone": "other"}).assign(col=lambda x: "x|out|" + x["other"])
        inn = d.rename(columns={"to_zone": "zone", "from_zone": "other"}).assign(col=lambda x: "x|in|" + x["other"])
        both = pd.concat([out, inn], ignore_index=True)
        both["h"] = both["ts"].dt.floor("h")
        wide = both.groupby(["zone", "h", "col"])["mw"].mean().unstack("col")
        mt = {c: meta(c, ("Export to " if c.startswith("x|out") else "Import from ") + c.split("|")[2], G_FLOW, "", "MW")
              for c in wide.columns}
        for z, g in wide.groupby(level="zone"):
            F.add(z, g.droplevel("zone"), mt)

    avail = F.write()
    order = {g: i for i, g in enumerate(GROUPS)}
    dk = list(DAILY)  # registry order

    def vkey(m):
        i, g = m["id"], m["grp"]
        k = (0 if i == "p|price" else 1 + dk.index(i[2:])) if g in (G_PRICE, G_RES) else \
            (i.split("|")[1], i.endswith("cons")) if g == G_GEN else \
            (0 if i.endswith("actual") else 1) if g == G_LOAD else m["name"] if g == G_FLOW else i
        return (order[g], str(k) if not isinstance(k, int) else f"{k:03d}")

    vars_ = sorted(F.catalog.values(), key=vkey)
    index = {"generated": now.isoformat(timespec="seconds"), "window": [a.isoformat(), b.isoformat()], "step_s": 3600,
             "zones": sorted(avail), "groups": GROUPS, "vars": vars_, "avail": avail, "capacity": bool(capx)}
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    if capx:
        (OUT / "capacity.json").write_text(json.dumps(capx, separators=(",", ":")))
    try:
        fl = flags_export(now)
        if fl:
            (OUT / "flags.json").write_text(json.dumps(fl, separators=(",", ":")))
    except Exception as e:  # the flags tab is optional; the data browser must still ship
        print(f"flags export failed: {type(e).__name__}: {e}")
    n = sum(1 for _ in OUT.rglob("*.json"))
    size = sum(p.stat().st_size for p in OUT.rglob("*.json")) / 1e6
    print(f"browse: {n} files, {size:.1f} MB; {len(avail)} zones, {len(vars_)} variables, flags {'yes' if (OUT / 'flags.json').exists() else 'no'}")


if __name__ == "__main__":
    main()
