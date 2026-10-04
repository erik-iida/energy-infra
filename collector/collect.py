"""Collect ENTSO-E series into the data store.

    python -m collector.collect daily      # last 4 days + tomorrow (revisions, late TSOs, next-day prices)
    python -m collector.collect recent     # last 2 days + tomorrow (keeps the Data tab current between daily runs)
    python -m collector.collect backfill   # ended months from BACKFILL_FROM not stored yet, newest first, resumable
    python -m collector.collect auto       # backfill while ended months are missing, otherwise recent (every 2 h)
    python -m collector.collect probe      # one zone and one border for 2 days: checks parsing, writes nothing

Needs ENTSOE_TOKEN. Each run appends a summary to collector_log.json in the store.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import pandas as pd

from common.entsoe import ZONE_EIC, token

from . import entsoe_raw as er
from common.store import Store

BACKFILL_FROM = os.environ.get("BACKFILL_FROM", "2024-01")
TIME_BUDGET_S = int(os.environ.get("COLLECT_BUDGET_S", str(45 * 60)))
WORKERS = 4
DATASETS = ["da_price", "gen_actual", "gen_forecast", "load", "flows"]


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_window(a: datetime, b: datetime, zones=None, borders=None) -> tuple[dict[str, pd.DataFrame], int, list[str]]:
    """Every per-zone dataset and every border direction for [a, b)."""
    zones = list(ZONE_EIC) if zones is None else zones
    borders = er.BORDERS if borders is None else borders
    fetched = datetime.now(timezone.utc)
    parts: dict[str, list[pd.DataFrame]] = {d: [] for d in DATASETS}
    calls, errors = 0, []
    jobs = [("zone", z) for z in zones] + [("flow", (x, y)) for p, q in borders for x, y in ((p, q), (q, p))]
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {}
        for kind, arg in jobs:
            if kind == "zone":
                futs[ex.submit(er.fetch_zone, arg, a, b)] = (kind, arg)
            else:
                futs[ex.submit(er.fetch_flow, *arg, a, b)] = (kind, arg)
        for f in as_completed(futs):
            kind, arg = futs[f]
            try:
                res, n, err = f.result()
            except Exception as e:
                errors.append(f"{kind} {arg}: {e!r}"[:200])
                continue
            calls += n
            errors += err
            rows = res if kind == "zone" else {"flows": res}
            for ds, df in er.frames(rows, fetched).items():
                parts[ds].append(df)
    out = {d: pd.concat(p, ignore_index=True) for d, p in parts.items() if p}
    return out, calls, errors


def late_zones(data: dict[str, pd.DataFrame], min_h: float = 6.0) -> dict[str, float]:
    """Zones whose newest actual-generation timestamp is more than min_h hours old (TSO publication lag)."""
    df = data.get("gen_actual")
    if df is None or df.empty:
        return {}
    now = pd.Timestamp.now(tz="UTC")
    last = df.groupby("zone")["ts"].max()
    lag = ((now - last).dt.total_seconds() / 3600).round(1)
    return {z: float(h) for z, h in lag[lag > min_h].sort_values(ascending=False).items()}


def seq_note() -> dict:
    d = dict(er.SEQ_DROPPED)
    er.SEQ_DROPPED.clear()
    return {"seq_dropped": d} if d else {}


def write_all(st: Store, data: dict[str, pd.DataFrame]) -> dict:
    summary = {}
    for ds, df in data.items():
        summary[ds] = {"rows": len(df), "files": st.write(ds, df, log)}
    return summary


def run_log(st: Store, entry: dict) -> None:
    hist = st.read_json("collector_log.json", default=[])
    hist.append(entry)
    st.write_json("collector_log.json", hist[-400:])


def months_between(first: str, last: str) -> list[str]:
    out, m = [], pd.Period(first, "M")
    while m <= pd.Period(last, "M"):
        out.append(str(m))
        m += 1
    return out


def daily(st: Store, back_days: int = 4) -> dict:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    a, b = today - timedelta(days=back_days), today + timedelta(days=2)
    log(f"window {a:%Y-%m-%d} .. {b:%Y-%m-%d}")
    data, calls, errors = fetch_window(a, b)
    return {"window": [a.isoformat(), b.isoformat()], "calls": calls, "errors": errors[:40],
            "n_errors": len(errors), "late_gen_actual_h": late_zones(data), **seq_note(),
            "written": write_all(st, data)}


def backfill(st: Store, t0: float) -> dict:
    state = st.read_json("backfill_state.json", default={"done": {}})
    now = datetime.now(timezone.utc)
    # ended months only (newest first): the running month is kept current by the daily / recent windows. Until 4 Oct 2026
    # the running month was in this list too and never marked done, so every 2-hourly run re-downloaded the whole month.
    months = months_between(BACKFILL_FROM, now.strftime("%Y-%m"))[::-1][1:]
    todo = [m for m in months if m not in state["done"]]
    log(f"backfill: {len(todo)} of {len(months)} months to do")
    did = []
    for m in todo:
        if time.time() - t0 > TIME_BUDGET_S - 12 * 60:
            break
        p = pd.Period(m, "M")
        a = p.start_time.tz_localize("UTC").to_pydatetime()
        b = min((p + 1).start_time.tz_localize("UTC").to_pydatetime(), now.replace(minute=0, second=0, microsecond=0))
        t1 = time.time()
        data, calls, errors = fetch_window(a, b)
        written = write_all(st, data)
        if (p + 1).start_time.tz_localize("UTC") <= now:  # always true now; kept as a guard
            state["done"][m] = {"at": now.isoformat(timespec="seconds"), "calls": calls, "n_errors": len(errors),
                                "rows": {k: v["rows"] for k, v in written.items()}}
            st.write_json("backfill_state.json", state)
        log(f"backfill {m}: {calls} calls, {len(errors)} errors, {time.time() - t1:.0f} s")
        did.append({"month": m, "calls": calls, "errors": errors[:15], "n_errors": len(errors), **seq_note()})
    left = len([m for m in months if m not in state["done"]])
    return {"months": did, "left": left}


def probe() -> dict:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    data, calls, errors = fetch_window(today - timedelta(days=1), today + timedelta(days=1),
                                       zones=["DE-LU", "RO"], borders=[("HU", "RO")])
    for ds, df in data.items():
        log(f"{ds}: {len(df)} rows, res {sorted(df.res_min.unique())}, {df.ts.min()} .. {df.ts.max()}")
        log(df.head(3).to_string())
    return {"calls": calls, "errors": errors, "late_gen_actual_h": late_zones(data), **seq_note()}


def main(argv=None) -> None:
    mode = (argv or sys.argv[1:] or ["daily"])[0]
    if not token():
        log("ENTSOE_TOKEN not set")
        sys.exit(1)
    t0 = time.time()
    if mode == "probe":
        log(str(probe()))
        return
    st = Store()
    if mode == "auto":
        state = st.read_json("backfill_state.json", default={"done": {}})
        now = datetime.now(timezone.utc).strftime("%Y-%m")
        backlog = [m for m in months_between(BACKFILL_FROM, now)[:-1] if m not in state["done"]]
        mode = "backfill" if backlog else "recent"
        log(f"auto: {len(backlog)} ended months missing -> {mode}")
    entry = {"mode": mode, "start": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        if mode == "daily":
            entry.update(daily(st))
        elif mode == "recent":
            entry.update(daily(st, back_days=2))
        elif mode == "backfill":
            entry.update(backfill(st, t0))
        else:
            raise SystemExit(f"unknown mode {mode}")
    except Exception as e:
        entry["failed"] = repr(e)[:400]
        raise
    finally:
        entry["seconds"] = round(time.time() - t0)
        try:
            run_log(st, entry)
        except Exception as e:
            log(f"run log not written: {e!r}")
        log(f"{mode}: {entry.get('calls', '')} calls, {entry['seconds']} s")


if __name__ == "__main__":
    main()
