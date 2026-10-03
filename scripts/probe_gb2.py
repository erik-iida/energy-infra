"""Probe of the open upstreams behind the paid 'Energy Dashboard' GB API: BMRS per-unit output (B1610), BM units,
forecasts, NESO data portal (historic mix, day-ahead forecasts), National Gas data portal, Carbon Intensity, REPD.
Logs status, row shapes and licence hints. No keys. Commits its log."""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "gbie" / "probe2_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
day = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")
iso = lambda d: d.strftime("%Y-%m-%dT%H:%MZ")
EL = "https://data.elexon.co.uk/bmrs/api/v1"
out = [f"probe2 at {iso(now)}"]


def get(name, url, params=None, show=600, rows_key="data"):
    t0 = time.time()
    try:
        r = requests.get(url, params=params, headers=UA, timeout=60)
    except Exception as e:
        out.append(f"=== {name}: ERROR {type(e).__name__}: {str(e)[:200]}")
        return None
    out.append(f"=== {name}: HTTP {r.status_code} {r.headers.get('content-type', '')[:40]} {len(r.content)} B in {time.time() - t0:.1f}s")
    out.append(f"    url: {r.url[:260]}")
    try:
        j = r.json()
    except Exception:
        out.append("    body: " + re.sub(r"\s+", " ", r.text[:show]))
        return r
    rows = j.get(rows_key) if isinstance(j, dict) and rows_key in j else j
    if isinstance(rows, list) and rows:
        out.append(f"    rows: {len(rows)}; first: {json.dumps(rows[0])[:450]}")
    else:
        out.append("    json: " + json.dumps(j)[:show])
    return j


# ---- Elexon: what exists (paths), then the candidates
try:
    spec = requests.get(f"{EL}/../../api/v1/openapi.json".replace("/api/v1/../../api/v1", "/api/v1"), headers=UA, timeout=60).json()
except Exception:
    spec = None
if not spec:
    for u in ("https://data.elexon.co.uk/bmrs/api/v1/openapi.json", "https://data.elexon.co.uk/swagger/v1/swagger.json"):
        try:
            spec = requests.get(u, headers=UA, timeout=60).json()
            break
        except Exception as e:
            out.append(f"openapi {u}: {e}")
if spec:
    paths = sorted(spec.get("paths", {}))
    out.append(f"=== Elexon openapi: {len(paths)} paths; info: {json.dumps(spec.get('info', {}))[:400]}")
    key = re.compile(r"(?i)forecast|unit|b1610|bmunit|reference|physical|PN|MEL|MIL|windfor|NDF|TSDF|availab|REMIT|price")
    for p in paths:
        if key.search(p):
            out.append("    " + p)

get("BM units reference", f"{EL}/reference/bmunits/all", show=400)
get("B1610 dataset (settlement date)", f"{EL}/datasets/B1610", {"settlementDate": day(2), "settlementPeriod": 20, "format": "json"})
get("B1610 dataset (from/to)", f"{EL}/datasets/B1610", {"from": iso(now - timedelta(days=2, hours=2)), "to": iso(now - timedelta(days=2)), "format": "json"})
get("B1610 stream", f"{EL}/datasets/B1610/stream", {"from": iso(now - timedelta(days=2, hours=2)), "to": iso(now - timedelta(days=2)), "bmUnit": "T_SGRWO-1"})
get("B1610 per-unit endpoint", f"{EL}/generation/actual/per-unit", {"settlementDate": day(2), "settlementPeriod": 20, "format": "json"})
get("PN (physical notifications)", f"{EL}/datasets/PN", {"from": iso(now - timedelta(hours=3)), "to": iso(now), "bmUnit": "T_SGRWO-1", "format": "json"})
get("Wind forecast latest", f"{EL}/forecast/generation/wind/latest", {"format": "json"})
get("Wind+solar day-ahead forecast", f"{EL}/forecast/generation/wind-and-solar/day-ahead", {"format": "json"})
get("Demand day-ahead forecast", f"{EL}/forecast/demand/day-ahead", {"format": "json"})
get("Demand total day-ahead", f"{EL}/forecast/demand/total/day-ahead", {"format": "json"})
get("WINDFOR", f"{EL}/datasets/WINDFOR", {"publishDateTimeFrom": iso(now - timedelta(hours=6)), "publishDateTimeTo": iso(now), "format": "json"})
get("NDF", f"{EL}/datasets/NDF", {"publishDateTimeFrom": iso(now - timedelta(hours=24)), "publishDateTimeTo": iso(now), "format": "json"})
get("TSDF", f"{EL}/datasets/TSDF", {"publishDateTimeFrom": iso(now - timedelta(hours=24)), "publishDateTimeTo": iso(now), "format": "json"})
get("Generation availability (UOU2T14D)", f"{EL}/datasets/UOU2T14D", {"publishDateTimeFrom": iso(now - timedelta(hours=6)), "publishDateTimeTo": iso(now), "format": "json"})
get("REMIT messages", f"{EL}/remit/list/by-publish", {"from": iso(now - timedelta(hours=6)), "to": iso(now), "format": "json"})
get("System prices (SSP/SBP)", f"{EL}/balancing/settlement/system-prices/{day(1)}", {"format": "json"}, show=200)
get("Market index MID", f"{EL}/datasets/MID", {"from": iso(now - timedelta(days=1)), "to": iso(now), "format": "json"}, show=200)

# ---- Carbon Intensity (CC BY 4.0 per its docs)
CI = "https://api.carbonintensity.org.uk"
get("CI intensity range", f"{CI}/intensity/{day(2)}T00:00Z/{day(1)}T00:00Z", rows_key="data")
get("CI generation range", f"{CI}/generation/{day(1)}T00:00Z/{day(1)}T03:00Z")
get("CI regional now", f"{CI}/regional", show=500)
get("CI factors", f"{CI}/intensity/factors", show=400)

# ---- NESO data portal (CKAN)
NE = "https://api.neso.energy/api/3/action"
for q in ("historic generation mix", "day ahead demand forecast", "day ahead wind forecast", "embedded wind solar", "balancing services interconnector", "demand data update", "carbon intensity"):
    j = get(f"NESO package_search '{q}'", f"{NE}/package_search", {"q": q, "rows": 6}, show=300, rows_key="__none__")
    try:
        for p in j["result"]["results"]:
            out.append(f"    pkg: {p['name']} | {p['title']} | licence={p.get('license_id')} | resources={[ (r['name'], r['format']) for r in p['resources']][:8]}")
    except Exception:
        pass
get("NESO licence list", f"{NE}/license_list", show=300)
try:
    r = requests.get("https://www.neso.energy/data-portal/neso-open-licence", headers=UA, timeout=60)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    out.append(f"=== NESO open licence page HTTP {r.status_code}: {t[:700]}")
except Exception as e:
    out.append(f"=== NESO licence page: ERROR {e}")

# ---- National Gas data portal
for u, p in (("https://data.nationalgas.com/", None),
             ("https://data.nationalgas.com/api/find-gas-data-download", {"applicableFor": "Y", "dateFrom": day(3), "dateTo": day(1), "dateType": "GASDAY", "latestFlag": "Y", "ids": "PUBOBJ1660", "formatType": "json"}),
             ("https://data.nationalgas.com/api/gas-system-status", None),
             ("https://data.nationalgas.com/find-gas-data-download", None)):
    get(f"NationalGas {u.split('.com')[1] or '/'}", u, p, show=500)
try:
    r = requests.get("https://data.nationalgas.com/", headers=UA, timeout=60)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    for m in list(re.finditer(r"(?i)licen[cs]e|open government|terms|api|PUBOBJ", t))[:8]:
        out.append("    natgas hint: " + t[max(0, m.start() - 100): m.end() + 160])
except Exception as e:
    out.append(f"natgas page: {e}")

# ---- REPD (GOV.UK content API lists the current CSV)
j = get("REPD GOV.UK content", "https://www.gov.uk/api/content/government/publications/renewable-energy-planning-database-monthly-extract", show=100)
try:
    for d in j["details"]["attachments"]:
        out.append(f"    attachment: {d.get('title')} | {d.get('url')} | {d.get('content_type')} | {d.get('file_size')}")
    out.append(f"    licence: {j.get('details', {}).get('licence') or j.get('links', {}).get('organisations')}")
except Exception as e:
    out.append(f"    REPD parse: {e}")
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2500])
