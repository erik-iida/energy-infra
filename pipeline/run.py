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
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config, wake
from .sources import cell_key, get_forecasts

HIST = config.STATE_DIR / "history.json"
WCACHE = config.STATE_DIR / "wake_cache.json"
# Wake results are reused when a farm, its hour and its hub-height wind (speed, direction) are unchanged: the forecast is
# cached between model updates, so most hourly runs repeat the previous run's inputs. Any change to wake.py, the turbine
# types or a farm's layout gives a new signature and recomputes.
WAKE_SIG = hashlib.sha1((config.ROOT / "pipeline" / "wake.py").read_bytes()).hexdigest()[:12]


def farm_sig(f: dict, types: list[dict]) -> str:
    keys = ("xy", "ti", "h", "mw", "D", "ur", "cap", "inst", "on")
    used = sorted({f["ti"]} if isinstance(f.get("ti"), int) else set(f.get("ti") or []))
    blob = json.dumps([WAKE_SIG, {k: f.get(k) for k in keys}, [types[g] for g in used if g < len(types)]], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


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
    secs = {"forecast": round(time.time() - t0, 1)}  # wall time per stage, written to feed["timing_s"] (find slow stages)
    t1 = time.time()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    past = [now - timedelta(hours=h) for h in range(config.HISTORY_HOURS - 1, -1, -1)]
    future = [now + timedelta(hours=h) for h in range(1, config.FORECAST_HOURS + 1)]

    hist = json.loads(HIST.read_text()) if HIST.exists() else {"hours": {}}
    need_past = [d for d in past if iso(d) not in hist["hours"] or d == now] if args.backfill else [now]
    times = need_past + future
    tsec = [d.timestamp() for d in times]
    models = list(config.WAKE_MODELS) + ["nowake"]

    results = {}
    timing = {}  # farm id -> ({model: ms}, time steps)
    missing = 0
    try:
        wc_old = json.loads(WCACHE.read_text()) if WCACHE.exists() else {}
    except Exception:
        wc_old = {}
    wc_new, reused, computed = {}, 0, 0
    # PyWake's cost per call is mostly per turbine (it steps downstream through the farm), nearly the same for 2 hours as
    # for 30. So when a farm has to be computed, compute every forecast hour up to the next forecast refresh + 24 h too:
    # the following runs then find all their hours in the cache until the forecast itself changes.
    ahead = int(np.ceil(config.REFRESH_HOURS)) + config.FORECAST_HOURS + 1
    ext_t = [now.timestamp() + 3600 * h for h in range(config.FORECAST_HOURS + 1, ahead + 1)]
    for f in farms:
        fc = fc_cells.get(cell_key(f["lat"], f["lon"]))
        if not fc:
            missing += 1
            continue
        fid = str(f["id"])
        lay = "xy" in f
        ws, wd = hub_wind(fc, tsec, f["h"] if lay else 100.0)
        ok = np.isfinite(ws)
        P = {m: np.full(len(times), np.nan) for m in models}
        sig = farm_sig(f, site["types"])
        old = wc_old.get(fid) if (wc_old.get(fid) or {}).get("sig") == sig else None
        # keep cached hours from now on (validated against the wind when used); drop the past
        ent = {"sig": sig, "h": {k: v for k, v in (old or {}).get("h", {}).items() if int(k) >= now.timestamp()},
               "ms": (old or {}).get("ms")}
        todo = []
        for i in np.flatnonzero(ok):
            key = str(int(tsec[i]))
            c = (old or {}).get("h", {}).get(key)
            if c and abs(c[0] - ws[i]) < 1e-3 and abs(c[1] - wd[i]) < 1e-2:
                for m, v in zip(models, c[2]):
                    P[m][i] = v
                ent["h"][key] = c
                reused += 1
            else:
                todo.append(i)
        if todo:
            idx = np.array(todo)
            # the extra hours ahead that are not cached yet, computed in the same call
            xs, xd = hub_wind(fc, ext_t, f["h"] if lay else 100.0)
            xk = [j for j in range(len(ext_t)) if np.isfinite(xs[j]) and str(int(ext_t[j])) not in ent["h"]]
            ws_in = np.concatenate([ws[idx], xs[xk]]) if xk else ws[idx]
            wd_in = np.concatenate([wd[idx], xd[xk]]) if xk else wd[idx]
            try:
                pw = wake.farm_power(f, site["types"], ws_in, wd_in) if lay else wake.estimate_no_layout(f, ws_in)
            except Exception as ex:  # one bad layout must never stop the feed
                print(f"warning: {f['n']}: {ex!r}"[:200])
                pw = wake.estimate_no_layout({**f, "cap": f.get("inst", f.get("cap", 0))}, ws_in)
            if "_ms" in pw:
                ent["ms"] = [pw.pop("_ms"), len(ws_in)]
            n = len(idx)
            for m in models:
                P[m][idx] = np.asarray(pw[m])[:n]
            row = lambda w, d, k: [round(float(w), 4), round(float(d), 3),  # noqa: E731
                                   [None if not np.isfinite(pw[m][k]) else float(pw[m][k]) for m in models]]
            for k, i in enumerate(todo):
                ent["h"][str(int(tsec[i]))] = row(ws[i], wd[i], k)
            for k, j in enumerate(xk):
                ent["h"][str(int(ext_t[j]))] = row(xs[j], xd[j], n + k)
            computed += len(ws_in)
        if ent["ms"]:
            timing[fid] = tuple(ent["ms"])
        wc_new[fid] = ent
        results[fid] = (ws, wd, P)
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    WCACHE.write_text(json.dumps(wc_new, separators=(",", ":")))
    print(f"wake: {computed} farm-hours computed, {reused} reused from the previous run")
    if missing:
        print(f"warning: {missing} farms had no forecast")
    secs["wake"] = round(time.time() - t1, 1)

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
        if fid in timing:
            ent["ms"], ent["nt"] = timing[fid]
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
    t1 = time.time()
    if config.MARKET and args.source != "synthetic":
        try:
            from . import market
            mk = market.build(farms, feed["hours"] + feed["fc_hours"])
            farms_block = feed.pop("farms")
            feed["market"] = mk
            if os.environ.get("SPARK") in ("private", "public"):  # off by default: see pipeline/spark.py and scripts/split_private.py
                try:
                    from . import spark
                    sp = spark.build(mk.get("prices", {}), len(feed["hours"]))
                    if sp:
                        mk["spark"] = sp
                except Exception as e:
                    print(f"spark spreads: skipped ({type(e).__name__})")
            feed["farms"] = farms_block  # keep the large block last so the metadata is easy to read
        except Exception as e:  # market data must never stop the wind feed
            print(f"market: failed ({e!r}); feed written without market data")
    secs["market"] = round(time.time() - t1, 1)
    secs["total_before_write"] = round(time.time() - t0, 1)
    feed["timing_s"] = secs
    feed = {"schema": 1, **feed}  # data contract version (docs/DATA_CONTRACT.md); bump when a field the page reads changes
    config.FEED_JSON.write_text(json.dumps(feed, separators=(",", ":")), encoding="utf-8")
    t1 = time.time()
    if os.environ.get("COLLECT_FARMS") == "1" and args.source != "synthetic":
        try:  # data store: per-farm wind and wake output (collector/farms.py); never blocks the feed
            from collector import farms as collect_farms
            collect_farms.record(feed, site, args.source)
        except Exception as e:
            print(f"collector: farm data not stored ({e!r})"[:300])
    secs["store"] = round(time.time() - t1, 1)
    print("timing (s): " + ", ".join(f"{k} {v}" for k, v in secs.items()))
    tot = sum(results[k][2]["turbopark"][np_ - 1] for k in results if np.isfinite(results[k][2]["turbopark"][np_ - 1]))
    print(f"{args.source}: {len(results)} farms, {len(times)} time steps, all farms now {tot / 1000:.2f} GW (TurbOPark), "
          f"{time.time() - t0:.0f} s -> {config.FEED_JSON.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
