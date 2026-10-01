"""Add offshore farms that the EuroWindWakes database lacks, from OpenStreetMap.

    python scripts/fetch_osm_turbines.py                 # all presets below
    python scripts/fetch_osm_turbines.py tahkoluoto      # one preset (also runs on GitHub: extra-turbines workflow)

Writes/updates data/raw/extra_turbines.csv (same columns as the database CSV), which
scripts/build_site.py reads in addition to the database. Then run:

    python scripts/build_site.py

OpenStreetMap tags are often incomplete, so each preset carries fallback turbine data (type, rated MW,
rotor, hub height, commissioning date). Values found in the OSM tags win over the fallbacks. Check the
printed table before pushing. Turbine positions: (c) OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "extra_turbines.csv"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
LOG = ROOT / "data" / "raw" / "extra_turbines_log.txt"
log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg)
    log_lines.append(msg)
COLS = ["wind_farm", "oem_manufacturer", "latitude", "longitude", "country", "rated_power", "rotor_diameter",
        "hub_height", "turbine_type", "commissioning_date"]

# name: (bbox south, west, north, east), fallback attributes. Check the fallbacks against a reliable source.
PRESETS = {
    "tahkoluoto": {
        "bbox": (61.55, 21.20, 61.72, 21.50),
        "wind_farm": "Tahkoluoto", "country": "Finland",
        # The bbox also holds the harbour/breakwater turbines (mapped 2011, near land) and one at Reposaari.
        # Keep only the offshore park: 11 turbines 4-7 km out, mapped in 2020 (10 x SWT-4.0-130 from 2017,
        # probably plus the 2010 pilot, which can't be told apart from the tags).
        "keep_ids": [7525510795, 7525511513, 7525511961, 7525512003, 7525513293, 7525513556, 7525513617,
                     7525514032, 7525514067, 7525514156, 7525514242],
        "fallback": {"oem_manufacturer": "Siemens", "turbine_type": "SWT-4.0-130", "rated_power": 4.0,
                     "rotor_diameter": 130.0, "hub_height": 90.0, "commissioning_date": "2017-08"},
    },
}


def num(v: str | None) -> float | None:
    if not v:
        return None
    m = re.search(r"[\d.]+", v.replace(",", "."))
    if not m:
        return None
    x = float(m.group())
    if "kw" in v.lower():
        x /= 1000
    return x


def osm_api(name: str, s: float, w: float, n: float, e: float) -> list[dict] | None:
    import xml.etree.ElementTree as ET

    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={w},{s},{e},{n}"
    try:
        r = requests.get(url, timeout=120, headers={"User-Agent": "offshore-wake-monitor (personal, non-commercial)"})
        if r.status_code != 200:
            log(f"{name}: OSM API -> HTTP {r.status_code}: {r.text[:120]!r}")
            return None
        els = []
        for nd in ET.fromstring(r.content).iter("node"):
            tags = {t.get("k"): t.get("v") for t in nd.iter("tag")}
            if tags.get("generator:source") == "wind":
                els.append({"id": int(nd.get("id")), "lat": float(nd.get("lat")), "lon": float(nd.get("lon")), "tags": tags})
        log(f"{name}: OSM API -> {len(els)} wind generators")
        return els
    except Exception as ex:
        log(f"{name}: OSM API -> {ex!r}")
        return None


def fetch(name: str, p: dict) -> list[dict]:
    s, w, n, e = p["bbox"]
    q = f'[out:json][timeout:60];node["generator:source"="wind"]({s},{w},{n},{e});out;'
    els = None
    for url in OVERPASS:  # public Overpass servers are often busy; the OSM API is the fallback
        if els is not None:
            break
        try:
            r = requests.post(url, data={"data": q}, timeout=60,
                              headers={"User-Agent": "offshore-wake-monitor (personal, non-commercial)"})
            if r.status_code != 200:
                log(f"{name}: {url} -> HTTP {r.status_code}: {r.text[:120]!r}")
                time.sleep(20)
                continue
            els = r.json().get("elements", [])
            log(f"{name}: {url} -> {len(els)} elements")
        except Exception as ex:
            log(f"{name}: {url} -> {ex!r}")
            time.sleep(20)
    if els is None:  # fall back to the main OSM API (small bounding boxes only)
        els = osm_api(name, s, w, n, e)
    if els is None:
        return []
    if p.get("keep_ids"):
        els = [el for el in els if el["id"] in set(p["keep_ids"])]
    rows = []
    for el in els:
        t = el.get("tags", {})
        log(f"    osm node {el['id']} {el['lat']:.5f} {el['lon']:.5f} tags: " +
            "; ".join(f"{k}={v}" for k, v in sorted(t.items()) if k not in ("power", "generator:source")))
        fb = p["fallback"]
        rows.append({
            "wind_farm": p["wind_farm"], "country": p["country"],
            "latitude": round(el["lat"], 5), "longitude": round(el["lon"], 5),
            "oem_manufacturer": t.get("manufacturer") or fb["oem_manufacturer"],
            "turbine_type": t.get("model") or fb["turbine_type"],
            "rated_power": num(t.get("generator:output:electricity")) or fb["rated_power"],
            "rotor_diameter": num(t.get("rotor:diameter")) or fb["rotor_diameter"],
            "hub_height": num(t.get("height:hub")) or fb["hub_height"],
            "commissioning_date": (t.get("start_date") or fb["commissioning_date"])[:7],
        })
    log(f"{name}: {len(rows)} turbines from OpenStreetMap")
    for x in rows:
        log(f"    {x['latitude']} {x['longitude']} {x['turbine_type']} {x['rated_power']} MW {x['commissioning_date']}")
    return rows


def main(names: list[str]) -> None:
    names = names or list(PRESETS)
    existing = list(csv.DictReader(open(OUT, encoding="utf-8"))) if OUT.exists() else []
    farms = {PRESETS[n]["wind_farm"] for n in names}
    keep = [r for r in existing if r["wind_farm"] not in farms]
    new = [row for n in names for row in fetch(n, PRESETS[n])]
    LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    if not new:
        print("nothing fetched; extra_turbines.csv left unchanged")
        return
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=COLS)
        wr.writeheader()
        wr.writerows(keep + new)
    log(f"wrote {len(keep) + len(new)} rows -> {OUT.relative_to(ROOT)}")
    LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
