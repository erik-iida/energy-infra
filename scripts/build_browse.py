"""Export the data store as small JSON files for the site's Flags and Data tabs and the map (build/data/browse/).

    index.json         {generated, window, zones, groups, vars: [{id, name, grp, tech, unit, def}], avail: {zone: [var id]},
                        capacity: bool}
    ts/<zone>.json     {t0: first hour (unix s), step: 3600, cols: [{id, name, grp, tech, unit}], v: [[...] per col]}
    capacity.json      IRENA installed capacity per country + 30-day capacity factor (see capacity_export)
    flags.json         signals and the metric overview for the latest complete CET day (newsletter.signals)
    flags/<day>.json   the same for each of the last FLAG_DAYS complete CET days (deep links on the Flags tab), plus
                       flags/index.json listing them; every file also carries `context` (display-only metrics, signals.CONTEXT)

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
from common import paths as config  # noqa: E402  (paths: data/static, build/)
from common.store import Store  # noqa: E402
from newsletter import fundamentals as FU  # noqa: E402
from newsletter import metrics as M  # noqa: E402
from newsletter import registry as R  # noqa: E402
from newsletter import signals as SG  # noqa: E402
from common.entsoe import PSR  # noqa: E402

OUT = config.BUILD_DATA / "browse"
DAYS_BACK, DAYS_FWD = 30, 2
TECH_KEY = {"nuclear": "nuc", "fossil_brown_coal_lignite": "coal", "fossil_hard_coal": "coal", "fossil_coal_derived_gas": "coal",
            "fossil_gas": "gas", "fossil_oil": "oil", "wind_onshore": "won", "wind_offshore": "woff", "solar": "sol",
            "hydro_run_of_river": "hyd", "hydro_water_reservoir": "hyd", "hydro_pumped_storage": "hyd",
            "biomass": "bio", "waste": "bio"}
G_PRICE, G_RES, G_SYS, G_GEN, G_FC, G_LOAD, G_FLOW = (
    "Prices & daily spreads", "Residual load & interconnection (daily)", "Generation & load (daily)", "Actual generation",
    "Day-ahead forecast (wind & solar)", "Load", "Cross-border flows")
GROUPS = [G_PRICE, G_RES, G_SYS, G_GEN, G_FC, G_LOAD, G_FLOW]
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
        unknown = [c for c in w.columns if c not in meta]
        if unknown:  # a new series kind in the store must not take the whole export down
            print(f"browse: no metadata for {unknown} ({zone}); skipped")
            w = w.drop(columns=unknown)
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
            p.write_text(json.dumps({"schema": 1, "t0": int(self.idx[0].timestamp()), "step": 3600,
                                     "cols": [self.meta[z][c] for c in cols], "v": v}, separators=(",", ":")))
            avail[z] = cols
        return avail


CAP_CLS = [("solar", "Solar"), ("wind_onshore", "Onshore wind"), ("wind_offshore", "Offshore wind"), ("hydro", "Hydro (excl. pumped)"),
           ("pumped", "Pumped storage"), ("nuclear", "Nuclear"), ("fossil", "Fossil"), ("bio", "Bio & waste"),
           ("geothermal", "Geothermal"), ("other", "Other")]


def capacity_export(ga: pd.DataFrame | None, now: datetime) -> dict | None:
    """Installed capacity for every IRENA country (data/ref, latest year: a reference only, it is older than the fleet)
    and, where the store has all of the country's bidding zones, the 90-day peak output per class (the capacity proxy)
    and the 30-day capacity factor against it (newsletter.fundamentals.peak_cf). `ga` covers the last 90 days."""
    cc = FU.country_capacity()
    if cc.empty:
        return None
    end = pd.Timestamp(now).floor("D")
    start = end - pd.Timedelta(days=30)
    pc = FU.country_peak_cf(ga, start, end) if ga is not None and not ga.empty else pd.DataFrame(columns=["iso3", "cls", "cap_mw", "cf"])
    zones_of: dict[str, list] = {}
    for z, iso in FU.ZONE_ISO3.items():
        zones_of.setdefault(iso, []).append(z)
    cfm: dict[str, dict] = {}
    pkm: dict[str, dict] = {}
    for r in pc.itertuples():
        cfm.setdefault(r.iso3, {})[r.cls] = round(100 * r.cf, 1)
        pkm.setdefault(r.iso3, {})[r.cls] = round(r.cap_mw / 1000, 3)
    rows = []
    for (iso, name, yr), g in cc.groupby(["iso3", "country", "year"]):
        rows.append({"id": iso, "name": name, "year": int(yr), "zones": sorted(zones_of.get(iso, [])),
                     "gw": {r.cls: round(r.cap_mw / 1000, 3) for r in g.itertuples()}, "pk": pkm.get(iso, {}), "cf": cfm.get(iso, {})})
    return {"classes": [{"id": k, "name": n} for k, n in CAP_CLS], "rows": rows, "cf_method": "peak90",
            "cf_window": [start.strftime("%Y-%m-%d"), (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
            "peak_window": [(end - pd.Timedelta(days=FU.PEAK_DAYS)).strftime("%Y-%m-%d"), (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]}


FLAG_FOCUS = ["PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "GR", "BA", "ME", "MK", "EE", "LV", "LT", "DE-LU"]


FLAG_DAYS = 14  # how long a deep link (#flags/<zone>/<metric>/<day>) keeps working
SCAN_KEYS = ("zone", "metric", "side", "value", "pct", "median", "p10", "p90", "n_hist", "status", "score")
CTX_KEYS = ("zone", "metric", "value", "pct", "median", "p10", "p90", "n_hist", "status")


def flags_export(now: datetime, days: int = FLAG_DAYS) -> list[dict]:
    """Signals of the newsletter framework for each of the last `days` complete CET days (newest first), plus the
    overview of every rule metric per zone (value and percentile against every earlier day of the zone in the store) and the
    display-only context metrics. Spark spreads are never part of these files."""
    from newsletter import build as NB  # raw rows for the last `days` + a margin; older days from the stored metrics_daily
    last = pd.Timestamp(now).tz_convert(M.CET).tz_localize(None).normalize() - pd.Timedelta(days=1)
    back = days + 3
    da, ga, ld, fl = NB.load_window_all(last, back=back)
    if da.empty:
        return []
    metrics = NB.with_history(M.all_metrics(da, ga, None, ld, fl), last, back=back)
    rules = [r for r in SG.RULES if not r.metric.startswith("spark")]
    base = metrics[metrics["metric"] == "baseload"]
    out = []
    for k in range(days):
        day = last - pd.Timedelta(days=k)
        scan = SG.scan(metrics, day, rules)
        if not scan:
            continue
        ctx = SG.scan(metrics, day, SG.CONTEXT)
        hist_days = int(base.loc[base["day"] <= day, "day"].nunique())
        out.append({"day": day.strftime("%Y-%m-%d"), "generated": now.isoformat(timespec="seconds"),
                    "window_days": SG.WINDOW_DAYS, "min_hist": SG.MIN_HIST, "hist_days": hist_days, "focus": FLAG_FOCUS,
                    "rules": [{"metric": r.metric, "label": r.label, "unit": r.unit, "hi": r.hi, "lo": r.lo, "min_abs": r.min_abs}
                              for r in rules],
                    "scan": [{k2: r[k2] for k2 in SCAN_KEYS} for r in scan],
                    "context_rules": [{"metric": r.metric, "label": r.label, "unit": r.unit} for r in SG.CONTEXT],
                    "context": [{k2: r[k2] for k2 in CTX_KEYS} for r in ctx]})
    return out


AGG_WINDOWS = {"w1": 7, "m1": 30, "y1": 365}   # keys used by the page's map window selector (plus "now" / "d1" from the feed)


def agg_export(st: Store, now: datetime) -> dict | None:
    """browse/agg.json: per zone and window (last 7 / 30 / 365 CET days ending yesterday), averages of the stored daily metrics
    for the map's zone colours: price (mean of daily baseload), tb2 / tb4 (mean of the daily spreads), wind / solar /
    wind+solar as a share of load and self-sufficiency = generation of all types / load (ratios of the window's energy:
    sums of the daily means), plus the number of days behind each number. Reads metrics_daily only (small)."""
    end = pd.Timestamp(now).tz_convert(M.CET).normalize().tz_localize(None) - pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=max(AGG_WINDOWS.values()) - 1)
    months = [str(x) for x in pd.period_range(start, end, freq="M")]
    parts = [d for d in (st.read("metrics_daily", m) for m in months) if d is not None]
    if not parts:
        return None
    dm = pd.concat(parts, ignore_index=True)
    dm["day"] = pd.to_datetime(dm["day"])
    dm = dm[(dm["day"] >= start) & (dm["day"] <= end)]
    need = ["baseload", "tb2", "tb4", "gen_wind_onshore", "gen_wind_offshore", "gen_solar", "gen_total", "load_mean"]
    w = dm[dm["metric"].isin(need)].pivot_table(index=["zone", "day"], columns="metric", values="value", aggfunc="last")
    out = {}
    for key, days in AGG_WINDOWS.items():
        lo = end - pd.Timedelta(days=days - 1)
        sub = w[w.index.get_level_values("day") >= lo]
        for z, g in sub.groupby(level="zone"):
            e = out.setdefault(z, {})
            r = {}
            for m in ("baseload", "tb2", "tb4"):
                if m in g and g[m].notna().any():
                    r["price" if m == "baseload" else m] = round(float(g[m].mean()), 2)
                    r["n_" + ("price" if m == "baseload" else m)] = int(g[m].notna().sum())
            if "load_mean" in g:
                ld = g["load_mean"]
                def share(cols):
                    gg = g.reindex(columns=cols).sum(axis=1, min_count=1)
                    both = gg.notna() & ld.notna() & (ld > 0)
                    return (round(float(100 * gg[both].sum() / ld[both].sum()), 2), int(both.sum())) if both.any() else (None, 0)
                for name, cols in (("wind", ["gen_wind_onshore", "gen_wind_offshore"]), ("solar", ["gen_solar"]),
                                   ("vre", ["gen_wind_onshore", "gen_wind_offshore", "gen_solar"]), ("self", ["gen_total"])):
                    v, n = share(cols)
                    if v is not None:
                        r[name], r["n_" + name] = v, n
            if r:
                e[key] = r
    if not out:
        return None
    return {"schema": 1, "generated": now.isoformat(timespec="seconds"), "end_day": end.strftime("%Y-%m-%d"),
            "windows": AGG_WINDOWS, "zones": out,
            "note": "per zone and window: price = mean daily baseload (EUR/MWh), tb2 / tb4 = mean daily spread, wind / solar / vre / "
                    "self = % of load over the window (energy); n_* = days behind the number; from the metrics_daily store dataset"}


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
        if (d["currency"] == "GBP").any():  # GB (Elexon Market Index): shown in EUR at the ECB rate of the day, as the metrics are
            gb = d["currency"] == "GBP"
            r = M._gbp_rates(d.loc[gb, "ts"])
            ok = r.notna()
            d = d.copy()
            idx = r.index[ok]
            d.loc[idx, "price"] = d.loc[idx, "price"] / r[ok]
            d.loc[idx, "currency"] = "EUR"
            if (~ok).any():
                print(f"browse: no GBP/EUR rate for {int((~ok).sum())} GB price rows; those stay in GBP")
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
    # capacity proxy: the highest hourly output per class in the last 90 days (IRENA year-end capacity is too old)
    a90 = pd.Timestamp(now - timedelta(days=FU.PEAK_DAYS)).floor("D")
    g90 = [x[(x["dir"] == "gen") & x["psr"].isin(FU.PSR_CLS)] for x in
           (read(st, "gen_actual", [str(q) for q in pd.period_range(a90, b, freq="M")], a90, b),) if not x.empty]
    capx = capacity_export(g90[0] if g90 else None, now)
    del g90
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
              "l|national_demand": meta("l|national_demand", "Load, national demand (GB: transmission view)", G_LOAD, "", "MW"),
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
        # latest net flow per zone pair for the map's interconnection layer (browse/xflow.json): a < b, mw > 0 = a -> b
        try:
            hf = d.assign(h=d["ts"].dt.floor("h")).groupby(["from_zone", "to_zone", "h"])["mw"].mean()
            cut = pd.Timestamp(now) - pd.Timedelta(hours=48)
            pairs = []
            for za, zb in {tuple(sorted(k[:2])) for k in hf.index}:
                ab = hf.loc[(za, zb)] if (za, zb) in hf.index.droplevel(2) else pd.Series(dtype=float)
                ba = hf.loc[(zb, za)] if (zb, za) in hf.index.droplevel(2) else pd.Series(dtype=float)
                net = ab.sub(ba, fill_value=0)
                net = net[net.index >= cut]
                if net.empty:
                    continue
                pairs.append([za, zb, int(net.index[-1].timestamp()), round(float(net.iloc[-1]), 1),
                              [None if pd.isna(x) else round(float(x), 1) for x in net.iloc[-24:]]])
            (OUT / "xflow.json").write_text(json.dumps({"schema": 1, "generated": now.isoformat(timespec="seconds"),
                                                       "note": "net physical flow a->b (MW, hourly mean), latest hour and last 24 h; ENTSO-E A11 / Elexon",
                                                       "pairs": sorted(pairs)}, separators=(",", ":")))
        except Exception as e:  # the map layer is optional
            print(f"xflow export failed: {type(e).__name__}: {e}")

    avail = F.write()
    order = {g: i for i, g in enumerate(GROUPS)}
    dk = list(DAILY)  # registry order

    def vkey(m):
        i, g = m["id"], m["grp"]
        k = (0 if i == "p|price" else 1 + dk.index(i[2:])) if g in (G_PRICE, G_RES, G_SYS) else \
            (i.split("|")[1], i.endswith("cons")) if g == G_GEN else \
            (0 if i.endswith("actual") else 1) if g == G_LOAD else m["name"] if g == G_FLOW else i
        return (order[g], str(k) if not isinstance(k, int) else f"{k:03d}")

    vars_ = sorted(F.catalog.values(), key=vkey)
    index = {"generated": now.isoformat(timespec="seconds"), "window": [a.isoformat(), b.isoformat()], "step_s": 3600,
             "zones": sorted(avail), "groups": GROUPS, "vars": vars_, "avail": avail, "capacity": bool(capx)}
    (OUT / "index.json").write_text(json.dumps({"schema": 1, **index}, separators=(",", ":")))  # schema: docs/DATA_CONTRACT.md
    if capx:
        (OUT / "capacity.json").write_text(json.dumps({"schema": 1, **capx}, separators=(",", ":")))
    try:
        fls = flags_export(now)
        if fls:
            days = [f["day"] for f in fls]
            for f in fls:
                f["days"] = days
                f["schema"] = 1
                (OUT / "flags").mkdir(exist_ok=True)
                (OUT / "flags" / f"{f['day']}.json").write_text(json.dumps(f, separators=(",", ":")))
            (OUT / "flags.json").write_text(json.dumps(fls[0], separators=(",", ":")))
            (OUT / "flags" / "index.json").write_text(json.dumps({"schema": 1, "days": days, "keep_days": FLAG_DAYS}))
    except Exception as e:  # the flags tab is optional; the data browser must still ship
        print(f"flags export failed: {type(e).__name__}: {e}")
    try:
        agg = agg_export(st, now)
        if agg:
            (OUT / "agg.json").write_text(json.dumps(agg, separators=(",", ":")))
            print(f"browse: agg.json for {len(agg['zones'])} zones (windows {', '.join(AGG_WINDOWS)})")
    except Exception as e:  # the map's longer windows are optional
        print(f"agg export failed: {type(e).__name__}: {e}")
    n = sum(1 for _ in OUT.rglob("*.json"))
    size = sum(p.stat().st_size for p in OUT.rglob("*.json")) / 1e6
    print(f"browse: {n} files, {size:.1f} MB; {len(avail)} zones, {len(vars_)} variables, flags {'yes' if (OUT / 'flags.json').exists() else 'no'}")


if __name__ == "__main__":
    main()
