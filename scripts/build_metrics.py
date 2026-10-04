"""Compute the daily metrics (newsletter/registry.py) from the store and write them to the store as `metrics_daily`.

    python scripts/build_metrics.py [--days 10] [--all]

  default  the last --days CET days (today and tomorrow included, so day-ahead based metrics appear as soon as the
           auction is out) PLUS every month the backfill has finished (backfill_state.json) and that has not been computed
           in full since (metrics_state.json), so the history fills in by itself while the backfill goes on
  --all    recompute every month in the store (after a definition change: bump registry.VERSION first)

One row per zone x CET day x metric: zone, day (naive CET date), metric, value, version, fetched. Re-running overwrites
(latest `fetched` wins), rows are never dropped. Metrics need complete days (registry.min_hours), so partial days simply
have no row. Spark spreads (private fuel data) are never computed here.
Needs the store (GH_TOKEN in Actions, or STORE_DIR=<folder>).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.store import Store  # noqa: E402
from newsletter import build as NB  # noqa: E402
from newsletter import metrics as M  # noqa: E402
from newsletter import registry as R  # noqa: E402

BUFFER_DAYS = 31  # context before the range: flows use the borders present on most days of the loaded window


def compute(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """Metrics for the CET days first..last (naive dates), inclusive."""
    a = (first - pd.Timedelta(days=BUFFER_DAYS)).tz_localize(M.CET).tz_convert("UTC")
    b = (last + pd.Timedelta(days=2)).tz_localize(M.CET).tz_convert("UTC")
    da, ga, ld, fl = NB.load_range(a, b)
    if da.empty:
        return pd.DataFrame()
    m = M.all_metrics(da, ga, None, ld, fl)
    m = m[(m["day"] >= first) & (m["day"] <= last) & m["metric"].isin(R.public_ids())]
    return m.assign(version=R.VERSION, fetched=pd.Timestamp.now(tz="UTC")).reset_index(drop=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    st = Store()
    done = (st.read_json("backfill_state.json", {}) or {}).get("done", {})
    state = st.read_json("metrics_state.json", {}) or {}
    todo = [m for m in sorted(done) if a.all or state.get(m, "") < done[m].get("at", "")]
    today = pd.Timestamp.now(tz=M.CET).tz_localize(None).normalize()
    ranges = []
    if not a.all:
        ranges.append((today - pd.Timedelta(days=a.days), today + pd.Timedelta(days=1), None))
    for m in todo:
        p = pd.Period(m)
        ranges.append((p.start_time.normalize(), min(p.end_time.normalize(), today + pd.Timedelta(days=1)), m))
    seen, total = set(), 0
    for first, last, month in ranges:
        key = (first, last)
        if key in seen or last < first:
            continue
        seen.add(key)
        df = compute(first, last)
        if df.empty:
            print(f"metrics {first:%Y-%m-%d}..{last:%Y-%m-%d}: nothing")
        else:
            st.write("metrics_daily", df[["zone", "day", "metric", "value", "version", "fetched"]])
            total += len(df)
        if month:  # computed in full from finished backfill data: don't redo until the backfill rewrites the month
            state[month] = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
            st.write_json("metrics_state.json", state)
        if df.empty:
            continue
        print(f"metrics {first:%Y-%m-%d}..{last:%Y-%m-%d}: {len(df)} rows, {df['zone'].nunique()} zones, {df['metric'].nunique()} metrics")
    print(f"done: {total} rows written")


if __name__ == "__main__":
    main()
