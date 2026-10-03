"""Probe 5: BM-unit registry by fuel type, B1610 per-unit range queries and latest available day, REPD csv header,
National Gas portal calls (from its JS bundle), NESO resources. No keys. Commits its log."""
import collections
import csv
import io
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "gbie" / "probe5_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
EL = "https://data.elexon.co.uk/bmrs/api/v1"
out = []


def G(u, **kw):
    t0 = time.time()
    try:
        r = requests.get(u, headers=UA, timeout=180, **kw)
    except Exception as e:
        out.append(f"=== {u[:240]} -> ERROR {type(e).__name__} {str(e)[:150]}")
        return None
    out.append(f"=== {r.url[:300]} -> {r.status_code} {len(r.content)} B in {time.time() - t0:.1f}s")
    return r


# 1) BM unit registry
r = G(f"{EL}/reference/bmunits/all")
units = r.json() if r is not None and r.status_code == 200 else []
if units:
    out.append(f"registry rows {len(units)}; keys {list(units[0])}")
    c = collections.Counter((u.get("fuelType"), u.get("bmUnitType")) for u in units)
    out.append("fuelType x bmUnitType: " + json.dumps([[list(k), v] for k, v in c.most_common(40)]))
    cap = collections.defaultdict(float)
    for u in units:
        try:
            cap[u.get("fuelType")] += float(u.get("generationCapacity") or 0)
        except ValueError:
            pass
    out.append("generationCapacity MW by fuelType: " + json.dumps({str(k): round(v) for k, v in cap.items()}))
    for ft in ("WIND", "BATTERY", "PS", "NPSHYD", "CCGT", "NUCLEAR", "BIOMASS", "OTHER", None):
        ex = [u for u in units if u.get("fuelType") == ft][:3]
        out.append(f"  examples {ft}: " + json.dumps([{k: u.get(k) for k in ("elexonBmUnit", "nationalGridBmUnit", "bmUnitName", "leadPartyName", "generationCapacity", "gspGroupId", "interconnectorId", "bmUnitType")} for u in ex]))
    wind = [u["elexonBmUnit"] for u in units if u.get("fuelType") == "WIND"][:5]
else:
    wind = ["T_SGRWO-1", "T_HOWBO-1", "T_MOWEO-1"]

# 2) B1610 per-unit, range, repeated bmUnit params
days = [(datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d") for n in (3, 4, 5, 6, 7, 8, 10)]
for d in days:
    r = G(f"{EL}/datasets/B1610", params={"settlementDate": d, "settlementPeriod": 20, "bmUnit": wind[0], "format": "json"})
    if r is not None and r.status_code == 200:
        rows = r.json().get("data", [])
        out.append(f"    B1610 {d}: rows {len(rows)} runTypes {sorted({x.get('settlementRunType') for x in rows})}")
a = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%dT00:00Z")
b = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%dT00:00Z")
for label, params in (
    ("stream 2 units", [("from", a), ("to", b), ("bmUnit", wind[0]), ("bmUnit", wind[1])]),
    ("stream 1 unit", [("from", a), ("to", b), ("bmUnit", wind[0])]),
    ("non-stream settlementDate range 1 unit", [("settlementDateFrom", a[:10]), ("settlementDateTo", b[:10]), ("bmUnit", wind[0]), ("format", "json")]),
):
    path = "/datasets/B1610/stream" if label.startswith("stream") else "/datasets/B1610"
    r = G(EL + path, params=params)
    if r is not None and r.status_code == 200:
        try:
            j = r.json()
            rows = j.get("data", j) if isinstance(j, dict) else j
            out.append(f"    {label}: rows {len(rows)}; units {sorted({x.get('bmUnit') for x in rows})}; runTypes {dict(collections.Counter(x.get('settlementRunType') for x in rows))}; last {max((x.get('halfHourEndTime') for x in rows), default=None)}")
        except Exception as e:
            out.append(f"    {label}: parse {e}; {r.text[:200]}")
    elif r is not None:
        out.append("    body: " + r.text[:300].replace("\n", " "))
# 40 units in one request: size/time
if len(wind) >= 5:
    r = G(EL + "/datasets/B1610/stream", params=[("from", a), ("to", b)] + [("bmUnit", w) for w in wind])
    if r is not None and r.status_code == 200:
        out.append(f"    5 units 14 days: rows {len(r.json())}")

# 3) REPD csv
r = G("https://assets.publishing.service.gov.uk/media/6a6cbdc00c36759b5ccaa305/REPD_Publication_Q2_2026.csv")
if r is not None and r.status_code == 200:
    txt = r.content.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(txt)))
    out.append(f"REPD rows {len(rows)}; columns {list(rows[0])}")
    tech = collections.Counter(x.get("Technology Type") for x in rows)
    out.append("technology x count: " + json.dumps(tech.most_common(25)))
    st = collections.Counter(x.get("Development Status (short)") for x in rows)
    out.append("status: " + json.dumps(st.most_common(15)))
    for x in [x for x in rows if "Offshore" in (x.get("Technology Type") or "") and x.get("Development Status (short)") == "Operational"][:3]:
        out.append("  offshore example: " + json.dumps(x)[:900])

# 4) National Gas bundle: how the download calls are built
r = G("https://data.nationalgas.com/assets/index-NpP-pJsT.js")
if r is not None and r.status_code == 200:
    js = r.text
    for key in ("find-gas-data-download", "latest-gas-flows-download", "report-table", "find-gas-data-folders", "reports-download"):
        for m in list(re.finditer(re.escape("/api/" + key), js))[:2]:
            out.append(f"  [{key}] " + js[max(0, m.start() - 350): m.end() + 450].replace("\n", " "))
    out.append("  PUBOBJ ids: " + json.dumps(sorted(set(re.findall(r"PUBOB[A-Z0-9]+", js)))[:60]))
for u in ("https://data.nationalgas.com/api/find-gas-data-folders", "https://data.nationalgas.com/api/gas-data-reports-folders",
          "https://data.nationalgas.com/api/latest-gas-flows-download"):
    r = G(u)
    if r is not None:
        out.append("    body: " + r.text[:900].replace("\n", " "))
r = G("https://www.nationalgas.com/our-businesses/operational-data/gas-data-portal/soap-rest-api-transition")
if r is not None and r.status_code == 200:
    t = re.sub(r"<[^>]+>", " ", r.text)
    out.append("  transition page: " + re.sub(r"\s+", " ", t)[:1800])

# 5) NESO resources: historic demand, day-ahead wind, embedded forecasts
for pid in ("historic-demand-data", "day-ahead-wind-forecast", "embedded-wind-and-solar-forecasts", "daily-demand-update"):
    r = G("https://api.neso.energy/api/3/action/package_show", params={"id": pid})
    if r is not None and r.status_code == 200:
        res = r.json()["result"]
        out.append(f"NESO {pid}: licence {res.get('license_title')}; updated {res.get('metadata_modified')}")
        for x in res["resources"][:30]:
            out.append(f"    {x.get('name')} | {x.get('format')} | {x.get('datastore_active')} | {x.get('url')} | {x.get('id')}")
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2500])
