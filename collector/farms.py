"""Per-farm wind and wake-model output from the hourly pipeline, into the data store.

Called at the end of pipeline.run when COLLECT_FARMS=1. These series can't be fetched again later (they are our
own model runs on the forecast of the day), so every run writes them; merging by key makes repeats harmless.

  farm_hourly    farm_id, ts, ws (hub-height m/s), wd (deg, from), p_<model> (MW) per wake model, nwp, fetched
                 = the past 24 h of the feed, i.e. the latest estimate for each hour
  farm_forecast  issued (forecast fetch time), farm_id, ts, lead_h, ws, wd, p_<model>
                 = the next 24 h, written once per new forecast (about every 6 h)
  farms_meta     one row per farm id: name, country, position, capacity, turbine type; snapshot per month,
                 so the ids in the other files can always be resolved (ids are never reused)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from pipeline import config

from .store import Store

LAST = config.STATE_DIR / "collect_farms.json"


def _rows(feed: dict, hours_key: str, U: str, D: str, P: str) -> list[dict]:
    hours = pd.to_datetime(feed[hours_key], utc=True)
    models = list(feed["models"])
    out = []
    for fid, f in feed["farms"].items():
        us, ds, ps = f.get(U), f.get(D), f.get(P)
        if not us:
            continue
        for i, t in enumerate(hours):
            if i >= len(us) or us[i] is None:
                continue
            r = {"farm_id": int(fid), "ts": t, "ws": float(us[i]), "wd": None if ds[i] is None else float(ds[i])}
            for m in models:
                v = (ps or {}).get(m, [None] * len(hours))[i]
                r[f"p_{m}"] = None if v is None else float(v)
            out.append(r)
    return out


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    df["farm_id"] = df["farm_id"].astype("int64")
    for c in df.columns:
        if c == "ws" or c == "wd" or c.startswith("p_") or c == "lead_h":
            df[c] = df[c].astype("float32")
    return df


def meta(site: dict) -> pd.DataFrame:
    rows = []
    for f in site["farms"]:
        rows.append({"farm_id": int(f["id"]), "name": f.get("n"), "country": f.get("c"), "region": f.get("rg"),
                     "lat": f.get("lat"), "lon": f.get("lon"), "mw": f.get("inst", f.get("cap")),
                     "turbines": len(f["xy"]) if "xy" in f else None, "turbine_type": f.get("t"),
                     "turbine_mw": f.get("mw"), "rotor_m": f.get("D"), "hub_m": f.get("h"), "year": f.get("y"),
                     "onshore": bool(f.get("on")), "src": f.get("src", "eurowindwakes"), "est": f.get("est")})
    df = pd.DataFrame(rows)
    df["year"] = df["year"].astype("string")
    df["est"] = df["est"].astype("string")
    return df


def record(feed: dict, site: dict, source: str, log=print) -> None:
    st = Store()
    now = pd.Timestamp(datetime.now(timezone.utc))
    nwp = feed.get("nwp_model") or source

    hourly = pd.DataFrame(_rows(feed, "hours", "U", "dir", "P"))
    if not hourly.empty:
        hourly = _typed(hourly)
        hourly["nwp"] = nwp
        hourly["fetched"] = now
        st.write("farm_hourly", hourly, log)

    # forecast: once per new forecast fetch
    try:
        fc_cache = json.loads((config.STATE_DIR / f"forecast_{source}.json").read_text())
        issued = pd.Timestamp(fc_cache.get("fetched")).tz_convert("UTC").floor("s")
    except Exception:
        issued = None
    last = json.loads(LAST.read_text()) if LAST.exists() else {}
    if issued is not None and last.get("issued") != issued.isoformat():
        fc = pd.DataFrame(_rows(feed, "fc_hours", "fU", "fdir", "fP"))
        if not fc.empty:
            fc["issued"] = issued
            fc["lead_h"] = (fc["ts"] - issued).dt.total_seconds() / 3600
            fc = _typed(fc)
            fc["nwp"] = nwp
            fc["fetched"] = now
            st.write("farm_forecast", fc, log)
        last["issued"] = issued.isoformat()

    month = now.strftime("%Y-%m")
    if last.get("meta_month") != month or last.get("meta_n") != len(site["farms"]):
        m = meta(site)
        m["fetched"] = now
        st.write("farms_meta", m, log)
        last["meta_month"], last["meta_n"] = month, len(site["farms"])
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(last))
