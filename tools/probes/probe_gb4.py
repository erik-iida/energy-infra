"""Probe 4: REPD quarterly extract location + columns, NESO historic generation mix columns, Carbon Intensity actual coverage."""
import csv
import io
import json
import re
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[2] / "data" / "raw" / "gbie" / "probe4_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
out = []


def jget(u, **kw):
    try:
        r = requests.get(u, headers=UA, timeout=90, **kw)
        out.append(f"=== {u[:200]} -> {r.status_code} {len(r.content)} B")
        return r
    except Exception as e:
        out.append(f"=== {u[:200]} -> ERROR {e}")
        return None


for slug in ("renewable-energy-planning-database-quarterly-extract", "renewable-energy-planning-database-monthly-extract"):
    r = jget(f"https://www.gov.uk/api/content/government/publications/{slug}")
    if r is not None and r.status_code == 200:
        j = r.json()
        out.append(f"    keys={list(j)} title={j.get('title')} doc_type={j.get('document_type')} redirects={j.get('redirects')}")
        out.append("    details: " + json.dumps(j.get("details", {}))[:1500])
        out.append("    links: " + json.dumps(j.get("links", {}))[:1500])
        for m in re.findall(r'https://assets\.publishing\.service\.gov\.uk/[^"\\ ]+\.csv', json.dumps(j)):
            out.append("    csv: " + m)
    r = jget(f"https://www.gov.uk/government/publications/{slug}")
    if r is not None and r.status_code == 200:
        for m in sorted(set(re.findall(r'https://assets\.publishing\.service\.gov\.uk/[^"\' ]+\.(?:csv|xlsx|ods)', r.text)))[:10]:
            out.append("    page asset: " + m)

# the newest REPD csv, header + a few rows (try the assets seen in search results, newest last)
for u in ("https://assets.publishing.service.gov.uk/media/68a5c7af2a1dfc29763d515c/repd-q2-jul-2025.csv",):
    r = jget(u)
    if r is not None and r.status_code == 200:
        txt = r.content.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(txt)))
        out.append(f"    header: {rows[0]}")
        out.append(f"    row1: {rows[1]}")
        out.append(f"    rows: {len(rows)}")
        tech = {}
        hdr = rows[0]
        if "Technology Type" in hdr:
            i = hdr.index("Technology Type")
            for x in rows[1:]:
                if len(x) > i:
                    tech[x[i]] = tech.get(x[i], 0) + 1
        out.append(f"    tech counts: {tech}")

# NESO historic generation mix: header and first/last rows through the CSV download
r = jget("https://api.neso.energy/dataset/88313ae5-94e4-4ddc-a790-593554d8c6b9/resource/f93d1835-75bc-43e5-84ad-12472b180a98/download/df_fuel_ckan.csv", stream=True)
if r is not None and r.status_code == 200:
    lines = r.content.decode("utf-8-sig").splitlines()
    out.append(f"    lines: {len(lines)}; header: {lines[0]}")
    out.append(f"    first: {lines[1]}")
    out.append(f"    last: {lines[-1]}")
r = jget("https://api.neso.energy/api/3/action/datastore_search", params={"resource_id": "f93d1835-75bc-43e5-84ad-12472b180a98", "limit": 1})
if r is not None and r.status_code == 200:
    out.append("    fields: " + json.dumps([(f["id"], f.get("info", {}).get("unit")) for f in r.json()["result"]["fields"]]))

# Carbon Intensity: actual + factors coverage for a 14-day window and for 2018
for a, b in (("2018-01-01T00:00Z", "2018-01-03T00:00Z"), ("2025-01-01T00:00Z", "2025-01-15T00:00Z")):
    r = jget(f"https://api.carbonintensity.org.uk/intensity/{a}/{b}")
    if r is not None and r.status_code == 200:
        d = r.json().get("data", [])
        out.append(f"    rows {len(d)}; first {d[0] if d else None}")
    elif r is not None:
        out.append("    body: " + r.text[:200])
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2000])
