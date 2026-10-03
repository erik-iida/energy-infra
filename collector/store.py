"""Append-only Parquet store kept as assets of one GitHub release.

Why a release and not git: release assets are not part of the git history, so rewriting a monthly file every
day doesn't make the repository grow. Each dataset is split by UTC month: <dataset>_<YYYY-MM>.parquet.

Safety rules (missed or lost data can't be fetched again for some datasets):
  * write() merges new rows into the existing file by the dataset's key (new rows win, e.g. TSO revisions);
    rows are never dropped, and a merge that would shrink the file is refused.
  * Upload goes to a temporary asset first, then the old asset is deleted and the new one renamed. If a run dies
    in between, read() picks up the temporary asset.

Backends: GitHub release via the `gh` CLI (GH_TOKEN, GITHUB_REPOSITORY), or a local folder when STORE_DIR is
set (tests, or working on a downloaded copy).
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd

TAG = os.environ.get("STORE_TAG", "store")

# dataset -> key columns (rows with the same key are the same observation)
KEYS = {
    "da_price": ["zone", "ts", "res_min", "seq"],
    "gen_actual": ["zone", "ts", "res_min", "psr", "dir"],
    "gen_forecast": ["zone", "ts", "res_min", "psr"],
    "load": ["zone", "ts", "res_min", "kind"],
    "flows": ["from_zone", "to_zone", "ts", "res_min"],
    "farm_hourly": ["farm_id", "ts"],
    "farm_forecast": ["issued", "farm_id", "ts"],
    "farms_meta": ["farm_id"],
    # derived, one row per zone x CET day x metric (newsletter/registry.py defines the metric ids); `version` = registry.VERSION
    "metrics_daily": ["zone", "day", "metric"],
    # GB imbalance (system) prices from Elexon BMRS: zone, ts, res_min, sell, buy (GBP/MWh), niv (MWh), currency
    "imb_price": ["zone", "ts", "res_min"],
    # GB metered output per BM unit (Elexon B1610), mw = average MW of the half hour, signed; run = settlement run type
    "unit_output": ["bm_unit", "ts", "res_min"],
    # GB history since 2009, one wide row per half hour: NESO generation mix + carbon intensity + demand file (collector/gbhist.py)
    "gb_hist": ["zone", "ts", "res_min"],
    # GB forecasts, long format; `issued` = when the forecast was made, `ts` = the half hour it is for
    "gb_forecast": ["series", "issued", "ts", "res_min"],
}
# datasets keyed by month of `ts`; farm_forecast by month of `issued`; farms_meta by month of the snapshot
MONTH_COL = {"farm_forecast": "issued", "metrics_daily": "day", "gb_forecast": "issued"}


def asset_name(dataset: str, month: str) -> str:
    return f"{dataset}_{month}.parquet"


class Store:
    def __init__(self):
        self.local = os.environ.get("STORE_DIR")
        self.repo = os.environ.get("GITHUB_REPOSITORY", "erik-iida/energy-infra")
        self._assets: dict[str, int] | None = None
        if self.local:
            Path(self.local).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ GitHub plumbing
    def _gh(self, *args: str, binary: bool = False, check: bool = True):
        for attempt in range(4):
            r = subprocess.run(["gh", *args], capture_output=True)
            if r.returncode == 0 or not check:
                return r
            err = r.stderr.decode(errors="replace")
            if attempt < 3 and any(s in err for s in ("502", "503", "504", "timeout", "EOF", "connection")):
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"gh {' '.join(args[:2])}: {err[:300]}")

    def _release_id(self) -> int:
        r = self._gh("api", f"repos/{self.repo}/releases/tags/{TAG}", check=False)
        if r.returncode != 0:
            self._gh("release", "create", TAG, "--repo", self.repo, "--title", "Data store",
                     "--notes", "Collected time series (Parquet), written by the collector workflows. "
                                "Do not delete: some series can't be fetched again.",
                     "--prerelease", "--latest=false", check=False)
            r = self._gh("api", f"repos/{self.repo}/releases/tags/{TAG}")
        return json.loads(r.stdout)["id"]

    def assets(self, refresh: bool = False) -> dict[str, int]:
        """asset name -> asset id"""
        if self.local:
            return {p.name: 0 for p in Path(self.local).iterdir() if p.is_file()}
        if self._assets is None or refresh:
            rid = self._release_id()
            r = self._gh("api", "--paginate", f"repos/{self.repo}/releases/{rid}/assets?per_page=100",
                         "--jq", ".[] | [.name, .id] | @tsv")
            self._assets = {}
            for line in r.stdout.decode().splitlines():
                n, i = line.split("\t")
                self._assets[n] = int(i)
        return self._assets

    def _download(self, name: str) -> bytes | None:
        if self.local:
            p = Path(self.local) / name
            return p.read_bytes() if p.exists() else None
        a = self.assets()
        real = name if name in a else ("tmp-" + name if "tmp-" + name in a else None)
        if not real:
            return None
        r = self._gh("release", "download", TAG, "--repo", self.repo, "--pattern", real, "--output", "-")
        if not r.stdout:
            raise RuntimeError(f"download of {real} returned no data")
        return r.stdout

    def _upload(self, name: str, data: bytes) -> None:
        if self.local:
            p = Path(self.local) / name
            tmp = p.with_name("tmp-" + name)
            tmp.write_bytes(data)
            tmp.replace(p)
            return
        a = self.assets(refresh=True)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / ("tmp-" + name)
            tmp.write_bytes(data)
            if "tmp-" + name in a:  # leftover from a run that died: its content is already merged into `data`
                self._gh("api", "-X", "DELETE", f"repos/{self.repo}/releases/assets/{a['tmp-' + name]}")
            self._gh("release", "upload", TAG, str(tmp), "--repo", self.repo)
        a = self.assets(refresh=True)
        new_id = a["tmp-" + name]
        if name in a:
            self._gh("api", "-X", "DELETE", f"repos/{self.repo}/releases/assets/{a[name]}")
        self._gh("api", "-X", "PATCH", f"repos/{self.repo}/releases/assets/{new_id}", "-f", f"name={name}")
        self._assets = None

    # ------------------------------------------------------------ public API
    def read(self, dataset: str, month: str) -> pd.DataFrame | None:
        b = self._download(asset_name(dataset, month))
        return pd.read_parquet(io.BytesIO(b)) if b else None

    def read_json(self, name: str, default=None):
        b = self._download(name)
        return json.loads(b) if b else default

    def write_json(self, name: str, obj) -> None:
        self._upload(name, json.dumps(obj, indent=1, sort_keys=True, default=str).encode())

    def write(self, dataset: str, df: pd.DataFrame, log=print) -> dict[str, int]:
        """Merge rows into the monthly files. Returns {month: rows in the file after the merge}."""
        if df is None or df.empty:
            return {}
        key = KEYS[dataset]
        mcol = MONTH_COL.get(dataset, "ts")
        if dataset == "farms_meta":
            months = pd.Series(pd.Timestamp.now(tz="UTC").strftime("%Y-%m"), index=df.index)
        else:
            months = df[mcol].dt.strftime("%Y-%m")
        out = {}
        for m, part in df.groupby(months):
            old = self.read(dataset, m)
            merged = part if old is None else pd.concat([old, part], ignore_index=True)
            if "fetched" in merged:  # the most recently fetched version of an observation wins
                merged = merged.sort_values("fetched", kind="stable")
            merged = merged.drop_duplicates(subset=key, keep="last").sort_values(key, kind="stable")
            merged = merged.reset_index(drop=True)
            if old is not None and len(merged) < len(old):
                raise RuntimeError(f"{dataset} {m}: merge would shrink {len(old)} -> {len(merged)} rows; refused")
            buf = io.BytesIO()
            merged.to_parquet(buf, index=False, compression="zstd")
            self._upload(asset_name(dataset, m), buf.getvalue())
            added = len(merged) - (0 if old is None else len(old))
            log(f"store: {dataset} {m}: {len(merged)} rows ({added:+d}), {buf.tell() / 1e6:.2f} MB")
            out[m] = len(merged)
        return out


def load(dataset: str, months: list[str]) -> pd.DataFrame:
    """Concatenate monthly files (for analysis and the newsletter)."""
    st = Store()
    parts = [p for m in months if (p := st.read(dataset, m)) is not None]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
