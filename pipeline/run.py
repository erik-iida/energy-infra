"""Hourly job: forecast -> hub-height wind -> PyWake -> web/data/feed.json

    python -m pipeline.run                        # Open-Meteo (default), free, no key
    python -m pipeline.run --source synthetic     # made-up weather, no network
    python -m pipeline.run --source windy         # needs WINDY_KEY

Each run records the current hour into state/history.json (kept for 24 h) and computes the
next 24 h from the cached forecast. The web page reads feed.json.
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config, wake
from .sources import cell_key, get_forecasts

HIST = config.STATE_DIR / "history.json"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:00Z")


def hub_wind(fc: dict, times: list[float], hub: float) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate u, v to the requested times, return hub-height speed and meteorological direction.
    Times outside the forecast give NaN."""
    t = np.asarray(fc["t"], float)
    tt = np.asarray(times, float)
    u = np.interp(tt, t, fc["u"], left=np.nan, right=np.nan)
    v = np.interp(tt, t, fc["v"], left=np.nan, right=np.nan)
    ws_ref = np.hypot(u, v)
    wd = (np.degrees(np.arctan2(u, v)) + 180) % 360  # direction the wind comes from
    shear = np.log(hub / config.Z0) / np.log(fc["z"] / config.Z0)
    return ws_ref * shear, wd


def r1(a):
    return [None if (x is None or not np.isfinite(x)) else round(float(x), 1) for x in a]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=config.SOURCE, choices=["openmeteo", "windy", "ecmwf", "synthetic"])
    ap.add_argument("--no-backfill", dest="backfill", action="store_false",
                    help="don't fill missing past hours from the cached forecast (default: fill them if it covers them)")
    args = ap.parse_args(argv)
    t0 = time.time()

    site = json.loads(config.SITE_JSON.read_text(encoding="utf-8"))
    farms = site["farms"]
    cells = {}
    for f in farms:
        k = cell_key(f["lat"], f["lon"])
        cells[k] = tuple(float(v) for v in k.split(","))
    fc_cells = get_forecasts(cells, args.source)

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    past = [now - timedelta(hours=h) for h in range(config.HISTORY_HOURS - 1, -1, -1)]
    future = [now + timedelta(hours=h) for h in range(1, config.FORECAST_HOURS + 1)]

    hist = json.loads(HIST.read_text()) if HIST.exists() else {"hours": {}}
    need_past = [d for d in past if iso(d) not in hist["hours"] or d == now] if args.backfill else [now]
    times = need_past + future
    tsec = [d.timestamp() for d in times]
    models = list(config.WAKE_MODELS) + ["nowake"]

    results = {}
    missing = 0
    for f in farms:
        fc = fc_cells.get(cell_key(f["lat"], f["lon"]))
        if not fc:
            missing += 1
            continue
        lay = "xy" in f
        ws, wd = hub_wind(fc, tsec, f["h"] if lay else 100.0)
        ok = np.isfinite(ws)
        P = {m: np.full(len(times), np.nan) for m in models}
        if ok.any():
            pw = wake.farm_power(f, site["types"], ws[ok], wd[ok]) if lay else wake.estimate_no_layout(f, ws[ok])
            for m in models:
                P[m][ok] = pw[m]
        results[str(f["id"])] = (ws, wd, P)
    if missing:
        print(f"warning: {missing} farms had no forecast")

    # write the past hours into the rolling history
    for i, d in enumerate(need_past):
        row = {}
        for fid, (ws, wd, P) in results.items():
            if np.isfinite(ws[i]):
                row[fid] = {"U": round(float(ws[i]), 2), "dir": int(round(float(wd[i]))) % 360,
                            "P": {m: round(float(P[m][i]), 2) for m in models}}
        if row:
            hist["hours"][iso(d)] = row
    keep = {iso(d) for d in past}
    hist["hours"] = {k: v for k, v in hist["hours"].items() if k in keep}
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(hist, separators=(",", ":")))

    # assemble the feed
    np_ = len(need_past)
    feed_farms = {}
    for f in farms:
        fid = str(f["id"])
        hrs = [hist["hours"].get(iso(d), {}).get(fid) for d in past]
        ent = {"U": [h["U"] if h else None for h in hrs], "dir": [h["dir"] if h else None for h in hrs],
               "P": {m: [h["P"][m] if h else None for h in hrs] for m in models}}
        if fid in results:
            ws, wd, P = results[fid]
            ent["fU"] = r1(ws[np_:])
            ent["fdir"] = [None if not np.isfinite(x) else int(round(float(x))) % 360 for x in wd[np_:]]
            ent["fP"] = {m: r1(P[m][np_:]) for m in models}
        feed_farms[fid] = ent

    feed = {
        "version": 1,
        "source": args.source,
        "windy_model": config.WINDY_MODEL if args.source == "windy" else None,
        "nwp_model": {"openmeteo": config.OPENMETEO_MODEL, "windy": config.WINDY_MODEL}.get(args.source),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ref_heights_m": dict(collections.Counter(str(int(c["z"])) for c in fc_cells.values())),
        "models": {**config.WAKE_MODELS, "nowake": "No wake"},
        "hours": [iso(d) for d in past],
        "fc_hours": [iso(d) for d in future],
        "farms": feed_farms,
    }
    if config.MARKET and args.source != "synthetic":
        try:
            from . import market
            mk, hist = market.build(farms, feed["hours"] + feed["fc_hours"])
            farms_block = feed.pop("farms")
            feed["market"] = mk
            feed["farms"] = farms_block  # keep the large block last so the metadata is easy to read
            (config.FEED_JSON.parent / "market_history.json").write_text(
                json.dumps(hist, separators=(",", ":")), encoding="utf-8")
        except Exception as e:  # market data must never stop the wind feed
            print(f"market: failed ({e!r}); feed written without market data")
    config.FEED_JSON.write_text(json.dumps(feed, separators=(",", ":")), encoding="utf-8")
    tot = sum(results[k][2]["turbopark"][np_ - 1] for k in results if np.isfinite(results[k][2]["turbopark"][np_ - 1]))
    print(f"{args.source}: {len(results)} farms, {len(times)} time steps, Europe now {tot / 1000:.2f} GW (TurbOPark), "
          f"{time.time() - t0:.0f} s -> {config.FEED_JSON.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
