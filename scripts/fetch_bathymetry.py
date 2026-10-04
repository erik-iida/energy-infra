"""Fetch a coarse depth grid from EMODnet Bathymetry for the map underlay.

    python scripts/fetch_bathymetry.py

Writes data/static/bathy.png (8-bit greyscale) and data/static/bathy.json (bbox, size, encoding). The browser
colours the grid itself, so the colour scale (depth range) can be changed with a slider.

Encoding of each pixel value v:
    0..200   depth in metres (rounded)
    201..254 deeper: depth = 200 + (v - 200) * 100 m
    255      land or no data

Source: EMODnet Bathymetry Consortium, EMODnet Digital Bathymetry (DTM), CC BY 4.0, via the WCS at
ows.emodnet-bathymetry.eu, resampled by the server. Runs on GitHub Actions (bathymetry workflow); the cloud
build environment can't reach EMODnet.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import paths as config  # noqa: E402
OUT_PNG = config.static_file("bathy.png")
OUT_JSON = config.static_file("bathy.json")
LOG = ROOT / "data" / "raw" / "bathy_log.txt"
WCS = "https://ows.emodnet-bathymetry.eu/wcs"
BBOX = (-20.0, 34.0, 32.0, 66.0)  # west, south, east, north: all European offshore wind seas
RES = 48                           # pixels per degree (1.25 arc-minutes, ~2.3 km N-S)
TILE = 2                           # degrees per request; split further if the server says too much data
UA = {"User-Agent": "offshore-wake-monitor (personal, non-commercial)"}
log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    log_lines.append(msg)


def read_tiff(content: bytes) -> np.ndarray:
    import tifffile

    return np.asarray(tifffile.imread(io.BytesIO(content)), dtype="float64").squeeze()


def read_arcgrid(text: str) -> np.ndarray:
    lines = text.splitlines()
    head, i = {}, 0
    while i < len(lines) and lines[i].split() and lines[i].split()[0].lower() in (
            "ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "dx", "dy",
            "nodata_value"):
        k, v = lines[i].split()[:2]
        head[k.lower()] = float(v)
        i += 1
    a = np.array(" ".join(lines[i:]).split(), dtype="float64").reshape(int(head["nrows"]), int(head["ncols"]))
    if "nodata_value" in head:
        a[a == head["nodata_value"]] = np.nan
    return a


def tile(w: float, s: float, e: float, n: float, px: int, py: int) -> np.ndarray | None:
    base = {"service": "WCS", "version": "1.0.0", "request": "GetCoverage", "coverage": "emodnet:mean",
            "crs": "EPSG:4326", "bbox": f"{w},{s},{e},{n}", "width": px, "height": py}
    for fmt in ("image/tiff", "GeoTIFF", "ArcGrid"):
        for attempt in range(3):
            try:
                r = requests.get(WCS, params={**base, "format": fmt}, headers=UA, timeout=120)
                ct = r.headers.get("content-type", "")
                if r.status_code != 200 or "xml" in ct:
                    if "too much data" in r.text and px >= 2 and py >= 2:
                        return split(w, s, e, n, px, py)
                    log(f"  {w},{s} {fmt}: HTTP {r.status_code} {ct} {r.text[:300]!r}")
                    break  # try the next format
                a = read_arcgrid(r.text) if fmt == "ArcGrid" else read_tiff(r.content)
                if a.shape != (py, px):
                    log(f"  {w},{s} {fmt}: shape {a.shape}, expected {(py, px)}; resampling")
                    yi = (np.arange(py) * a.shape[0] / py).astype(int)
                    xi = (np.arange(px) * a.shape[1] / px).astype(int)
                    a = a[yi][:, xi]
                return a
            except Exception as ex:
                log(f"  {w},{s} {fmt} attempt {attempt + 1}: {ex!r}")
                time.sleep(5 * (attempt + 1))
    return None


def split(w: float, s: float, e: float, n: float, px: int, py: int) -> np.ndarray | None:
    """Fetch a tile as four quadrants (the server limits how much source data one request may read)."""
    mx, my = (w + e) / 2, (s + n) / 2
    hx, hy = px // 2, py // 2
    out = np.full((py, px), np.nan)
    parts = [((w, my, mx, n), (0, 0, hx, hy)), ((mx, my, e, n), (0, hx, px - hx, hy)),
             ((w, s, mx, my), (hy, 0, hx, py - hy)), ((mx, s, e, my), (hy, hx, px - hx, py - hy))]
    got = 0
    for (a, b, c, d), (r0, c0, qx, qy) in parts:
        q = tile(a, b, c, d, qx, qy)
        if q is not None:
            out[r0:r0 + qy, c0:c0 + qx] = q
            got += 1
    return out if got else None


def main() -> int:
    w0, s0, e0, n0 = BBOX
    W, H = int((e0 - w0) * RES), int((n0 - s0) * RES)
    grid = np.full((H, W), np.nan)
    from concurrent.futures import ThreadPoolExecutor

    jobs = []
    lat = n0
    while lat > s0:  # rows from north to south
        lon = w0
        while lon < e0:
            e, s = min(e0, lon + TILE), max(s0, lat - TILE)
            jobs.append((lon, s, e, lat, int(round((e - lon) * RES)), int(round((lat - s) * RES))))
            lon = e
        lat = s
    ok = bad = 0
    with ThreadPoolExecutor(4) as ex:  # a few at a time, to be polite to the server
        for j, a in zip(jobs, ex.map(lambda t: tile(*t), jobs)):
            w, s, e, n, px, py = j
            r0, c0 = int(round((n0 - n) * RES)), int(round((w - w0) * RES))
            if a is None:
                bad += 1
            else:
                grid[r0:r0 + py, c0:c0 + px] = a
                ok += 1
            if (ok + bad) % 22 == 0:
                log(f"{ok + bad}/{len(jobs)} tiles: {ok} ok, {bad} failed")
    valid = np.isfinite(grid) & (grid > -12000) & (grid < 9000)
    log(f"valid cells {valid.mean():.1%}; elevation range {np.nanmin(np.where(valid, grid, np.nan)):.0f}"
        f" to {np.nanmax(np.where(valid, grid, np.nan)):.0f} m")
    if ok == 0:
        log("nothing fetched; files left unchanged")
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return 1
    d = np.where(valid, -grid, -1.0)  # depth, positive down
    v = np.where(d <= 200, np.round(d), np.minimum(254, 200 + np.round((d - 200) / 100)))
    v = np.where(~valid | (d < 0), 255, np.clip(v, 0, 254)).astype("uint8")

    from PIL import Image

    Image.fromarray(v, mode="L").save(OUT_PNG, optimize=True)
    OUT_JSON.write_text(json.dumps({
        "bbox": list(BBOX), "w": W, "h": H, "res_per_deg": RES,
        "encoding": "v<=200: depth m; 201..254: 200+(v-200)*100 m; 255: land/no data",
        "source": "EMODnet Bathymetry Consortium, EMODnet Digital Bathymetry (DTM), CC BY 4.0",
        "fetched": time.strftime("%Y-%m-%d"), "tiles_ok": ok, "tiles_failed": bad}), encoding="utf-8")
    log(f"wrote {OUT_PNG.relative_to(ROOT)} {W}x{H}, {OUT_PNG.stat().st_size / 1e6:.2f} MB")
    LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
