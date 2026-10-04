"""Copy the data store from one backend to another and verify it (spec 2 step 1; run once before the Render cutover).

    python tools/store_migrate.py --from github --to s3 [--dry-run] [--only da_price,flows] [--verify-only]

Environment: the target's settings (STORE_BUCKET, STORE_S3_ENDPOINT, credentials; or STORE_DIR for a local copy) and,
for the GitHub source, GH_TOKEN. Copies every asset of the source that is missing or different in the target (compared
by size and MD5), never deletes anything, then verifies: every Parquet file is read on both sides and the row counts
must match. Prints one line per file and a summary table per dataset. Safe to re-run; it only fills gaps.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402

from common import store as ST  # noqa: E402


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()  # noqa: S324  (integrity check, not security)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, choices=["github", "s3", "local"])
    ap.add_argument("--to", dest="dst", required=True, choices=["github", "s3", "local"])
    ap.add_argument("--only", help="comma-separated dataset names (default: everything, incl. json state files)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-only", action="store_true", help="skip the copy, only compare")
    a = ap.parse_args(argv)
    if a.src == a.dst:
        ap.error("--from and --to must differ")
    src, dst = ST.Store(a.src), ST.Store(a.dst)
    only = set(a.only.split(",")) if a.only else None

    def dataset_of(name: str) -> str:
        return name.rsplit("_", 1)[0] if name.endswith(".parquet") else "(json)"

    names = sorted(n for n in src.assets(refresh=True) if not n.startswith("tmp-") and (only is None or dataset_of(n) in only))
    print(f"{a.src} -> {a.dst}: {len(names)} files" + (" (dry run)" if a.dry_run else ""))
    have = dst.assets(refresh=True)
    copied = skipped = 0
    if not a.verify_only:
        for n in names:
            data = src._download(n)
            if data is None:
                print(f"  {n}: unreadable at source, skipped")
                continue
            cur = dst._download(n) if n in have else None
            if cur is not None and len(cur) == len(data) and md5(cur) == md5(data):
                skipped += 1
                continue
            print(f"  {n}: {len(data) / 1e6:.2f} MB {'(would copy)' if a.dry_run else '-> copied'}")
            if not a.dry_run:
                dst._upload(n, data)
            copied += 1
        print(f"copied {copied}, already identical {skipped}")
        if a.dry_run:
            return 0
    # verify row counts per Parquet file
    rows = defaultdict(lambda: [0, 0, 0])  # dataset -> [files, rows src, rows dst]
    bad = []
    ST._MEM.clear()
    dst.assets(refresh=True)
    for n in names:
        if not n.endswith(".parquet"):
            continue
        s_b, d_b = src._download(n), dst._download(n)
        ns = len(pd.read_parquet(io.BytesIO(s_b))) if s_b else -1
        nd = len(pd.read_parquet(io.BytesIO(d_b))) if d_b else -1
        r = rows[dataset_of(n)]
        r[0] += 1; r[1] += max(ns, 0); r[2] += max(nd, 0)
        if ns != nd:
            bad.append((n, ns, nd))
    print(f"\n{'dataset':14s} {'files':>5s} {'rows source':>12s} {'rows target':>12s}")
    for d, (f, s_, d_) in sorted(rows.items()):
        print(f"{d:14s} {f:5d} {s_:12,d} {d_:12,d}" + ("" if s_ == d_ else "   <-- differs"))
    if bad:
        print(f"\n{len(bad)} file(s) differ:")
        for n, ns, nd in bad:
            print(f"  {n}: source {ns} rows, target {nd} rows")
        return 1
    print("\nverified: every Parquet file has the same row count on both sides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
