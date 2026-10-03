"""Great Britain per-unit output, unit registry and plant sites, from open sources without keys.

    python -m collector.gbunits daily      # registry + REPD refresh, last 14 days of unit output
    python -m collector.gbunits backfill   # whole months from BACKFILL_FROM, newest first, resumable (gbunits_state.json)

Sources and licences (credit on the page):
  Elexon BMRS Insights API  data.elexon.co.uk/bmrs/api/v1   "Contains BMRS data (c) Elexon Limited copyright and database right <year>."
      B1610   metered output per BM unit and settlement period (MWh)       -> store dataset unit_output  (mw = MWh x 2)
      BM unit reference (name, lead party, fuel, capacity)                  -> release asset gb_units.json
  DESNZ Renewable Energy Planning Database (REPD), quarterly extract, Open Government Licence v3.0
      sites with technology, status, capacity, turbines, CfD round, coordinates   -> release asset gb_repd.json
      (British National Grid -> WGS84 with pyproj; BM units are matched to sites by name, score kept in gb_units.json)

Coverage: B1610 exists only for BM units: transmission-connected plants and the larger embedded ones (about 300 wind farms, the
big thermal and hydro stations, pumped storage and many batteries). Small embedded wind and solar are not in it; their
total is in the gen_actual (B1630) series. B1610 is published about 4-5 days after the day (settlement run II) and revised by
later runs (SF, R1, R2 ...): the newest fetch of a half hour wins in the store, so the daily job re-reads 14 days.
Units: unit_output.mw is the average MW of the half hour, signed (negative = import, e.g. battery charging, pumping).
"""
from __future__ import annotations

import difflib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from .gbie import EL, UA, _get, _iso, _rows, _windows, log
from .store import Store

BACKFILL_FROM = os.environ.get("BACKFILL_FROM", "2024-01")
BUDGET_S = int(os.environ.get("COLLECT_BUDGET_S", str(40 * 60)))
CHUNK = 25          # BM units per request
WINDOW_DAYS = 10    # days per request
REPD_PAGE = "https://www.gov.uk/api/content/government/publications/renewable-energy-planning-database-quarterly-extract"
REPD_HTML = "https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract"
REPD_KEEP = {"Operational", "Under Construction", "Awaiting Construction", "Decommissioned"}

# registry fuel -> REPD technologies it can be matched with (thermal and nuclear plants are not in the REPD)
FUEL_REPD = {
    "WIND": {"Wind Onshore", "Wind Offshore"},
    "PS": {"Pumped Storage Hydroelectricity"},
    "NPSHYD": {"Small Hydro", "Large Hydro"},
    "BIOMASS": {"Biomass (dedicated)", "Biomass (co-firing)", "EfW Incineration", "Anaerobic Digestion", "Landfill Gas",
                "Advanced Conversion Technologies", "Sewage Sludge Digestion"},
    "OTHER": {"Battery", "Liquid Air Energy Storage", "Compressed Air Energy Storage", "Solar Photovoltaics", "Hydrogen"},
    None: {"Battery", "Liquid Air Energy Storage", "Compressed Air Energy Storage", "Solar Photovoltaics", "Hydrogen"},
}
# words that carry no identity in BM-unit or REPD names (removed before comparing)
STOP = {"wind", "windfarm", "farm", "farms", "wf", "bmu", "offshore", "onshore", "power", "station", "stations", "ltd", "limited",
        "plc", "energy", "generation", "generating", "generator", "renewables", "renewable", "uk", "the", "of", "and", "project",
        "company", "holdings", "scheme", "gb", "owf", "was", "extension", "phase", "battery", "storage", "bess"}
NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "i": "1", "ii": "2", "iii": "3", "iv": "4"}
OVERRIDES = Path(__file__).resolve().parents[1] / "data" / "gb_unit_overrides.json"  # {bm_unit: repd_ref}, hand-checked


# ------------------------------------------------------------------ registry
def fetch_registry() -> pd.DataFrame:
    rows = _rows(_get(f"{EL}/reference/bmunits/all", {}, timeout=120))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    num = lambda c: pd.to_numeric(df.get(c), errors="coerce")
    out = pd.DataFrame({
        "bm_unit": df["elexonBmUnit"], "ngc_id": df.get("nationalGridBmUnit"), "name": df.get("bmUnitName"),
        "party": df.get("leadPartyName"), "fuel": df.get("fuelType"), "unit_type": df.get("bmUnitType"),
        "capacity_mw": num("generationCapacity"), "gsp_group": df.get("gspGroupId"), "eic": df.get("eic"),
    })
    return out.drop_duplicates("bm_unit").reset_index(drop=True)


def select_units(reg: pd.DataFrame) -> pd.DataFrame:
    """Generating and storage units worth collecting: any with a fuel type (interconnectors excluded: their flows are in
    `flows`), plus transmission / embedded / miscellaneous units of 5 MW and more without one (mostly batteries)."""
    fuel = reg["fuel"]
    gen = fuel.notna() & ~fuel.fillna("").str.startswith("INT")
    other = fuel.isna() & reg["unit_type"].isin(["T", "E", "M"]) & (reg["capacity_mw"].fillna(0) >= 5)
    return reg[gen | other].reset_index(drop=True)


# ------------------------------------------------------------------ REPD
def _repd_csv_url() -> str | None:
    r = _get(REPD_PAGE, {})
    urls = re.findall(r'https://assets\.publishing\.service\.gov\.uk/[^"\\ ]+\.csv', json.dumps(r.json())) if r is not None else []
    if not urls:
        r = _get(REPD_HTML, {})
        urls = re.findall(r'https://assets\.publishing\.service\.gov\.uk/[^"\' ]+\.csv', r.text) if r is not None else []
    return urls[0] if urls else None


def parse_repd(text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    col = lambda *names: next((raw[n] for n in names if n in raw), pd.Series([""] * len(raw)))
    num = lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")
    df = pd.DataFrame({
        "ref": col("Ref ID"), "name": col("Site Name"), "operator": col("Operator (or Applicant)"),
        "tech": col("Technology Type"), "storage_type": col("Storage Type"),
        "mw": num(col("Installed Capacity (MWelec)")), "status": col("Development Status (short)"),
        "country": col("Country"), "region": col("Region"), "turbines": num(col("No. of Turbines")),
        "turbine_mw": num(col("Turbine Capacity (MW)")), "cfd_round": col("CfD Allocation Round"),
        "offshore_round": col("Offshore Wind Round"), "x": num(col("X-coordinate")), "y": num(col("Y-coordinate")),
    })
    df = df[df["status"].isin(REPD_KEEP)].reset_index(drop=True)
    ok = df["x"].notna() & df["y"].notna() & (df["x"] > 0)
    df["lat"], df["lon"] = float("nan"), float("nan")
    if ok.any():
        from pyproj import Transformer  # British National Grid -> WGS84
        lon, lat = Transformer.from_crs(27700, 4326, always_xy=True).transform(df.loc[ok, "x"].values, df.loc[ok, "y"].values)
        df.loc[ok, "lon"], df.loc[ok, "lat"] = lon.round(5), lat.round(5)
    return df.drop(columns=["x", "y"])


def fetch_repd() -> pd.DataFrame:
    url = _repd_csv_url()
    if not url:
        log("REPD: csv link not found")
        return pd.DataFrame()
    r = _get(url, {}, timeout=180)
    if r is None:
        return pd.DataFrame()
    log(f"REPD: {url.rsplit('/', 1)[-1]}")
    return parse_repd(r.content.decode("utf-8-sig", errors="replace"))


# ------------------------------------------------------------------ matching BM units to REPD sites
def _compact(s) -> str:
    """Name without generic words, number words as digits, no spaces: 'Dogger Bank A Offshore WF 1' -> 'doggerbanka1'."""
    toks = re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\(.*?\)", " ", str(s or "").lower()).replace("-", " ").replace("_", " ")).split()
    return "".join(NUMBER_WORDS.get(t, t) for t in toks if t not in STOP)


def _trigrams(c: str) -> set:
    return {c[i:i + 3] for i in range(len(c) - 2)}


def _score(a: str, b: str) -> float:
    """Similarity of two compact names; differing numbers (Hornsea 1 vs Hornsea 3) cost 20 %."""
    sc = difflib.SequenceMatcher(None, a, b).ratio()
    da, db = set(re.findall(r"\d+", a)), set(re.findall(r"\d+", b))
    return sc * 0.8 if da and db and not (da & db) else sc


def match_units(units: pd.DataFrame, repd: pd.DataFrame, min_score: float = 0.82, overrides: dict | None = None) -> pd.DataFrame:
    """Adds repd_ref / repd_site / repd_tech / lat / lon / match_score to the units.

    Score = SequenceMatcher ratio of the compact names (unit name or lead party vs REPD site name, generic words removed) among
    sites of a compatible technology. A site's matched units must have a total capacity within a factor 2 of the REPD
    capacity, else the matches are dropped (unless the name is near-identical). `overrides` ({bm_unit: repd_ref}) wins."""
    out = units.copy()
    for c in ("repd_ref", "repd_site", "repd_tech"):
        out[c] = None
    for c in ("lat", "lon", "match_score"):
        out[c] = float("nan")
    if repd.empty:
        return out
    comp = {i: _compact(n) for i, n in zip(repd.index, repd["name"])}
    grams: dict[str, set] = {}
    for i, c in comp.items():
        for g in _trigrams(c):
            grams.setdefault(g, set()).add(i)
    by_ref = {str(r): i for i, r in zip(repd.index, repd["ref"])}
    pick = {}
    for j, u in out.iterrows():
        fuel = u["fuel"] if isinstance(u["fuel"], str) else None
        techs = FUEL_REPD.get(fuel)
        if not techs:
            continue
        best = (0.0, None)
        for field in (u["name"], u["party"]):
            cu = _compact(field)
            if len(cu) < 4:
                continue
            cand = set().union(*(grams.get(g, set()) for g in _trigrams(cu)))
            for i in cand:
                if repd.at[i, "tech"] not in techs or len(comp[i]) < 4:
                    continue
                sc = _score(cu, comp[i])
                if sc > best[0]:
                    best = (sc, i)
        if best[1] is not None and best[0] >= min_score:
            pick[j] = best
    # capacity sanity per site
    cap = out["capacity_mw"].fillna(0)
    for i in {b[1] for b in pick.values()}:
        js = [j for j, b in pick.items() if b[1] == i]
        site_mw = repd.at[i, "mw"]
        tot = float(cap[js].sum())
        if site_mw and tot and not (0.5 <= tot / site_mw <= 2.0) and max(pick[j][0] for j in js) < 0.95:
            for j in js:
                del pick[j]
    for j, (sc, i) in pick.items():
        out.loc[j, ["repd_ref", "repd_site", "repd_tech"]] = [repd.at[i, "ref"], repd.at[i, "name"], repd.at[i, "tech"]]
        out.loc[j, ["lat", "lon", "match_score"]] = [repd.at[i, "lat"], repd.at[i, "lon"], round(sc, 3)]
    for bm, ref in (overrides or {}).items():  # hand-checked links; "" = checked, no site (an automatic match was wrong)
        i, j = by_ref.get(str(ref)), out.index[out["bm_unit"] == bm]
        if not ref and len(j):
            out.loc[j[0], ["repd_ref", "repd_site", "repd_tech"]] = [None, None, None]
            out.loc[j[0], ["lat", "lon", "match_score"]] = [float("nan")] * 3
        elif i is not None and len(j):
            out.loc[j[0], ["repd_ref", "repd_site", "repd_tech"]] = [repd.at[i, "ref"], repd.at[i, "name"], repd.at[i, "tech"]]
            out.loc[j[0], ["lat", "lon", "match_score"]] = [repd.at[i, "lat"], repd.at[i, "lon"], 1.0]
    return out


def load_overrides() -> dict:
    try:
        return {k: v for k, v in json.loads(OVERRIDES.read_text()).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def refresh_reference(store: Store) -> pd.DataFrame:
    """Rebuild gb_units.json and gb_repd.json; returns the selected units (matched). Falls back to the stored copy."""
    reg = fetch_registry()
    if reg.empty:
        old = store.read_json("gb_units.json", {})
        log("registry unavailable; using the stored copy")
        return pd.DataFrame(old.get("units", []))
    units = select_units(reg)
    repd = fetch_repd()
    if repd.empty:
        old = {u["bm_unit"]: u for u in (store.read_json("gb_units.json", {}) or {}).get("units", [])}
        units = match_units(units, pd.DataFrame())
        for c in ("repd_ref", "repd_site", "repd_tech", "lat", "lon", "match_score"):  # keep earlier matches
            units[c] = [old.get(b, {}).get(c, units.at[i, c]) for i, b in zip(units.index, units["bm_unit"])]
    else:
        units = match_units(units, repd, overrides=load_overrides())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    clean = lambda df: json.loads(df.astype(object).where(df.notna(), None).to_json(orient="records"))
    store.write_json("gb_units.json", {"generated": now, "n_registry": int(len(reg)), "units": clean(units)})
    if not repd.empty:
        store.write_json("gb_repd.json", {"generated": now, "sites": clean(repd)})
    m = units["lat"].notna()
    for fuel in ("WIND", "PS", "NPSHYD", "BIOMASS"):
        s = units[units["fuel"] == fuel]
        if len(s):
            log(f"  {fuel}: {len(s)} units, {s['lat'].notna().sum()} placed, {s.loc[s['lat'].notna(), 'capacity_mw'].sum() / max(s['capacity_mw'].sum(), 1):.0%} of capacity")
    log(f"reference: {len(units)} units selected of {len(reg)}; {int(m.sum())} placed on a REPD site; REPD sites {len(repd)}")
    return units


# ------------------------------------------------------------------ B1610 per-unit output
def fetch_b1610(units: list[str], a: datetime, b: datetime) -> pd.DataFrame:
    rows = []
    for s, e in _windows(a, b, WINDOW_DAYS):
        for i in range(0, len(units), CHUNK):
            rows += _rows(_get(f"{EL}/datasets/B1610/stream", {"from": _iso(s), "to": _iso(e), "bmUnit": units[i:i + CHUNK]}, timeout=180))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.dropna(subset=["quantity"])
    # halfHourEndTime is UTC (naive); the half hour starts 30 min earlier
    df["ts"] = pd.to_datetime(df["halfHourEndTime"], utc=True) - pd.Timedelta(minutes=30)
    df = df[(df["ts"] >= a) & (df["ts"] < b)]
    df["mw"] = df["quantity"].astype(float) * 2.0
    return df.rename(columns={"settlementRunType": "run"})[["bmUnit", "ts", "mw", "run"]].rename(columns={"bmUnit": "bm_unit"})


def unit_frame(units: list[str], a: datetime, b: datetime, fetched: datetime) -> pd.DataFrame:
    df = fetch_b1610(units, a, b)
    if df.empty:
        return df
    df["res_min"] = 30
    df["fetched"] = fetched
    return df


def write(store: Store, df: pd.DataFrame) -> None:
    if df is not None and not df.empty:
        df = df.copy()
        df["res_min"] = df["res_min"].astype("int16")
        store.write("unit_output", df, log=log)


def collect_window(store: Store, units: list[str], a: datetime, b: datetime) -> None:
    df = unit_frame(units, a, b, datetime.now(timezone.utc))
    log(f"window {a:%Y-%m-%d} .. {b:%Y-%m-%d}: unit_output {len(df)} rows, {df['bm_unit'].nunique() if len(df) else 0} units")
    write(store, df)


def daily(store: Store) -> None:
    units = refresh_reference(store)
    ids = list(units["bm_unit"]) if len(units) else []
    if not ids:
        log("no units; nothing to collect")
        return
    b = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    collect_window(store, ids, b - timedelta(days=15), b)


def backfill(store: Store) -> None:
    t0 = time.time()
    ref = store.read_json("gb_units.json", None)
    units = pd.DataFrame(ref["units"]) if ref else refresh_reference(store)
    ids = list(units["bm_unit"]) if len(units) else []
    if not ids:
        log("no units; nothing to backfill")
        return
    st = store.read_json("gbunits_state.json", {"done": []})
    done = set(st.get("done", []))
    now = datetime.now(timezone.utc)
    months, m = [], datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    while m.strftime("%Y-%m") >= BACKFILL_FROM:
        months.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    for m in months:
        key = m.strftime("%Y-%m")
        if key in done:
            continue
        if time.time() - t0 > BUDGET_S:
            log("time budget used up; the next run continues")
            break
        nxt = (m + timedelta(days=32)).replace(day=1)
        collect_window(store, ids, m, min(nxt, now + timedelta(days=1)))
        if nxt <= now - timedelta(days=45):  # settlement runs have caught up: never fetch again
            done.add(key)
            st["done"] = sorted(done)
            store.write_json("gbunits_state.json", st)
    log(f"backfill: {len(done)} months done, {len(months) - len(done)} to go")


def main(argv=None) -> None:
    mode = (argv or sys.argv[1:] or ["daily"])[0]
    store = Store()
    {"daily": daily, "backfill": backfill}[mode](store)
    lg = store.read_json("collector_log.json", []) or []
    lg.append({"run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "mode": f"gbunits-{mode}"})
    store.write_json("collector_log.json", lg[-400:])


if __name__ == "__main__":
    main()
