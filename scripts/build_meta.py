"""Write build/data/meta.json: build time, schema version and freshness of every data file the page loads.

    python scripts/build_meta.py [--data DIR ...]     default: build/data and data/static (the first that has a file wins)

The schema numbers here are the data contract (docs/DATA_CONTRACT.md): bump one when a field the page reads is renamed,
removed or changes meaning, and update the page in the same push. `last_data` is the newest data point a file carries
(not the time it was written), so "data N h old" labels can be built from it later. Run by hourly-feed before deploy;
never fails the job (a file that is missing or unreadable is listed with "missing": true).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import paths as config  # noqa: E402

# file (relative to data/) -> schema version (see docs/DATA_CONTRACT.md)
SCHEMAS = {
    "site.json": 1, "feed.json": 1, "zones.json": 1, "capture.json": 1, "gas.json": 1,
    "gie.json": 1, "grid.json": 1, "bathy.json": 1, "browse/index.json": 1, "browse/ts/<zone>.json": 1,
    "browse/capacity.json": 1, "browse/agg.json": 1, "browse/flags.json": 1, "browse/flags/<day>.json": 1, "browse/xflow.json": 1,
    "newsletter/index.json": 1, "meta.json": 1,
}


def _iso(t: float | int | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="minutes")


def last_data(name: str, d) -> str | None:
    """Newest data point in a file, as ISO time (None when the file has no time axis)."""
    try:
        if name == "feed.json":
            h = d.get("hours") or []  # past hours, "YYYY-MM-DDTHH:MMZ"; the last one is "now"
            return h[-1].replace("Z", ":00Z") if h else d.get("generated")
        if name == "browse/xflow.json":
            return _iso(max(p[2] for p in d["pairs"])) if d.get("pairs") else None
        if name == "browse/flags.json":
            return d.get("day")
        if name == "newsletter/index.json":
            return d.get("latest")
        if name == "capture.json":
            return (d.get("months") or [None])[-1]
        if name == "gas.json":
            return (d.get("days") or [None])[-1]
        if name == "gie.json":
            rows = ((d.get("storage") or {}).get("EU") or {}).get("d") or []  # [[day, ...], ...] oldest first
            return rows[-1][0] if rows else None
    except Exception:
        return None
    return None


def build(dirs: list[Path]) -> dict:
    """dirs: where the page's data files are looked up, first match wins (build output, then committed inputs)."""
    def find(rel: str) -> Path:
        for d in dirs:
            if (d / rel).exists():
                return d / rel
        return dirs[0] / rel
    files = {}
    for name, ver in SCHEMAS.items():
        if "<" in name or name == "meta.json":
            continue
        p = find(name)
        if not p.exists():
            files[name] = {"schema": ver, "missing": True}
            continue
        e = {"schema": ver, "bytes": p.stat().st_size}
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                if d.get("generated"):
                    e["generated"] = d["generated"]
                if "schema" in d and d["schema"] != ver:
                    e["schema_in_file"] = d["schema"]  # a writer and this table disagree: the contract test flags it
                ld = last_data(name, d)
                if ld:
                    e["last_data"] = ld
        except Exception as ex:
            e["unreadable"] = type(ex).__name__
        files[name] = e
    tsd, fld = find("browse/ts"), find("browse/flags")
    ts = sorted(tsd.glob("*.json")) if tsd.exists() else []
    files["browse/ts/<zone>.json"] = {"schema": SCHEMAS["browse/ts/<zone>.json"], "count": len(ts)}
    fl = sorted(fld.glob("2*.json")) if fld.exists() else []
    files["browse/flags/<day>.json"] = {"schema": SCHEMAS["browse/flags/<day>.json"], "count": len(fl),
                                        "days": [f.stem for f in fl][-14:]}
    return {"schema": SCHEMAS["meta.json"], "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "contract": "docs/DATA_CONTRACT.md", "files": files}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="*", default=[str(config.BUILD_DATA), str(config.DATA_STATIC)])
    a = ap.parse_args(argv)
    dirs = [Path(d) for d in a.data]
    m = build(dirs)
    dirs[0].mkdir(parents=True, exist_ok=True)
    (dirs[0] / "meta.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    miss = [k for k, v in m["files"].items() if v.get("missing")]
    print(f"meta.json: {len(m['files'])} files" + (f", missing: {', '.join(miss)}" if miss else ""))


if __name__ == "__main__":
    main()
