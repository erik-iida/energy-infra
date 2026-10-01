"""Download the Global Offshore Wind Turbine Dataset (Zhang et al., figshare 13280252, CC0) and convert it to CSV.

    python scripts/fetch_global_turbines.py

Writes data/raw/global_turbines.csv (one row per turbine, all shapefile attributes plus lat/lon) and
data/raw/global_turbines_log.txt (zip contents and fields). Runs on GitHub Actions (global-turbines workflow);
the cloud build environment can't reach figshare.

Source: Zhang, T., Tian, B., Sengupta, D., Zhang, L., Si, Y. (2021) Global offshore wind turbine dataset.
Scientific Data 8, 191. https://doi.org/10.6084/m9.figshare.13280252 (CC0). Turbines detected in Sentinel-1
SAR imagery, 2015-2019, with country, sea area and the year/month a turbine first appears.
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import requests
import shapefile  # pyshp

ROOT = Path(__file__).resolve().parents[1]
URL = "https://ndownloader.figshare.com/files/32822453"
API = "https://api.figshare.com/v2/file/download/32822453"
OUT = ROOT / "data" / "raw" / "global_turbines.csv"
LOG = ROOT / "data" / "raw" / "global_turbines_log.txt"


def main() -> None:
    log = []
    r = None
    for url in (URL, API):
        for ua in ("offshore-wake-monitor/1.0 (+https://github.com/erik-iida/energy-infra)",
                   "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"):
            try:
                q = requests.get(url, timeout=300, headers={"User-Agent": ua, "Accept": "*/*"}, allow_redirects=True)
                log.append(f"{url} [{ua[:20]}] -> HTTP {q.status_code} {q.headers.get('content-type')} "
                           f"{len(q.content)} bytes, final {q.url[:120]}")
                if q.status_code == 200 and q.content[:2] == b"PK":
                    r = q
                    break
                log.append(f"    {q.text[:200]!r}")
            except Exception as ex:
                log.append(f"{url}: {ex!r}")
        if r is not None:
            break
    if r is None:
        LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
        print("\n".join(log))
        return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    log.append(f"zip {len(r.content)} bytes")
    names = z.namelist()
    log += [f"  {n} {z.getinfo(n).file_size}" for n in names]
    shps = [n for n in names if n.lower().endswith(".shp") and not n.startswith("__MACOSX")]
    rows, fields_all = [], []
    for shp in shps:
        base = shp[:-4]
        get = lambda ext: io.BytesIO(z.read(next(n for n in names if n.lower() == (base + ext).lower())))
        sf = shapefile.Reader(shp=get(".shp"), dbf=get(".dbf"), shx=get(".shx"))
        fields = [f[0] for f in sf.fields[1:]]
        log.append(f"{shp}: {len(sf)} records, type {sf.shapeTypeName}, fields {fields}")
        for i, rec in enumerate(sf.iterShapeRecords()):
            if i < 3:
                log.append(f"    sample: {rec.shape.points[:1]} {list(rec.record)}")
            pts = rec.shape.points
            if not pts:
                continue
            lon = sum(p[0] for p in pts) / len(pts)
            lat = sum(p[1] for p in pts) / len(pts)
            d = {"file": Path(shp).name, "lon": round(lon, 6), "lat": round(lat, 6)}
            d.update({k: v for k, v in zip(fields, rec.record)})
            rows.append(d)
        fields_all += [f for f in fields if f not in fields_all]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "lon", "lat"] + fields_all)
        w.writeheader()
        w.writerows(rows)
    log.append(f"wrote {len(rows)} rows -> {OUT.relative_to(ROOT)}")
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
