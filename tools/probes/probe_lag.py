"""Probe (Actions): publication lag of A75 actual generation per zone, measured with the collector's own parser
(curve type A03 forward-filled), window today-4d .. today+2 like the daily job. Writes data/raw/entsoe/probe_lag_log.txt."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pandas as pd
from collector import collect as c

LOG = Path(__file__).resolve().parents[2] / "data" / "raw" / "entsoe" / "probe_lag_log.txt"
now = datetime.now(timezone.utc)
today = now.replace(hour=0, minute=0, second=0, microsecond=0)
data, calls, errors = c.fetch_window(today - timedelta(days=4), today + timedelta(days=2), borders=[])
out = [f"run {now:%Y-%m-%d %H:%M} UTC, {calls} calls, {len(errors)} errors", "errors: " + "; ".join(errors[:8])]
out.append(f"late zones (newest gen_actual older than 6 h): {c.late_zones(data)}")
out.append(f"seq dropped: {c.seq_note()}")
ga = data["gen_actual"]
for z in ("RO", "MK", "AL", "BG", "HU", "DE-LU"):
    d = ga[(ga.zone == z) & (ga.dir == "gen")]
    out.append(f"\n{z}: newest {d.ts.max()} (lag {(pd.Timestamp(now) - d.ts.max()).total_seconds() / 3600:.1f} h)")
    if d.empty:
        continue
    d = d.assign(day=d.ts.dt.strftime("%m-%d"))
    for day, g in d.groupby("day"):
        per = g.groupby("psr").ts.nunique()
        out.append(f"  {day}: {g.ts.nunique()} distinct timestamps, per psr min {per.min()} max {per.max()}; res {sorted(g.res_min.unique())}")
    per = d.groupby("psr").ts.max()
    out.append("  newest per psr: " + ", ".join(f"{k}={v:%d %H:%M}" for k, v in per.items()))
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out))
