"""Export the last ~30 days of the data store as small JSON files for the site's Data tab (web/data/browse/).

    web/data/browse/index.json                    {generated, window, datasets: {name: {label, unit, zones: [...]}}}
    web/data/browse/<dataset>/<zone>.json         {t0: first hour (unix s), step: 3600, cols: [{id, name, tech, unit}], v: [[...] per col]}

Hourly means of the native-resolution rows (the store keeps 15/30/60-minute data untouched), UTC hour starts, one file
per zone and dataset so the page loads only what is opened. Not committed: the deploy job builds it from the `store`
release (hourly.yml). ENTSO-E data plus capacity.json (IRENA installed capacity from data/ref, capacity factor from the store; credited on the page). STORE_DIR=<folder> reads a local copy.
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
from pipeline.entsoe import PSR  # noqa: E402

OUT = ROOT / "web" / "data" / "browse"
DAYS_BACK, DAYS_FWD = 30, 2
TECH_KEY = {"nuclear": "nuc", "fossil_brown_coal_lignite": "coal", "fossil_hard_coal": "coal", "fossil_coal_derived_gas": "coal",
            "fossil_gas": "gas", "fossil_oil": "oil", "wind_onshore": "won", "wind_offshore": "woff", "solar": "sol",
            "hydro_run_of_river": "hyd", "hydro_water_reservoir": "hyd", "hydro_pumped_storage": "hyd",
            "biomass": "bio", "waste": "bio"}
LABELS = {"da_price": ("Day-ahead price", "EUR/MWh"), "gen_actual": ("Actual generation", "MW"),
          "gen_forecast": ("Wind & solar day-ahead forecast", "MW"), "load": ("Load", "MW"),
          "flows": ("Cross-border physical flows", "MW"), "capacity": ("Installed capacity & capacity factor", "GW")}


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


def write_zone(ds: str, zone: str, w: pd.DataFrame, meta: dict, a, b) -> None:
    idx = pd.date_range(a.floor("h"), b.floor("h"), freq="h", inclusive="left")
    w = w.reindex(idx).dropna(axis=1, how="all")
    if w.empty:
        return
    cols = [meta[c] for c in w.columns]
    v = [[None if pd.isna(x) else round(float(x), 2) for x in w[c]] for c in w.columns]
    p = OUT / ds / f"{zone}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"t0": int(idx[0].timestamp()), "step": 3600, "cols": cols, "v": v}, separators=(",", ":")))


CAP_CLS = [("solar", "Solar"), ("wind_onshore", "Onshore wind"), ("wind_offshore", "Offshore wind"), ("hydro", "Hydro (excl. pumped)"),
           ("pumped", "Pumped storage"), ("nuclear", "Nuclear"), ("fossil", "Fossil"), ("bio", "Bio & waste"), ("other", "Other")]


def capacity_export(ga: pd.DataFrame, now: datetime) -> dict | None:
    """Installed capacity per zone and class (IRENA, data/ref) and the 30-day capacity factor from the store's generation."""
    cap = FU.capacity()
    if cap.empty:
        return None
    cap = cap.assign(cls=cap["cls"].where(~cap["cls"].isin(["geothermal"]), "other"))
    cap = cap.groupby(["zone", "cls", "year"], as_index=False)["cap_mw"].sum()
    end = pd.Timestamp(now).floor("D")
    start = end - pd.Timedelta(days=30)
    cf = FU.capacity_factors(ga, start, end, FU.capacity()) if ga is not None and not ga.empty else pd.DataFrame()
    out = {"classes": [{"id": k, "name": n} for k, n in CAP_CLS], "gw": {}, "cf": {}, "year": {},
           "cf_window": [start.strftime("%Y-%m-%d"), (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]}
    for r in cap.itertuples():
        out["gw"].setdefault(r.zone, {})[r.cls] = round(r.cap_mw / 1000, 3)
        out["year"][r.zone] = int(r.year)
    for r in (cf.itertuples() if not cf.empty else []):
        v = FU.plausible_cf(r.cls, r.cf)
        if v is not None:
            out["cf"].setdefault(r.zone, {})[r.cls] = round(100 * v, 1)
    return out


def main() -> None:
    now = datetime.now(timezone.utc)
    a = pd.Timestamp(now - timedelta(days=DAYS_BACK)).floor("D")
    b = pd.Timestamp(now + timedelta(days=DAYS_FWD)).floor("D")
    months = [str(p) for p in pd.period_range(a, b, freq="M")]
    st = Store()
    shutil.rmtree(OUT, ignore_errors=True)
    zones: dict[str, set] = {k: set() for k in LABELS}

    def emit(ds, frames, meta):
        for z, w in frames.items():
            write_zone(ds, z, w, meta, a, b)
            if (OUT / ds / f"{z}.json").exists():
                zones[ds].add(z)

    d = read(st, "da_price", months, a, b)
    if not d.empty:
        d = d[d["seq"] == 1]
        for cur, g in d.groupby("currency"):
            emit("da_price", hourly(g, lambda x: "price", "price"),
                 {"price": {"id": "price", "name": "Day-ahead price", "tech": "", "unit": f"{cur}/MWh"}})
    d = read(st, "gen_actual", months, a, b)
    capx = capacity_export(d, now)
    if not d.empty:
        meta = {}
        for psr, (key, name) in PSR.items():
            meta[f"{psr}|gen"] = {"id": f"{psr}|gen", "name": name, "tech": TECH_KEY.get(key, ""), "unit": "MW"}
            meta[f"{psr}|cons"] = {"id": f"{psr}|cons", "name": name + " (consumption)", "tech": "", "unit": "MW"}
        emit("gen_actual", hourly(d, lambda x: x["psr"] + "|" + x["dir"], "mw"), {k: v for k, v in meta.items()})
    d = read(st, "gen_forecast", months, a, b)
    if not d.empty:
        meta = {p: {"id": p, "name": PSR.get(p, (p, p))[1] + " forecast", "tech": TECH_KEY.get(PSR.get(p, ("", ""))[0], ""),
                    "unit": "MW"} for p in d["psr"].unique()}
        emit("gen_forecast", hourly(d, lambda x: x["psr"], "mw"), meta)
    d = read(st, "load", months, a, b)
    if not d.empty:
        meta = {"actual": {"id": "actual", "name": "Load, actual", "tech": "", "unit": "MW"},
                "da_forecast": {"id": "da_forecast", "name": "Load, day-ahead forecast", "tech": "", "unit": "MW"}}
        emit("load", hourly(d, lambda x: x["kind"], "mw"), meta)
    d = read(st, "flows", months, a, b)
    if not d.empty:
        out = d.rename(columns={"from_zone": "zone", "to_zone": "other"}).assign(col=lambda x: "out|" + x["other"])
        inn = d.rename(columns={"to_zone": "zone", "from_zone": "other"}).assign(col=lambda x: "in|" + x["other"])
        both = pd.concat([out, inn], ignore_index=True)
        both["h"] = both["ts"].dt.floor("h")
        wide = both.groupby(["zone", "h", "col"])["mw"].mean().unstack("col")
        meta = {c: {"id": c, "name": ("Export to " if c.startswith("out") else "Import from ") + c.split("|")[1],
                    "tech": "", "unit": "MW"} for c in wide.columns}
        emit("flows", {z: g.droplevel("zone") for z, g in wide.groupby(level="zone")}, meta)

    if capx:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "capacity.json").write_text(json.dumps(capx, separators=(",", ":")))
        zones["capacity"] = set(capx["gw"])
    index = {"generated": now.isoformat(timespec="seconds"),
             "window": [a.isoformat(), b.isoformat()], "step_s": 3600,
             "datasets": {k: {"label": LABELS[k][0], "unit": LABELS[k][1], "zones": sorted(v)} for k, v in zones.items() if v}}
    if "capacity" in index["datasets"]:
        index["datasets"]["capacity"]["static"] = True
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    n = sum(1 for _ in OUT.rglob("*.json"))
    size = sum(p.stat().st_size for p in OUT.rglob("*.json")) / 1e6
    print(f"browse: {n} files, {size:.1f} MB; " + ", ".join(f"{k} {len(v)} zones" for k, v in zones.items()))


if __name__ == "__main__":
    main()
