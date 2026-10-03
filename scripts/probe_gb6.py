"""Probe 6: National Gas portal (dataset ids, query parameters, licence text, latest flows), NESO CSV headers,
Carbon Intensity regional history. No keys. Commits its log."""
import collections
import csv
import io
import json
import re
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "gbie" / "probe6_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
out = []


def G(u, **kw):
    try:
        r = requests.get(u, headers=UA, timeout=120, **kw)
    except Exception as e:
        out.append(f"=== {u[:240]} -> ERROR {type(e).__name__} {str(e)[:150]}")
        return None
    out.append(f"=== {r.url[:300]} -> {r.status_code} {len(r.content)} B")
    return r


NG = "https://data.nationalgas.com"
# 1) dataset catalogue: ids + names for flows, storage, demand, prices
r = G(NG + "/api/find-gas-data-folders")
items = []


def walk(n, path):
    if isinstance(n, dict):
        nm = n.get("name")
        if "description" in n and nm:
            items.append((" > ".join(path + [nm]), n.get("description") or ""))
        for c in n.get("children", []) or []:
            walk(c, path + ([nm] if nm else []))
    elif isinstance(n, list):
        for c in n:
            walk(c, path)


if r is not None and r.status_code == 200:
    walk(r.json().get("data"), [])
    out.append(f"catalogue items {len(items)}")
    pat = re.compile(r"(?i)physical flow|instantaneous|linepack|storage|system average price|\bSAP\b|\bSMP\b|demand.*(actual|NTS)|calorific|LNG|interconnector|terminal|entry.*(NTS|physical)")
    n = 0
    for path, desc in items:
        if pat.search(path):
            ids = re.findall(r"PUBOBJ\d+", desc)
            out.append(f"  {path} | {ids} | {desc[:110]}")
            n += 1
            if n >= 90:
                break
# 2) query parameters in the bundle
r = G(NG + "/assets/index-NpP-pJsT.js")
if r is not None and r.status_code == 200:
    js = r.text
    for key in ("applicableFor", "latestFlag", "formatType"):
        for m in list(re.finditer(key, js))[:3]:
            out.append(f"  [{key}] " + js[max(0, m.start() - 500): m.end() + 500].replace("\n", " "))
# 3) licence / terms
for u in ("https://www.nationalgas.com/our-policies/terms-and-conditions",
          "https://www.nationalgas.com/our-businesses/operational-data/gas-data-portal"):
    r = G(u)
    if r is not None and r.status_code == 200:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>", " ", r.text)))
        for m in list(re.finditer(r"(?i)licen[cs]e|re-?use|redistribut|open data|commercial|copyright|permission", t))[:8]:
            out.append("  licence hint: " + t[max(0, m.start() - 200): m.end() + 300])
# 4) latest flows structure
r = G(NG + "/api/latest-gas-flows-download")
if r is not None and r.status_code == 200:
    blocks = collections.OrderedDict()
    rows = list(csv.reader(io.StringIO(r.text)))
    hdr = None
    for row in rows:
        if len(row) > 3 and row[1] == "Published Time" or (row and row[0] and "," not in row[0] and len(row) > 3 and row[2] == "Value"):
            hdr = row[0]
            blocks[hdr] = set()
        elif hdr and row:
            blocks[hdr].add(row[0])
    out.append(f"latest flows: {len(rows)} rows; header sample {rows[0]}")
    for k, v in blocks.items():
        out.append(f"  block '{k}': {sorted(v)[:60]}")
# 5) NESO CSV headers
for name, u in (
    ("historic demand 2025", "https://api.neso.energy/dataset/8f2fe0af-871c-488d-8bad-960426f24601/resource/b2bde559-3455-4021-b179-dfe60c0337b0/download/demanddata_2025.csv"),
    ("historic DA wind", "https://api.neso.energy/dataset/fbe3701d-1487-443e-abe9-47a6c01ecce2/resource/7524ec65-f782-4258-aaf8-5b926c17b966/download/7524ec65-f782-4258-aaf8-5b926c17b966-20261003084501.csv"),
    ("DA wind latest", "https://api.neso.energy/dataset/fbe3701d-1487-443e-abe9-47a6c01ecce2/resource/b2f03146-f05d-4824-a663-3a4f36090c71/download/b2f03146-f05d-4824-a663-3a4f36090c71-20261003084006.csv"),
    ("embedded forecast latest", "https://api.neso.energy/dataset/91c0c70e-0ef5-4116-b6fa-7ad084b5e0e8/resource/db6c038f-98af-4570-ab60-24d71ebd0ae5/download/202610031225_embedded_forecast.csv"),
    ("embedded archive 2025", "https://api.neso.energy/dataset/91c0c70e-0ef5-4116-b6fa-7ad084b5e0e8/resource/fc13df13-2dad-4a1c-b9e3-4569efba4955/download/embedded_archive_2025.csv"),
    ("demand update", "https://api.neso.energy/dataset/7a12172a-939c-404c-b581-a6128b74f588/resource/177f6fa4-ae49-4182-81ea-0c6b35f26ca6/download/demanddataupdate.csv"),
):
    r = G(u)
    if r is not None and r.status_code == 200:
        lines = r.text.splitlines()
        out.append(f"  {name}: {len(lines)} lines; head: {lines[0][:400]}")
        out.append(f"      row1: {lines[1][:300] if len(lines) > 1 else ''}")
        out.append(f"      last: {lines[-1][:300]}")
# 6) Carbon Intensity regional history (one region, two days) + licence page
r = G("https://api.carbonintensity.org.uk/regional/intensity/2025-01-01T00:00Z/2025-01-03T00:00Z/regionid/1")
if r is not None and r.status_code == 200:
    out.append("  regional: " + r.text[:600])
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2000])
