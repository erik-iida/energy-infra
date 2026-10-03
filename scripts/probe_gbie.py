"""One-off probe of the open GB and Ireland sources (Elexon BMRS Insights, PV_Live, Carbon Intensity, EirGrid Smart Grid
Dashboard): status, row shapes, units and licence hints for the collector. No keys involved. Commits its log."""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "gbie" / "probe_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
a, b = now - timedelta(hours=6), now
iso = lambda d: d.strftime("%Y-%m-%dT%H:%MZ")
EL = "https://data.elexon.co.uk/bmrs/api/v1"
out = [f"probe at {iso(now)}"]


def get(name, url, params=None, show=700):
    t0 = time.time()
    try:
        r = requests.get(url, params=params, headers=UA, timeout=60)
    except Exception as e:
        out.append(f"=== {name}: ERROR {type(e).__name__}: {str(e)[:200]}")
        return None
    out.append(f"=== {name}: HTTP {r.status_code} {r.headers.get('content-type', '')} {len(r.content)} B in {time.time() - t0:.1f}s")
    out.append(f"    url: {r.url[:230]}")
    lic = {k: v for k, v in r.headers.items() if k.lower() in ("x-ratelimit-limit", "x-ratelimit-remaining", "link", "license", "x-license")}
    if lic:
        out.append(f"    headers: {lic}")
    try:
        j = r.json()
    except Exception:
        out.append("    body: " + r.text[:show].replace("\n", " "))
        return None
    rows = j.get("data") if isinstance(j, dict) and "data" in j else j
    if isinstance(rows, list) and rows:
        out.append(f"    rows: {len(rows)}; first: {json.dumps(rows[0])[:400]}")
        if isinstance(rows[0], dict):
            for k in ("fuelType", "psrType", "businessType", "interconnectorName"):
                if k in rows[0]:
                    out.append(f"    distinct {k}: {sorted({str(x.get(k)) for x in rows})}")
    else:
        out.append("    json: " + json.dumps(j)[:show])
    return j


# --- Elexon BMRS Insights: generation by fuel, wind and solar, demand, prices, interconnectors
for ds in ("FUELHH", "FUELINST", "B1630", "INDO", "ITSDO", "TSDF", "MID"):
    get(f"Elexon dataset {ds} (publish window)", f"{EL}/datasets/{ds}", {"publishDateTimeFrom": iso(a), "publishDateTimeTo": iso(b), "format": "json"})
get("Elexon MID (settlement date range)", f"{EL}/datasets/MID", {"from": iso(now - timedelta(days=1)), "to": iso(now), "format": "json"})
get("Elexon demand outturn", f"{EL}/demand/outturn", {"settlementDateFrom": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
                                                      "settlementDateTo": now.strftime("%Y-%m-%d"), "format": "json"})
get("Elexon wind+solar actual per type", f"{EL}/generation/actual/per-type/wind-and-solar",
    {"from": iso(now - timedelta(days=1)), "to": iso(now), "format": "json"})
get("Elexon system prices", f"{EL}/balancing/settlement/system-prices/{(now - timedelta(days=1)).strftime('%Y-%m-%d')}", {"format": "json"})
get("Elexon openapi (title, licence)", "https://data.elexon.co.uk/bmrs/api/v1/openapi.json", show=300)

# --- PV_Live (Sheffield Solar) and Carbon Intensity
get("PV_Live national", "https://api.pvlive.uk/pvlive/v4/gsp/0", {"start": iso(a), "end": iso(b), "data_format": "json", "extra_fields": "installedcapacity_mwp"})
get("Carbon Intensity generation", "https://api.carbonintensity.org.uk/generation")

# --- EirGrid Smart Grid Dashboard (all-island and ROI)
d0, d1 = (now - timedelta(days=1)).strftime("%d-%b-%Y %H:%M"), (now + timedelta(days=0)).strftime("%d-%b-%Y %H:%M")
for area in ("demandactual", "generationactual", "windactual", "interconnection", "co2intensity", "snsp", "fuelmix"):
    for region in ("ALL", "ROI"):
        get(f"EirGrid {area} {region}", "https://www.smartgriddashboard.com/DashboardService.svc/data",
            {"area": area, "region": region, "datefrom": d0, "dateto": d1}, show=500)
try:
    r = requests.get("https://www.smartgriddashboard.com/", headers=UA, timeout=60)
    txt = re.sub(r"<[^>]+>", " ", r.text)
    out.append(f"=== EirGrid dashboard page: HTTP {r.status_code}, {len(r.text)} chars")
    for m in list(re.finditer(r"(?i)licen[cs]e|creative commons|copyright|terms of use|CC BY", txt))[:6]:
        out.append("    licence hint: " + re.sub(r"\s+", " ", txt[max(0, m.start() - 120): m.end() + 200]))
except Exception as e:
    out.append(f"=== EirGrid dashboard page: ERROR {e}")
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:3000])
