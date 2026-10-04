"""High-voltage grid for the map: the PyPSA-Eur prebuilt network from OpenStreetMap (Xiong et al., Zenodo, ODbL).

    python scripts/fetch_grid.py            # download the latest version and build data/static/grid.json
    python scripts/fetch_grid.py --local    # rebuild from data/raw/grid/*.csv already downloaded

Runs on GitHub Actions (grid workflow); the cloud build environment can't reach Zenodo.

Output data/static/grid.json: {"src", "version", "lines": [[kv, flags, [lon, lat, lon, lat, ...]], ...]}
  kv     nominal voltage in kV (AC lines), or 0 for DC links (HVDC)
  flags  bit 1 = under construction, bit 2 = underground / submarine cable, bits 3+ = circuits (capped at 7)
Geometry simplified to ~300 m and rounded to 0.001 deg. Data (c) OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import requests
from shapely import wkt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import paths as config  # noqa: E402
RAW = ROOT / "data" / "raw" / "grid"
OUT = config.static_file("grid.json")
LOG = RAW / "grid_log.txt"
RECORD = "14144752"  # any version of the record; the API resolves the latest
UA = {"User-Agent": "offshore-wake-monitor/1.0 (+https://github.com/erik-iida/energy-infra)"}
SIMPLIFY_DEG = 0.003
log_lines: list[str] = []
csv.field_size_limit(10 ** 9)


def log(msg: str) -> None:
    print(msg, flush=True)
    log_lines.append(msg)


def download() -> dict:
    meta = requests.get(f"https://zenodo.org/api/records/{RECORD}/versions/latest", headers=UA, timeout=60).json()
    ver = meta.get("metadata", {}).get("version", "?")
    log(f"zenodo record {meta.get('id')} version {ver}, license {meta.get('metadata', {}).get('license')}")
    RAW.mkdir(parents=True, exist_ok=True)
    for f in meta.get("files", []):
        key = f.get("key")
        if key in ("lines.csv", "links.csv"):
            url = f["links"]["self"]
            r = requests.get(url, headers=UA, timeout=600)
            r.raise_for_status()
            (RAW / key).write_bytes(r.content)
            log(f"  {key}: {len(r.content) / 1e6:.1f} MB")
    return {"record": meta.get("id"), "version": ver}


def read_rows(p: Path) -> list[dict]:
    """CSV rows; the geometry is taken as everything from the WKT keyword on, because unquoted commas in the
    free-text 'tags' column shift the later columns."""
    import re
    lines = open(p, encoding="utf-8").read().splitlines()
    head = next(csv.reader([lines[0]]))
    gi = head.index("geometry") if "geometry" in head else len(head)
    log(f"  {p.name} sample: {lines[1][:300]!r}" if len(lines) > 1 else f"  {p.name} empty")
    out = []
    for ln in lines[1:]:
        m = re.search(r"(MULTI)?LINESTRING\s*\(", ln)
        geom = ln[m.start():].strip().strip('"') if m else ""
        if m:
            depth, end = 0, None  # cut at the matching closing bracket
            for k, ch in enumerate(geom):
                depth += ch == "("
                depth -= ch == ")"
                if ch == ")" and depth == 0:
                    end = k + 1
                    break
            geom = geom[:end] if end else geom
        vals = next(csv.reader([ln[:m.start()] if m else ln]))
        d = dict(zip(head[:gi], vals[:gi]))
        d["geometry"] = geom
        out.append(d)
    return out


def truthy(v: str | None) -> bool:
    return str(v).strip().lower() in ("true", "1", "t", "yes")


def build(info: dict) -> None:
    out = []
    for name, dc in (("lines.csv", False), ("links.csv", True)):
        p = RAW / name
        if not p.exists():
            log(f"  {name} missing")
            continue
        rows = read_rows(p)
        if rows:
            log(f"  {name}: {len(rows)} rows, columns {list(rows[0])}")
        skipped = 0
        for r in rows:
            g = r.get("geometry") or ""
            if not g.strip():
                skipped += 1
                continue
            try:
                geom = wkt.loads(g).simplify(SIMPLIFY_DEG, preserve_topology=False)
            except Exception:
                skipped += 1
                continue
            try:
                kv = 0 if dc else round(float(r.get("voltage") or 0))
            except ValueError:
                kv = 0
            if not dc and kv < 100:
                skipped += 1
                continue
            try:
                circ = max(1, min(7, round(float(r.get("circuits") or 1))))
            except ValueError:
                circ = 1
            flags = (1 if truthy(r.get("under_construction")) else 0) | \
                    (2 if truthy(r.get("underground")) or "cable" in str(r.get("type", "")).lower() else 0) | (circ << 2)
            parts = getattr(geom, "geoms", [geom])
            for part in parts:
                cs = [round(v, 3) for xy in part.coords for v in xy[:2]]
                if len(cs) >= 4:
                    out.append([kv, flags, cs])
        log(f"  {name}: kept {sum(1 for o in out if (o[0] == 0) == dc)} segments, skipped {skipped}")
    by = {}
    for kv, _, _ in out:
        by[kv] = by.get(kv, 0) + 1
    log(f"  segments by kV: {dict(sorted(by.items()))}")
    OUT.write_text(json.dumps({"src": "PyPSA-Eur prebuilt network from OpenStreetMap (Xiong et al.), ODbL",
                               **info, "lines": out}, separators=(",", ":")), encoding="utf-8")
    log(f"wrote {OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    try:
        info = {"version": "local"} if "--local" in sys.argv else download()
        build(info)
    finally:
        RAW.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
