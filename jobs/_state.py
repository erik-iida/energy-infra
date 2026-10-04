"""Keep state/ (forecast cache, PyWake result cache, ENTSO-E cache, call counter, fuel cache) between runs when the job
runs on a machine that starts empty every time (Render cron jobs). The files are mirrored to the data store's bucket
under <STORE_PREFIX>-state/ (same credentials as the store). Enabled by STATE_SYNC=1; a no-op otherwise (GitHub Actions
keeps state/ in its own cache).

    pull()  before the job: download every object into STATE_DIR (skips files already present with the same size + ETag)
    push()  after the job: upload files that are new or changed since pull()
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from common import paths


def enabled() -> bool:
    return os.environ.get("STATE_SYNC", "") == "1" and bool(os.environ.get("STORE_BUCKET"))


def _client():
    from common.store import Store
    return Store("s3")._s3()


def _prefix() -> str:
    return os.environ.get("STORE_PREFIX", "store").strip("/") + "-state/"


_seen: dict[str, str] = {}   # relative path -> md5 at pull time


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()  # noqa: S324


def pull(log=print) -> int:
    if not enabled():
        return 0
    s3, bucket, pfx = _client(), os.environ["STORE_BUCKET"], _prefix()
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=pfx):
        for o in page.get("Contents", []):
            rel = o["Key"][len(pfx):]
            if not rel:
                continue
            dst = paths.STATE_DIR / rel
            etag = o["ETag"].strip('"')
            if dst.exists() and dst.stat().st_size == o["Size"] and _md5(dst) == etag:
                _seen[rel] = etag
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())
            _seen[rel] = _md5(dst)
            n += 1
    log(f"state: pulled {n} file(s) from {bucket}/{pfx}")
    return n


def push(log=print) -> int:
    if not enabled():
        return 0
    s3, bucket, pfx = _client(), os.environ["STORE_BUCKET"], _prefix()
    n = 0
    if paths.STATE_DIR.exists():
        for p in paths.STATE_DIR.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(paths.STATE_DIR).as_posix()
            h = _md5(p)
            if _seen.get(rel) == h:
                continue
            s3.put_object(Bucket=bucket, Key=pfx + rel, Body=p.read_bytes())
            _seen[rel] = h
            n += 1
    log(f"state: pushed {n} file(s) to {bucket}/{pfx}")
    return n
