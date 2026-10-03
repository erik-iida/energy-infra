"""Great Britain long history (back to 2009) and day-ahead forecasts into the data store, from NESO and Elexon open data.

    python -m collector.gbhist daily      # last 14 days of history, today's forecasts
    python -m collector.gbhist backfill   # NESO history 2009 -> now (once), NESO day-ahead wind forecast archive (once)

Sources and licences (credit on the page):
  NESO Data Portal  api.neso.energy   NESO Open Data Licence: "Supported by National Energy SO Open Data"
      Historic generation mix and carbon intensity (half-hourly since 2009)        -> gb_hist
      Historic demand data (ND, TSD, embedded wind and solar, interconnector flows, pumping)  -> gb_hist
      Day-ahead wind forecast (+ archive since 2018), embedded wind and solar forecast  -> gb_forecast
  Elexon BMRS Insights API  "Contains BMRS data (c) Elexon Limited copyright and database right <year>."
      day-ahead national demand forecast, day-ahead wind and solar forecast           -> gb_forecast

gb_hist: one wide row per half hour (zone GB, ts = start of the half hour in UTC, res_min 30). Columns: the NESO mix in MW
(gas, coal, nuclear, wind [transmission-metered], wind_emb [embedded estimate], hydro, imports, biomass, other, solar, storage,
generation) and carbon_intensity (gCO2/kWh, NESO's calculation), then the demand file's columns in lower case (nd, tsd,
embedded_wind_generation ... greenlink_flow; flows in MW, positive = import into GB).
gb_forecast: long format, key (series, issued, ts): `issued` = when the forecast was made, `ts` = the half hour it is for.
"""
from __future__ import annotations

import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from .gbie import EL, UA, _get, _iso, _rows, log
from .store import Store

CKAN = "https://api.neso.energy/api/3/action/package_show"
FIRST_YEAR = int(os.environ.get("GBHIST_FROM_YEAR", "2009"))
ELEXON_SERIES = {"solar": "da_solar", "wind onshore": "da_wind_onshore", "wind offshore": "da_wind_offshore", "wind": "da_wind"}


# ------------------------------------------------------------------ NESO plumbing
def neso_resources(package: str) -> list[dict]:
    r = _get(CKAN, {"id": package})
    return r.json()["result"]["resources"] if r is not None else []


def neso_csv(url: str, **read_kw) -> pd.DataFrame:
    r = _get(url, {}, timeout=300)
    if r is None:
        return pd.DataFrame()
    return pd.read_csv(io.BytesIO(r.content), **read_kw)


def london_to_utc(date: pd.Series, period: pd.Series) -> pd.Series:
    """Settlement date + period (1-based half hours from local midnight, 46/50 on clock change days) -> UTC start time."""
    d = pd.to_datetime(date).dt.tz_localize("Europe/London").dt.tz_convert("UTC")
    return d + pd.to_timedelta((period.astype(int) - 1) * 30, unit="m")


# ------------------------------------------------------------------ history: mix + demand
def parse_mix(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df["ts"] = pd.to_datetime(df["datetime"], utc=True)
    keep = [c for c in df.columns if c != "datetime" and not c.endswith("_perc") and c not in ("_id", "ts")
            and c not in ("low_carbon", "zero_carbon", "renewable", "fossil")]  # derived shares, recomputable
    out = df[["ts"] + keep].copy()
    for c in keep:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.drop_duplicates("ts", keep="last")


def parse_demand(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    if "forecast_actual_indicator" in df:  # the update file also holds forecasts for the coming days
        df = df[df["forecast_actual_indicator"] == "A"]
    df = df.dropna(subset=["settlement_date", "settlement_period"])
    df["ts"] = london_to_utc(df["settlement_date"], df["settlement_period"])
    drop = {"settlement_date", "settlement_period", "forecast_actual_indicator", "_id", "ts"}
    cols = [c for c in df.columns if c not in drop]
    out = df[["ts"] + cols].copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.drop_duplicates("ts", keep="last")


def hist_frame(a: datetime | None, fetched: datetime) -> pd.DataFrame:
    """NESO mix + demand from `a` (None = everything), merged on the half hour."""
    mix = pd.DataFrame()
    res = [x for x in neso_resources("historic-generation-mix") if str(x.get("format", "")).upper() == "CSV"]
    if res:
        mix = parse_mix(neso_csv(res[0]["url"]))
    dem = []
    for x in neso_resources("historic-demand-data"):
        m = re.search(r"Historic Demand Data (\d{4})", x.get("name", ""))
        if not m or str(x.get("format", "")).upper() != "CSV":
            continue
        y = int(m.group(1))
        if y < FIRST_YEAR or (a is not None and y < a.year):
            continue
        d = neso_csv(x["url"])
        if not d.empty:
            dem.append(parse_demand(d))
    demand = pd.concat(dem, ignore_index=True).drop_duplicates("ts", keep="last") if dem else pd.DataFrame()
    if mix.empty and demand.empty:
        return pd.DataFrame()
    df = mix if demand.empty else demand if mix.empty else mix.merge(demand, on="ts", how="outer", suffixes=("", "_dem"))
    if a is not None:
        df = df[df["ts"] >= a]
    df = df.sort_values("ts")
    df["zone"], df["res_min"], df["fetched"] = "GB", 30, fetched
    return df.reset_index(drop=True)


# ------------------------------------------------------------------ forecasts
def _fc(series: str, issued, ts, mw, fetched) -> pd.DataFrame:
    df = pd.DataFrame({"series": series, "issued": pd.to_datetime(issued, utc=True), "ts": pd.to_datetime(ts, utc=True),
                       "mw": pd.to_numeric(mw, errors="coerce")})
    df["res_min"], df["fetched"] = 30, fetched
    return df.dropna(subset=["mw", "issued", "ts"])


def neso_wind_da(fetched: datetime, archive: bool) -> pd.DataFrame:
    """NESO day-ahead wind forecast (Capacity = forecast MW, Incentive_forecast = the forecast used for the wind incentive)."""
    out = []
    for x in neso_resources("day-ahead-wind-forecast"):
        name = x.get("name", "")
        want = name == "Historic Day Ahead Wind Forecasts" if archive else name == "Day Ahead Wind Forecast"
        if not want or str(x.get("format", "")).upper() != "CSV":
            continue
        d = neso_csv(x["url"])
        if d.empty:
            continue
        issued = d["Forecast_Timestamp"] if "Forecast_Timestamp" in d else pd.Timestamp.now(tz="UTC").floor("min")
        out.append(_fc("wind_da", issued, d["Datetime_GMT"], d["Capacity"], fetched))
        out.append(_fc("wind_da_incentive", issued, d["Datetime_GMT"], d["Incentive_forecast"], fetched))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def neso_embedded(fetched: datetime) -> pd.DataFrame:
    out = []
    for x in neso_resources("embedded-wind-and-solar-forecasts"):
        if x.get("name") != "Embedded Solar and Wind Forecast":
            continue
        d = neso_csv(x["url"])
        if d.empty:
            continue
        ts = london_to_utc(d["SETTLEMENT_DATE"].astype(str).str[:10], d["SETTLEMENT_PERIOD"])
        issued = fetched.replace(second=0, microsecond=0)  # the file carries no issue time; the vintage is the fetch
        out.append(_fc("embedded_wind", issued, ts, d["EMBEDDED_WIND_FORECAST"], fetched))
        out.append(_fc("embedded_solar", issued, ts, d["EMBEDDED_SOLAR_FORECAST"], fetched))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def elexon_forecasts(a: datetime, b: datetime, fetched: datetime) -> pd.DataFrame:
    out = []
    r = _get(f"{EL}/forecast/demand/day-ahead", {"format": "json"})
    d = pd.DataFrame(_rows(r))
    if not d.empty:
        d = d[d.get("boundary", "N") == "N"] if "boundary" in d else d
        out.append(_fc("da_national_demand", d["publishTime"], d["startTime"], d["nationalDemand"], fetched))
        out.append(_fc("da_transmission_demand", d["publishTime"], d["startTime"], d["transmissionSystemDemand"], fetched))
    r = _get(f"{EL}/forecast/generation/wind-and-solar/day-ahead", {"from": _iso(a), "to": _iso(b), "processType": "Day Ahead", "format": "json"})
    w = pd.DataFrame(_rows(r))
    if not w.empty:
        for psr, part in w.groupby(w["psrType"].str.lower()):
            out.append(_fc(ELEXON_SERIES.get(psr, "da_" + re.sub(r"\W+", "_", psr)), part["publishTime"], part["startTime"], part["quantity"], fetched))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ------------------------------------------------------------------ writing
def write(store: Store, dataset: str, df: pd.DataFrame) -> None:
    if df is not None and not df.empty:
        df = df.copy()
        df["res_min"] = df["res_min"].astype("int16")
        store.write(dataset, df, log=log)


def daily(store: Store) -> None:
    fetched = datetime.now(timezone.utc)
    now = fetched.replace(minute=0, second=0, microsecond=0)
    h = hist_frame(now - timedelta(days=14), fetched)
    log(f"gb_hist: {len(h)} rows since {now - timedelta(days=14):%Y-%m-%d}")
    write(store, "gb_hist", h)
    f = pd.concat([x for x in (neso_wind_da(fetched, False), neso_embedded(fetched),
                               elexon_forecasts(now - timedelta(days=1), now + timedelta(days=3), fetched)) if not x.empty] or [pd.DataFrame()],
                  ignore_index=True)
    log(f"gb_forecast: {len(f)} rows, series {sorted(f['series'].unique()) if len(f) else []}")
    write(store, "gb_forecast", f)


MAX_MONTHS = int(os.environ.get("GBHIST_MAX_MONTHS", "60"))  # months written per run (each write costs several GitHub API calls)


def backfill(store: Store) -> None:
    st = store.read_json("gbhist_state.json", {}) or {}
    fetched = datetime.now(timezone.utc)
    if not st.get("hist"):
        h = hist_frame(None, fetched)
        if len(h):
            log(f"gb_hist full history: {len(h)} rows {h['ts'].min()} .. {h['ts'].max()}")
            have = {n[len("gb_hist_"):-len(".parquet")] for n in store.assets() if n.startswith("gb_hist_")}
            months = h["ts"].dt.strftime("%Y-%m")
            missing = sorted(set(months) - have, reverse=True)  # newest first; months already in the store are kept as they are
            todo = missing[:MAX_MONTHS]
            log(f"gb_hist: {len(missing)} months missing in the store, writing {len(todo)} now")
            if todo:
                write(store, "gb_hist", h[months.isin(todo)])
            if len(missing) <= MAX_MONTHS:
                st["hist"] = fetched.strftime("%Y-%m-%d")
                store.write_json("gbhist_state.json", st)
    if not st.get("wind_da"):
        f = neso_wind_da(fetched, True)
        log(f"gb_forecast NESO day-ahead wind archive: {len(f)} rows")
        if len(f):
            write(store, "gb_forecast", f)
            st["wind_da"] = fetched.strftime("%Y-%m-%d")
            store.write_json("gbhist_state.json", st)


def main(argv=None) -> None:
    mode = (argv or sys.argv[1:] or ["daily"])[0]
    store = Store()
    {"daily": daily, "backfill": backfill}[mode](store)
    lg = store.read_json("collector_log.json", []) or []
    lg.append({"run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "mode": f"gbhist-{mode}"})
    store.write_json("collector_log.json", lg[-400:])


if __name__ == "__main__":
    main()
