"""Great Britain and Ireland into the data store (zones "GB" and "IE(SEM)"), from open sources without keys.

    python -m collector.gbie daily      # last 4 days
    python -m collector.gbie backfill   # whole months from BACKFILL_FROM, newest first, resumable (gbie_state.json)

Sources and licences (credit on the page):
  Elexon BMRS Insights API  data.elexon.co.uk/bmrs/api/v1   "Contains BMRS data (c) Elexon Limited copyright and database right <year>."
      FUELHH   half-hourly generation by fuel (transmission-metered) and interconnector flows   -> gen_actual, flows
      B1630    wind and solar generation per type, incl. the embedded estimate                  -> gen_actual
      INDO     initial national demand outturn                                                  -> load
  EirGrid Smart Grid Dashboard  smartgriddashboard.com/DashboardService.svc   "Supported by EirGrid Group Data" (EirGrid open data licence)
      demandactual (all-island = the SEM zone)                                                 -> load of IE(SEM)
Not collected: the BMRS Market Index prices (N2EX / APX): exchange data that the BMRS open licence does not cover. GB has no
openly licensed day-ahead price series here; Ireland's day-ahead price already comes from ENTSO-E.

Store formats are those of collector/entsoe_raw.py (psr = ENTSO-E code, res_min = native resolution, mw, fetched).
GB load: kind "actual" = national demand + embedded wind and solar (so it is comparable with the other zones' total consumption);
kind "national_demand" = the raw INDO value (transmission view, embedded generation already netted off).
Flows: neighbours of GB (FR, NL, BE, NO2, DK1, IE(SEM)) as directed rows, import into GB positive; several links to one neighbour are summed.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from .store import Store

EL = "https://data.elexon.co.uk/bmrs/api/v1"
EIR = "https://www.smartgriddashboard.com/DashboardService.svc/data"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
BACKFILL_FROM = os.environ.get("BACKFILL_FROM", "2024-01")
BUDGET_S = int(os.environ.get("COLLECT_BUDGET_S", str(40 * 60)))

# FUELHH fuel -> ENTSO-E production type (WIND is left out: B1630 carries wind including the embedded estimate)
FUEL_PSR = {"BIOMASS": "B01", "CCGT": "B04", "OCGT": "B04", "COAL": "B05", "OIL": "B06", "PS": "B10", "NPSHYD": "B11",
            "NUCLEAR": "B14", "OTHER": "B20"}
# interconnector fuel code -> neighbouring zone (GB side is always "GB")
LINKS = {"INTFR": "FR", "INTELEC": "FR", "INTIFA2": "FR", "INTNED": "NL", "INTNEM": "BE", "INTNSL": "NO2", "INTVKL": "DK1",
         "INTEW": "IE(SEM)", "INTIRL": "IE(SEM)", "INTGRNL": "IE(SEM)"}
B1630_PSR = {"Solar": "B16", "Wind Onshore": "B19", "Wind Offshore": "B18"}


def log(msg: str) -> None:
    print(msg, flush=True)


def _get(url: str, params: dict, tries: int = 6, timeout: int = 90):
    """GET with retries (EirGrid answers 503 often). Returns the response or None after the last failure."""
    last = ""
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code} {r.text[:120]!r}"
            if r.status_code in (400, 404):  # not a transient failure
                break
        except requests.RequestException as e:
            last = f"{type(e).__name__}"
        time.sleep(min(60, 4 * (i + 1) ** 2))
    log(f"  gave up: {url.rsplit('/', 1)[-1]} {last} {params}")
    return None


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%MZ")


def _rows(r) -> list[dict]:
    if r is None:
        return []
    j = r.json()
    return j.get("data", j) if isinstance(j, dict) else j


def _windows(a: datetime, b: datetime, days: int):
    t = a
    while t < b:
        yield t, min(b, t + timedelta(days=days))
        t += timedelta(days=days)


# ------------------------------------------------------------------ Elexon
def fetch_fuelhh(a: datetime, b: datetime) -> pd.DataFrame:
    out = []
    for s, e in _windows(a, b, 2):
        out += _rows(_get(f"{EL}/datasets/FUELHH", {"publishDateTimeFrom": _iso(s), "publishDateTimeTo": _iso(e), "format": "json"}))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df.sort_values("publishTime").drop_duplicates(["ts", "fuelType"], keep="last")
    return df[(df["ts"] >= a) & (df["ts"] < b)][["ts", "fuelType", "generation"]]


def fetch_b1630(a: datetime, b: datetime) -> pd.DataFrame:
    out = []
    for s, e in _windows(a, b, 2):
        out += _rows(_get(f"{EL}/generation/actual/per-type/wind-and-solar", {"from": _iso(s), "to": _iso(e), "format": "json"}))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df.sort_values("publishTime").drop_duplicates(["ts", "psrType"], keep="last")
    return df[(df["ts"] >= a) & (df["ts"] < b)][["ts", "psrType", "quantity"]]


def fetch_indo(a: datetime, b: datetime) -> pd.DataFrame:
    out = []
    for s, e in _windows(a - timedelta(days=1), b + timedelta(days=1), 5):
        out += _rows(_get(f"{EL}/demand/outturn", {"settlementDateFrom": s.strftime("%Y-%m-%d"),
                                                   "settlementDateTo": e.strftime("%Y-%m-%d"), "format": "json"}))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df.sort_values("publishTime").drop_duplicates("ts", keep="last")
    return df[(df["ts"] >= a) & (df["ts"] < b)][["ts", "initialDemandOutturn"]]


def gb_frames(a: datetime, b: datetime, fetched: datetime) -> dict[str, pd.DataFrame]:
    fh, ws, nd = fetch_fuelhh(a, b), fetch_b1630(a, b), fetch_indo(a, b)
    gen, flows, load = [], [], []
    if not fh.empty:
        g = fh[fh["fuelType"].isin(FUEL_PSR)].copy()
        g["psr"] = g["fuelType"].map(FUEL_PSR)
        g = g.groupby(["ts", "psr"], as_index=False)["generation"].sum().rename(columns={"generation": "mw"})
        g["zone"], g["res_min"], g["dir"] = "GB", 30, "gen"
        gen.append(g)
        lk = fh[fh["fuelType"].isin(LINKS)].copy()
        lk["nb"] = lk["fuelType"].map(LINKS)
        lk = lk.groupby(["ts", "nb"], as_index=False)["generation"].sum()  # positive = import into GB
        imp = lk.assign(from_zone=lk["nb"], to_zone="GB", mw=lk["generation"].clip(lower=0))
        exp = lk.assign(from_zone="GB", to_zone=lk["nb"], mw=(-lk["generation"]).clip(lower=0))
        fl = pd.concat([imp, exp])[["from_zone", "to_zone", "ts", "mw"]]
        fl["res_min"] = 30
        flows.append(fl)
    if not ws.empty:
        w = ws.assign(psr=ws["psrType"].map(B1630_PSR)).dropna(subset=["psr"])
        w = w.rename(columns={"quantity": "mw"})[["ts", "psr", "mw"]]
        w["zone"], w["res_min"], w["dir"] = "GB", 30, "gen"
        gen.append(w)
    if not nd.empty:
        n = nd.rename(columns={"initialDemandOutturn": "mw"})
        n["zone"], n["res_min"], n["kind"] = "GB", 30, "national_demand"
        load.append(n)
        # total consumption estimate: national demand + embedded solar + embedded wind (B1630 wind minus transmission-metered wind)
        if not ws.empty and not fh.empty:
            sol = ws[ws["psrType"] == "Solar"].set_index("ts")["quantity"]
            wnd = ws[ws["psrType"].isin(["Wind Onshore", "Wind Offshore"])].groupby("ts")["quantity"].sum()
            twd = fh[fh["fuelType"] == "WIND"].set_index("ts")["generation"]
            t = pd.concat([nd.set_index("ts")["initialDemandOutturn"].rename("nd"), sol.rename("sol"), wnd.rename("wnd"), twd.rename("twd")],
                          axis=1).dropna()
            if not t.empty:
                act = (t["nd"] + t["sol"] + (t["wnd"] - t["twd"]).clip(lower=0)).rename("mw").reset_index()
                act["zone"], act["res_min"], act["kind"] = "GB", 30, "actual"
                load.append(act)
    cat = lambda xs: pd.concat(xs, ignore_index=True).assign(fetched=fetched) if xs else pd.DataFrame()
    return {"gen_actual": cat(gen), "flows": cat(flows), "load": cat(load)}


# ------------------------------------------------------------------ EirGrid (all-island demand = zone IE(SEM))
def fetch_eirgrid_demand(a: datetime, b: datetime, tz: str) -> pd.DataFrame:
    out = []
    for s, e in _windows(a, b, 7):
        r = _get(EIR, {"area": "demandactual", "region": "ALL", "datefrom": s.strftime("%d-%b-%Y %H:%M"), "dateto": e.strftime("%d-%b-%Y %H:%M")})
        if r is not None:
            out += [x for x in r.json().get("Rows", []) if x.get("FieldName") == "SYSTEM_DEMAND" and x.get("Value") is not None]
    df = pd.DataFrame(out)
    if df.empty:
        return df
    t = pd.to_datetime(df["EffectiveTime"], format="%d-%b-%Y %H:%M:%S")
    df["ts"] = (t.dt.tz_localize("UTC") if tz == "UTC" else t.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC"))
    df = df.dropna(subset=["ts"]).drop_duplicates("ts", keep="last")
    return df[(df["ts"] >= a) & (df["ts"] < b)][["ts", "Value"]].rename(columns={"Value": "mw"})


def eirgrid_tz(store: Store) -> str | None:
    """Are the dashboard's EffectiveTime stamps UTC or Irish local time? Correlate its wind with ENTSO-E's IE(SEM) wind (B19)."""
    b = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    a = b - timedelta(days=3)
    rows = []
    r = _get(EIR, {"area": "windactual", "region": "ALL", "datefrom": a.strftime("%d-%b-%Y %H:%M"), "dateto": b.strftime("%d-%b-%Y %H:%M")})
    if r is None:
        return None
    rows = [x for x in r.json().get("Rows", []) if x.get("Value") is not None]
    if not rows:
        return None
    t = pd.DataFrame(rows)
    t["t"] = pd.to_datetime(t["EffectiveTime"], format="%d-%b-%Y %H:%M:%S")
    ref = []
    for m in sorted({a.strftime("%Y-%m"), b.strftime("%Y-%m")}):
        g = store.read("gen_actual", m)
        if g is not None:
            ref.append(g[(g["zone"] == "IE(SEM)") & (g["psr"] == "B19")])
    if not ref:
        return None
    g = pd.concat(ref).set_index("ts")["mw"].sort_index()
    g = g[~g.index.duplicated(keep="last")]
    best, score = None, -2.0
    for tz in ("UTC", "Europe/Dublin"):
        ts = t["t"].dt.tz_localize("UTC") if tz == "UTC" else t["t"].dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        s = pd.Series(t["Value"].values, index=ts).dropna()
        s = s[~s.index.duplicated(keep="last")]
        j = pd.concat([s.rename("e"), g.rename("g")], axis=1).dropna()
        c = j["e"].corr(j["g"]) if len(j) > 20 else -2.0
        log(f"  EirGrid time zone {tz}: correlation of wind with ENTSO-E IE(SEM) B19 = {c:.3f} over {len(j)} points")
        if c > score:
            best, score = tz, c
    return best if score > 0.9 else None


def ie_frames(a: datetime, b: datetime, fetched: datetime, tz: str) -> dict[str, pd.DataFrame]:
    d = fetch_eirgrid_demand(a, b, tz)
    if d.empty:
        return {}
    d["zone"], d["res_min"], d["kind"], d["fetched"] = "IE(SEM)", 15, "actual", fetched
    return {"load": d}


# ------------------------------------------------------------------ runs
def write(store: Store, parts: dict[str, pd.DataFrame]) -> None:
    for ds, df in parts.items():
        if df is not None and not df.empty:
            df = df.copy()
            df["res_min"] = df["res_min"].astype("int16")
            store.write(ds, df, log=log)


def collect_window(store: Store, a: datetime, b: datetime, tz: str | None) -> None:
    fetched = datetime.now(timezone.utc)
    parts = gb_frames(a, b, fetched)
    if tz:
        ie = ie_frames(a, b, fetched, tz)
        if "load" in ie:  # both zones' load rows go in one write
            parts["load"] = pd.concat([parts["load"], ie["load"]], ignore_index=True) if not parts["load"].empty else ie["load"]
    log(f"window {a:%Y-%m-%d} .. {b:%Y-%m-%d}: " + ", ".join(f"{k} {len(v)}" for k, v in parts.items()))
    write(store, parts)


def daily(store: Store, tz: str | None) -> None:
    b = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    collect_window(store, b - timedelta(days=4), b, tz)


def backfill(store: Store, tz: str | None) -> None:
    t0 = time.time()
    st = store.read_json("gbie_state.json", {"done": []})
    done = set(st.get("done", []))
    now = datetime.now(timezone.utc)
    months = []
    m = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
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
        collect_window(store, m, min(nxt, now + timedelta(hours=1)), tz)
        if nxt <= now - timedelta(days=2):  # a finished month: never fetch again
            done.add(key)
            st["done"] = sorted(done)
            store.write_json("gbie_state.json", st)
    log(f"backfill: {len(done)} months done, {len(months) - len(done)} to go")


def main(argv=None) -> None:
    mode = (argv or sys.argv[1:] or ["daily"])[0]
    store = Store()
    tz = eirgrid_tz(store)
    log(f"EirGrid time stamps read as: {tz or 'unknown (Ireland load skipped)'}")
    {"daily": daily, "backfill": backfill}[mode](store, tz)
    log_name = "collector_log.json"
    lg = store.read_json(log_name, []) or []
    lg.append({"run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "mode": f"gbie-{mode}", "eirgrid_tz": tz})
    store.write_json(log_name, lg[-400:])


if __name__ == "__main__":
    main()
