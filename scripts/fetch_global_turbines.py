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
import sys
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
ZIP = ROOT / "data" / "raw" / "global_offshore_wind_turbines_2021.zip"


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
    ZIP.write_bytes(r.content)  # keep the original; conversion below can also be re-run locally
    try:
        convert(r.content, log)
    except Exception:
        import traceback
        log.append(traceback.format_exc())
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))


def convert(content: bytes, log: list[str]) -> None:
    """Shapefile -> CSV. Name fields are cp1252 (the unused lat/lon text columns hold GBK degree signs); positions come from the point geometry (the lat/lon
    attribute columns are degree-minute-second strings)."""
    z = zipfile.ZipFile(io.BytesIO(content))
    log.append(f"zip {len(content)} bytes")
    names = z.namelist()
    shp = next(n for n in names if n.lower().endswith(".shp") and "__MACOSX" not in n)
    base = shp[:-4]
    get = lambda ext: io.BytesIO(z.read(next(n for n in names if n.lower() == (base + ext).lower())))
    sf = shapefile.Reader(shp=get(".shp"), dbf=get(".dbf"), shx=get(".shx"), encoding="cp1252", encodingErrors="replace")
    fields = [f[0] for f in sf.fields[1:]]
    log.append(f"{shp}: {len(sf)} records, fields {fields}")
    cols = ["lon", "lat", "country", "project", "owner", "project_mw", "first_seen", "owfid"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        n = 0
        for shape, rec in zip(sf.iterShapes(), sf.iterRecords()):
            d = dict(zip(fields, rec))
            x, y = shape.points[0]
            ym = [int(v) for v in str(d.get("yearmonth") or "").replace("-", "/").split("/") if v.strip().isdigit()]
            w.writerow([round(x, 6), round(y, 6), (d.get("country") or "").strip(), (d.get("p_name_4c") or "").strip(),
                        (d.get("o_name_4c") or "").strip(), (d.get("capacity4c") or "").strip(),
                        f"{ym[0]}-{ym[1]:02d}" if len(ym) >= 2 else (str(ym[0]) if ym else ""), d.get("owfid")])
            n += 1
    log.append(f"wrote {n} rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--local":  # convert the committed zip without downloading
        lg: list[str] = []
        convert(ZIP.read_bytes(), lg)
        print("\n".join(lg))
    else:
        main()
