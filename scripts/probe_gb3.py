"""Probe 3: B1610 parameter variants, Elexon API spec, NESO licence/resources, National Gas portal JS endpoints, REPD structure."""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "gbie" / "probe3_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
day = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")
EL = "https://data.elexon.co.uk/bmrs/api/v1"
out = [f"probe3 at {now:%Y-%m-%dT%H:%MZ}"]


def get(name, url, params=None, show=500):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=90)
    except Exception as e:
        out.append(f"=== {name}: ERROR {type(e).__name__}: {str(e)[:150]}")
        return None
    out.append(f"=== {name}: HTTP {r.status_code} {len(r.content)} B  {r.url[:230]}")
    try:
        j = r.json()
    except Exception:
        out.append("    body: " + re.sub(r"\s+", " ", r.text[:show]))
        return r
    rows = j.get("data") if isinstance(j, dict) and "data" in j else j
    if isinstance(rows, list):
        out.append(f"    rows: {len(rows)}" + (f"; first: {json.dumps(rows[0])[:400]}" if rows else ""))
        if rows and isinstance(rows[0], dict) and "bmUnit" in rows[0]:
            out.append(f"    distinct bmUnit: {len({x.get('bmUnit') for x in rows})}")
    else:
        out.append("    json: " + json.dumps(j)[:show])
    return j


# --- B1610 variants (per-unit metered output)
for d in (day(3), day(8), day(30)):
    for sp in (12, 30):
        get(f"B1610 {d} SP{sp}", f"{EL}/datasets/B1610", {"settlementDate": d, "settlementPeriod": sp, "format": "json"}, show=200)
get("B1610 bmUnit filter", f"{EL}/datasets/B1610", {"settlementDate": day(8), "settlementPeriod": 30, "bmUnit": "T_SGRWO-1", "format": "json"}, show=200)
get("B1610 stream whole day", f"{EL}/datasets/B1610/stream", {"from": f"{day(8)}T00:00Z", "to": f"{day(7)}T00:00Z"}, show=200)
get("B1610 stream with settlementPeriodFrom", f"{EL}/datasets/B1610/stream", {"from": f"{day(8)}T00:00Z", "to": f"{day(8)}T06:00Z", "settlementPeriodFrom": 1, "settlementPeriodTo": 12}, show=200)
get("PN settlementDate/period", f"{EL}/datasets/PN", {"settlementDate": day(0), "settlementPeriod": 20, "format": "json"}, show=200)
get("PN stream", f"{EL}/datasets/PN/stream", {"from": f"{day(1)}T12:00Z", "to": f"{day(1)}T13:00Z", "bmUnit": "T_SGRWO-1"}, show=200)
get("AGPT (B1620 gen per type)", f"{EL}/datasets/AGPT", {"publishDateTimeFrom": f"{day(1)}T00:00Z", "publishDateTimeTo": f"{day(1)}T03:00Z", "format": "json"}, show=200)
get("wind-and-solar day-ahead forecast", f"{EL}/forecast/generation/wind-and-solar/day-ahead", {"from": f"{day(1)}T00:00Z", "to": f"{day(0)}T00:00Z", "processType": "Day Ahead", "format": "json"}, show=300)
get("wind latest forecast", f"{EL}/forecast/generation/wind/latest", {"from": f"{day(0)}T00:00Z", "to": f"{day(-1)}T00:00Z", "format": "json"}, show=300)
get("wind history forecast", f"{EL}/forecast/generation/wind/history", {"from": f"{day(3)}T00:00Z", "to": f"{day(2)}T00:00Z", "format": "json"}, show=300)

# --- Elexon spec
for u in ("https://data.elexon.co.uk/bmrs/api/v1/swagger/v1/swagger.json", "https://data.elexon.co.uk/swagger/v1/swagger.json",
          "https://bmrs.elexon.co.uk/api-documentation", "https://data.elexon.co.uk/bmrs/api/v1/openapi/v1.json"):
    try:
        r = requests.get(u, headers=UA, timeout=60)
        out.append(f"spec {u}: {r.status_code} {len(r.content)} B {r.headers.get('content-type')}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            j = r.json()
            ps = sorted(j.get("paths", {}))
            out.append(f"    {len(ps)} paths")
            for p in ps:
                if re.search(r"(?i)forecast|per-unit|unit|physical|b16|generation|windfor|reference", p):
                    out.append("    " + p)
            break
    except Exception as e:
        out.append(f"spec {u}: {e}")

# --- NESO: licence + resource URLs + datastore access
NE = "https://api.neso.energy/api/3/action"
j = get("NESO license_list", f"{NE}/license_list", show=1200)
for pk in ("historic-generation-mix", "day-ahead-wind-forecast", "embedded-wind-and-solar-forecasts", "daily-demand-update", "historic-demand-data"):
    j = get(f"NESO package_show {pk}", f"{NE}/package_show", {"id": pk}, show=100)
    try:
        res = j["result"]
        out.append(f"    licence_title={res.get('license_title')} url={res.get('license_url')} modified={res.get('metadata_modified')}")
        for r in res["resources"][:14]:
            out.append(f"    res: {r['id']} | {r['name']} | {r['format']} | datastore={r.get('datastore_active')} | {r.get('url')}")
    except Exception as e:
        out.append(f"    parse: {e}")
# one datastore query to confirm API access (SQL-free)
get("NESO datastore_search historic gen mix", f"{NE}/datastore_search", {"resource_id": "f93d1835-75bc-43e5-84ad-12472b180a98", "limit": 2}, show=500)
try:
    r = requests.get("https://www.neso.energy/data-portal/neso-open-licence", headers=UA, timeout=60)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    i = t.find("Licence")
    out.append("NESO licence text: " + t[max(0, i - 50): i + 2500])
except Exception as e:
    out.append(f"NESO licence page: {e}")

# --- National Gas: find JS bundles and API paths
try:
    r = requests.get("https://data.nationalgas.com/", headers=UA, timeout=60)
    scripts = re.findall(r'src="([^"]+\.js)"', r.text)
    out.append(f"=== NationalGas scripts: {scripts}")
    for s in scripts[:4]:
        u = s if s.startswith("http") else "https://data.nationalgas.com" + (s if s.startswith("/") else "/" + s)
        js = requests.get(u, headers=UA, timeout=90).text
        out.append(f"    {u}: {len(js)} chars")
        for m in sorted(set(re.findall(r'["\'`](/?api/[A-Za-z0-9_\-/{}$.?=&]+)["\'`]', js)))[:40]:
            out.append(f"      api path: {m}")
        for m in sorted(set(re.findall(r'https?://[A-Za-z0-9_.\-/]*(?:api|nationalgas)[A-Za-z0-9_.\-/]*', js)))[:20]:
            out.append(f"      url: {m}")
        for m in list(re.finditer(r"(?i)licen[cs]e|open government|PUBOBJ\d+", js))[:6]:
            out.append("      hint: " + js[max(0, m.start() - 60): m.end() + 100].replace("\n", " "))
except Exception as e:
    out.append(f"NationalGas: {e}")
for u, p in (("https://data.nationalgas.com/api/find-gas-data-download", {"applicableFor": "Y", "dateFrom": day(3), "dateTo": day(1), "dateType": "GASDAY", "latestFlag": "Y", "ids": "PUBOBJ1660", "formatType": "json"}),
             ("https://data.nationalgas.com/api/find-gas-data-download", {"applicableFor": "Y", "dateFrom": f"{day(3)}", "dateTo": f"{day(1)}", "dateType": "GASDAY", "latestFlag": "Y", "ids": "PUBOBJ1660", "formatType": "csv"}),
             ("https://data.nationalgas.com/api/find-gas-data-download", {"applicableFor": "Y", "dateFrom": f"{day(3)}", "dateTo": f"{day(1)}", "dateType": "GASDAY", "latestFlag": "Y", "ids": "PUBOBJ1660"}),
             ("https://data.nationalgas.com/api/gas-system-status", None)):
    get("NationalGas " + str(p and p.get("formatType")), u, p, show=300)

# --- REPD: full structure
j = get("REPD content", "https://www.gov.uk/api/content/government/publications/renewable-energy-planning-database-monthly-extract", show=10)
if isinstance(j, dict):
    out.append("    top keys: " + str(list(j)))
    out.append("    details keys: " + str(list(j.get("details", {}))))
    out.append("    details: " + json.dumps(j.get("details", {}))[:1800])
    out.append("    links: " + json.dumps(j.get("links", {}))[:600])
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2000])
