"""Append-only Parquet store kept as assets of one GitHub release.

Why a release and not git: release assets are not part of the git history, so rewriting a monthly file every
day doesn't make the repository grow. Each dataset is split by UTC month: <dataset>_<YYYY-MM>.parquet.

Safety rules (missed or lost data can't be fetched again for some datasets):
  * write() merges new rows into the existing file by the dataset's key (new rows win, e.g. TSO revisions);
    rows are never dropped, and a merge that would shrink the file is refused.
  * Upload goes to a temporary asset first, then the old asset is deleted and the new one renamed. If a run dies
    in between, read() picks up the temporary asset.

Backends (STORE_BACKEND, or inferred: STORE_DIR -> local, STORE_BUCKET -> s3, else github):
  github  assets of one GitHub release via the `gh` CLI (GH_TOKEN, GITHUB_REPOSITORY, tag STORE_TAG). The original.
  s3      any S3-compatible bucket (Cloudflare R2, Backblaze B2, AWS S3): STORE_BUCKET, optional STORE_PREFIX (folder inside
          the bucket, default "store"), STORE_S3_ENDPOINT (R2 / B2 need it), credentials in AWS_ACCESS_KEY_ID /
          AWS_SECRET_ACCESS_KEY (or STORE_S3_KEY / STORE_S3_SECRET), STORE_S3_REGION (default "auto"). Objects are named
          exactly like the release assets, so a bucket is a copy of the release (tools/store_migrate.py).
  local   a folder (STORE_DIR): tests, or working on a downloaded copy.
The same read / write / merge rules apply to all three; only the bytes transport differs.
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


_MEM: dict[str, bytes] = {}  # "<asset id>-<name>" -> bytes, shared by every Store() in this process
_ASSETS: dict[str, dict[str, int]] = {}  # repo -> {asset name: id}, shared; refreshed after every upload


def backend_kind() -> str:
    k = os.environ.get("STORE_BACKEND", "").lower()
    if k in ("github", "s3", "local"):
        return k
    if os.environ.get("STORE_DIR"):
        return "local"
    if os.environ.get("STORE_BUCKET"):
        return "s3"
    return "github"


_S3 = {}  # (endpoint, bucket) -> boto3 client, shared


class Store:
    def __init__(self, kind: str | None = None):
        self.kind = kind or backend_kind()
        self.local = os.environ.get("STORE_DIR") if self.kind == "local" else None
        self.repo = os.environ.get("GITHUB_REPOSITORY", "erik-iida/energy-infra")
        self.bucket = os.environ.get("STORE_BUCKET", "")
        self.prefix = os.environ.get("STORE_PREFIX", "store").strip("/")
        if self.kind == "local":
            if not self.local:
                raise RuntimeError("STORE_DIR not set for the local store backend")
            Path(self.local).mkdir(parents=True, exist_ok=True)
        if self.kind == "s3" and not self.bucket:
            raise RuntimeError("STORE_BUCKET not set for the s3 store backend")

    # ------------------------------------------------------------ S3 plumbing (R2, B2, AWS)
    def _s3(self):
        endpoint = os.environ.get("STORE_S3_ENDPOINT") or None
        key = (endpoint, self.bucket)
        if key not in _S3:
            import boto3  # only needed for this backend
            from botocore.config import Config
            _S3[key] = boto3.client(
                "s3", endpoint_url=endpoint, region_name=os.environ.get("STORE_S3_REGION", "auto"),
                aws_access_key_id=os.environ.get("STORE_S3_KEY") or os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("STORE_S3_SECRET") or os.environ.get("AWS_SECRET_ACCESS_KEY"),
                config=Config(retries={"max_attempts": 5, "mode": "standard"}, s3={"addressing_style": "path"}))
        return _S3[key]

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def _s3_list(self) -> dict[str, str]:
        """object name -> ETag (changes with every upload, so it is the cache version)."""
        out = {}
        pfx = self._key("")
        for page in self._s3().get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=pfx):
            for o in page.get("Contents", []):
                out[o["Key"][len(pfx):]] = o["ETag"].strip('"')
        return out

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

    def assets(self, refresh: bool = False) -> dict:
        """asset name -> version (GitHub: asset id, S3: ETag, local: 0). A new version means a new download."""
        if self.local:
            return {p.name: 0 for p in Path(self.local).iterdir() if p.is_file()}
        if self.kind == "s3":
            k = f"s3:{self.bucket}/{self.prefix}"
            if k not in _ASSETS or refresh:
                _ASSETS[k] = self._s3_list()
            return _ASSETS[k]
        if self.repo not in _ASSETS or refresh:
            rid = self._release_id()
            r = self._gh("api", "--paginate", f"repos/{self.repo}/releases/{rid}/assets?per_page=100",
                         "--jq", ".[] | [.name, .id] | @tsv")
            got = {}
            for line in r.stdout.decode().splitlines():
                n, i = line.split("\t")
                got[n] = int(i)
            _ASSETS[self.repo] = got
        return _ASSETS[self.repo]

    def _download(self, name: str) -> bytes | None:
        """Asset bytes. Cached per asset id (an upload gives the asset a new id, so a cached copy is never stale): in memory
        for this process, and on disk under STORE_CACHE when set, so jobs that read the same months (Data-tab export,
        newsletter drafts) download each file once."""
        if self.local:
            p = Path(self.local) / name
            return p.read_bytes() if p.exists() else None
        for attempt in range(2):
            a = self.assets(refresh=attempt > 0)
            real = name if name in a else ("tmp-" + name if "tmp-" + name in a else None)
            if not real:
                return None
            try:
                return self._fetch(real, a[real])
            except RuntimeError:  # replaced by a collector upload since the listing was read: list again, once
                if attempt:
                    raise
        return None

    def _fetch(self, real: str, asset_id) -> bytes:
        key = f"{asset_id}-{real}"
        if key in _MEM:
            return _MEM[key]
        disk = Path(os.environ["STORE_CACHE"]) / key if os.environ.get("STORE_CACHE") else None
        if disk is not None and disk.exists():
            _MEM[key] = disk.read_bytes()
            return _MEM[key]
        if self.kind == "s3":
            try:
                data = self._s3().get_object(Bucket=self.bucket, Key=self._key(real))["Body"].read()
            except Exception as e:  # noqa: BLE001  (NoSuchKey after a concurrent replace -> caller lists again)
                raise RuntimeError(f"s3 get {real}: {type(e).__name__}") from e
        else:
            r = self._gh("release", "download", TAG, "--repo", self.repo, "--pattern", real, "--output", "-")
            data = r.stdout
        if not data:
            raise RuntimeError(f"download of {real} returned no data")
        _MEM[key] = data
        if disk is not None:
            disk.parent.mkdir(parents=True, exist_ok=True)
            disk.write_bytes(data)
        return data

    def _upload(self, name: str, data: bytes) -> None:
        if self.local:
            p = Path(self.local) / name
            tmp = p.with_name("tmp-" + name)
            tmp.write_bytes(data)
            tmp.replace(p)
            return
        if self.kind == "s3":  # an S3 put is atomic: readers see the old or the new object, never a partial one
            self._s3().put_object(Bucket=self.bucket, Key=self._key(name), Body=data)
            _ASSETS.pop(f"s3:{self.bucket}/{self.prefix}", None)
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
        _ASSETS.pop(self.repo, None)

    # ------------------------------------------------------------ public API
    def months(self, dataset: str) -> list[str]:
        """The months (YYYY-MM, ascending) for which `dataset` has a file in the store."""
        pre, suf = f"{dataset}_", ".parquet"
        return sorted(n[len(pre):-len(suf)] for n in self.assets() if n.startswith(pre) and n.endswith(suf) and len(n) == len(pre) + 7 + len(suf))

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
