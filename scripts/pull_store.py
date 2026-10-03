"""Download the data store (the `store` release assets) to a local folder, optionally as CSV.

    python scripts/pull_store.py                         # metrics_daily -> <home>/gridecon-store/, plus metrics_daily.csv
    python scripts/pull_store.py --datasets metrics_daily da_price load
    python scripts/pull_store.py --all                   # every asset (several hundred MB once the backfill is done)
    python scripts/pull_store.py --out D:/data/store

The store lives in a GitHub release (not in git), so `git pull` never brings it. The repo is public, so no token is
needed; set GITHUB_TOKEN to lift the anonymous rate limit. Files already downloaded with the same size are skipped.
Do not put the folder inside OneDrive (sync of big Parquet files, and git/venv trouble): the script refuses unless --force.
Then:   import pandas as pd, glob
        df = pd.concat(pd.read_parquet(f) for f in glob.glob("<out>/metrics_daily_*.parquet"))
        wide = df.pivot_table(index=["zone", "day"], columns="metric", values="value")
Or point the repo's code at it:  STORE_DIR=<out> python -m newsletter.build
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

REPO = os.environ.get("GITHUB_REPOSITORY", "erik-iida/energy-infra")
TAG = os.environ.get("STORE_TAG", "store")


def list_assets() -> list[dict]:
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h, timeout=60)
    r.raise_for_status()
    return r.json()["assets"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="*", default=["metrics_daily"], help="dataset names, e.g. metrics_daily da_price")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=str(Path.home() / "gridecon-store"))
    ap.add_argument("--force", action="store_true", help="allow a folder inside OneDrive")
    ap.add_argument("--no-csv", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser()
    if "onedrive" in str(out.resolve()).lower() and not a.force:
        sys.exit(f"{out} is inside OneDrive: choose another folder with --out (or --force).")
    out.mkdir(parents=True, exist_ok=True)
    want = [x for x in list_assets()
            if not x["name"].startswith("tmp-")
            and (a.all or re.sub(r"_\d{4}-\d{2}\.parquet$|\.json$", "", x["name"]) in a.datasets)]
    if not want:
        sys.exit("no matching assets in the release")
    for x in want:
        p = out / x["name"]
        if p.exists() and p.stat().st_size == x["size"]:
            continue
        r = requests.get(x["browser_download_url"], timeout=300)
        r.raise_for_status()
        p.write_bytes(r.content)
        print(f"{x['name']}  {x['size'] / 1e6:.2f} MB")
    print(f"{len(want)} files in {out}")
    if not a.no_csv:
        for ds in a.datasets:
            parts = sorted(out.glob(f"{ds}_*.parquet"))
            if ds == "metrics_daily" and parts:
                df = pd.concat((pd.read_parquet(f) for f in parts), ignore_index=True).sort_values(["zone", "day", "metric"])
                df.to_csv(out / "metrics_daily.csv", index=False)
                print(f"metrics_daily.csv: {len(df)} rows ({df['zone'].nunique()} zones, {df['metric'].nunique()} metrics, "
                      f"{df['day'].min():%Y-%m-%d} .. {df['day'].max():%Y-%m-%d})")


if __name__ == "__main__":
    main()
