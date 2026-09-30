"""Forecast sources. Each returns, per grid cell, a wind time series at a reference height:

    {"t": [unix seconds], "u": [m/s], "v": [m/s], "z": reference height in m}

Forecasts are cached in state/forecast_<source>.json and only refetched when older than
config.REFRESH_HOURS, which keeps API usage to a few hundred calls per day.
"""
from __future__ import annotations

import collections
import json
import math
import time
from datetime import datetime, timezone

from . import config
from .budget import Budget, BudgetExceeded


def cell_key(lat: float, lon: float) -> str:
    g = config.CELL_DEG
    return f"{round(lat / g) * g:.2f},{round(lon / g) * g:.2f}"


def _cache_path(source: str):
    return config.STATE_DIR / f"forecast_{source}.json"


def _load_cache(source: str) -> dict:
    p = _cache_path(source)
    return json.loads(p.read_text()) if p.exists() else {"cells": {}}


def _save_cache(source: str, cache: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(source).write_text(json.dumps(cache, separators=(",", ":")))


def _age_hours(iso: str | None) -> float:
    if not iso:
        return float("inf")
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600


# ---------------------------------------------------------------- Windy Point Forecast API
WINDY_URL = "https://api.windy.com/api/point-forecast/v2"


def _windy_cell(lat: float, lon: float) -> dict:
    import requests

    body = {"lat": lat, "lon": lon, "model": config.WINDY_MODEL, "parameters": ["wind"],
            "levels": ["surface"], "key": config.WINDY_KEY}
    r = requests.post(WINDY_URL, json=body, timeout=30)
    r.raise_for_status()
    d = r.json()
    t = [ms / 1000 for ms in d["ts"]]
    u, v = d["wind_u-surface"], d["wind_v-surface"]
    keep = [i for i in range(len(t)) if u[i] is not None and v[i] is not None]
    return {"t": [t[i] for i in keep], "u": [u[i] for i in keep], "v": [v[i] for i in keep], "z": 10.0}


def fetch_windy(cells: dict[str, tuple[float, float]]) -> dict:
    if not config.WINDY_KEY:
        raise SystemExit("WINDY_KEY is not set")
    cache = _load_cache("windy")
    stale = _age_hours(cache.get("fetched")) >= config.REFRESH_HOURS
    todo = [k for k in cells if stale or k not in cache["cells"]]
    if not todo:
        print(f"windy: cache is {_age_hours(cache.get('fetched')):.1f} h old, no calls made")
        return cache["cells"]
    budget = Budget("windy")
    print(f"windy: fetching {len(todo)} cells ({budget.left} calls left today)")
    done = 0
    for k in todo:
        try:
            budget.take()
        except BudgetExceeded as e:
            print(f"windy: {e}; keeping cached forecasts for the remaining {len(todo) - done} cells")
            break
        try:
            cache["cells"][k] = _windy_cell(*cells[k])
            done += 1
        except Exception as e:  # one retry at most, then move on
            print(f"windy: cell {k} failed ({e}); retrying once")
            time.sleep(2)
            try:
                budget.take()
                cache["cells"][k] = _windy_cell(*cells[k])
                done += 1
            except Exception as e2:
                print(f"windy: cell {k} failed again ({e2}); skipped")
    if done:
        cache["fetched"] = datetime.now(timezone.utc).isoformat()
        cache["model"] = config.WINDY_MODEL
    _save_cache("windy", cache)
    print(f"windy: {done} cells updated, {budget.calls} calls used today")
    return cache["cells"]


# ---------------------------------------------------------------- ECMWF open data (IFS, 100 m wind)
def fetch_ecmwf(cells: dict[str, tuple[float, float]]) -> dict:
    """One download covers every cell. Needs: pip install ecmwf-opendata xarray cfgrib eccodes"""
    from ecmwf.opendata import Client
    import xarray as xr

    cache = _load_cache("ecmwf")
    client = Client(source="ecmwf")
    latest = client.latest(type="fc", param="100u", step=0)
    if cache.get("run") == latest.isoformat() and all(k in cache["cells"] for k in cells):
        print(f"ecmwf: run {latest:%Y-%m-%d %HZ} already cached, nothing to download")
        return cache["cells"]
    Budget("ecmwf", cap=50).take()
    target = config.STATE_DIR / "ecmwf_latest.grib2"
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    steps = list(range(0, 73, 3))
    client.retrieve(type="fc", param=["100u", "100v"], step=steps, date=latest.strftime("%Y%m%d"),
                    time=latest.hour, target=str(target))
    ds = xr.open_dataset(target, engine="cfgrib")
    valid = ds["valid_time"].values.astype("datetime64[s]").astype("int64").tolist()  # unix seconds per step
    out = {}
    for k, (lat, lon) in cells.items():
        x = lon % 360 if float(ds.longitude.max()) > 180 else lon
        p = ds.sel(latitude=lat, longitude=x, method="nearest")
        out[k] = {"t": valid, "u": [float(x) for x in p["u100"].values], "v": [float(x) for x in p["v100"].values],
                  "z": 100.0}
    ds.close()
    run = latest
    target.unlink(missing_ok=True)
    cache = {"cells": out, "run": latest.isoformat(), "fetched": datetime.now(timezone.utc).isoformat()}
    _save_cache("ecmwf", cache)
    print(f"ecmwf: run {run:%Y-%m-%d %HZ}, {len(out)} cells")
    return out


# ---------------------------------------------------------------- Open-Meteo (free, non-commercial, CC BY 4.0)
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_ECMWF_URL = "https://api.open-meteo.com/v1/ecmwf"  # has 100 m wind for ECMWF models


def _om_plan(model: str) -> list[tuple[str, str, tuple[int, ...]]]:
    """(url, model, heights) to try in order. ECMWF models go to the ECMWF endpoint for 100 m wind."""
    general = (OPENMETEO_URL, model, (120, 80, 10))
    if model.startswith("ecmwf"):
        return [(OPENMETEO_ECMWF_URL, model, (100, 10)), (OPENMETEO_URL, "ecmwf_ifs025", (120, 80, 10))]
    return [general]


def _om_request(batch: list[tuple[float, float]]) -> list[dict]:
    import requests

    err = None
    for url, model, heights in _om_plan(config.OPENMETEO_MODEL):
        params = {
            "latitude": ",".join(f"{lat:.3f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.3f}" for _, lon in batch),
            "hourly": ",".join(f"wind_speed_{z}m,wind_direction_{z}m" for z in heights),
            "models": model, "wind_speed_unit": "ms", "timeformat": "unixtime", "past_days": 1, "forecast_days": 3,
        }
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 200:
            d = r.json()
            d = d if isinstance(d, list) else [d]
            for loc in d:
                loc["_heights"] = heights
            return d
        err = f"{url.rsplit('/', 1)[-1]} {model}: HTTP {r.status_code}: {r.text[:200]}"
        print(f"openmeteo: {err}; trying next option")
    raise RuntimeError(err)


def _om_series(loc: dict) -> dict | None:
    h = loc.get("hourly", {})
    t = h.get("time", [])
    for z in loc.get("_heights", (120, 80, 10)):
        ws, wd = h.get(f"wind_speed_{z}m"), h.get(f"wind_direction_{z}m")
        if not ws or not wd:
            continue
        keep = [i for i in range(len(t)) if ws[i] is not None and wd[i] is not None]
        if len(keep) < len(t) * 0.5:
            continue
        u = [-ws[i] * math.sin(math.radians(wd[i])) for i in keep]
        v = [-ws[i] * math.cos(math.radians(wd[i])) for i in keep]
        return {"t": [t[i] for i in keep], "u": u, "v": v, "z": float(z)}
    return None


def fetch_openmeteo(cells: dict[str, tuple[float, float]]) -> dict:
    cache = _load_cache("openmeteo")
    fresh = _age_hours(cache.get("fetched")) < config.REFRESH_HOURS and cache.get("model") == config.OPENMETEO_MODEL
    todo = [k for k in cells if not fresh or k not in cache["cells"]]
    if not todo:
        print(f"openmeteo: cache is {_age_hours(cache.get('fetched')):.1f} h old, no calls made")
        return cache["cells"]
    budget = Budget("openmeteo")
    print(f"openmeteo: model {config.OPENMETEO_MODEL}, fetching {len(todo)} locations ({budget.left} calls left today)")
    done, heights = 0, collections.Counter()
    for i in range(0, len(todo), 50):  # up to 50 locations per request
        keys = todo[i:i + 50]
        try:
            budget.take(len(keys))  # count every location as a call, to be safe
        except BudgetExceeded as e:
            print(f"openmeteo: {e}; keeping cached forecasts for the rest")
            break
        try:
            locs = _om_request([cells[k] for k in keys])
        except Exception as e:
            print(f"openmeteo: request failed ({e}); keeping cached forecasts for these {len(keys)} locations")
            continue
        for k, loc in zip(keys, locs):
            ser = _om_series(loc)
            if ser:
                cache["cells"][k] = ser
                heights[int(ser["z"])] += 1
                done += 1
    if done:
        cache["fetched"] = datetime.now(timezone.utc).isoformat()
        cache["model"] = config.OPENMETEO_MODEL
    _save_cache("openmeteo", cache)
    hs = ", ".join(f"{n} at {z} m" for z, n in sorted(heights.items(), reverse=True))
    print(f"openmeteo: {done} locations updated ({hs}), {budget.calls} calls counted today")
    return cache["cells"]


# ---------------------------------------------------------------- synthetic (offline testing)
def synthetic_uv(lat: float, lon: float, t: float) -> tuple[float, float]:
    """A weather system drifting west to east, so countries don't all peak at once. 10 m wind."""
    h = t / 3600
    ws = 7.6 + 4.2 * math.sin(2 * math.pi * (h - lon * 1.3) / 26 + lat * 0.4) + 1.3 * math.sin(h / 3.1 + lat * 2)
    ws = max(0.5, ws)
    wd = (250 + 60 * math.sin((h - lon) / 9)) % 360  # direction the wind comes from
    r = math.radians(wd)
    return -ws * math.sin(r), -ws * math.cos(r)


def fetch_synthetic(cells: dict[str, tuple[float, float]]) -> dict:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).timestamp()
    ts = [now + 3600 * h for h in range(-48, 73)]
    out = {}
    for k, (lat, lon) in cells.items():
        uv = [synthetic_uv(lat, lon, t) for t in ts]
        out[k] = {"t": ts, "u": [a for a, _ in uv], "v": [b for _, b in uv], "z": 10.0}
    return out


def get_forecasts(cells: dict[str, tuple[float, float]], source: str = config.SOURCE) -> dict:
    return {"openmeteo": fetch_openmeteo, "windy": fetch_windy, "ecmwf": fetch_ecmwf,
            "synthetic": fetch_synthetic}[source](cells)
