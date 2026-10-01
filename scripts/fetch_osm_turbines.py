"""Add offshore farms that the EuroWindWakes database lacks, from OpenStreetMap.

    python scripts/fetch_osm_turbines.py                 # all presets below
    python scripts/fetch_osm_turbines.py tahkoluoto      # one preset

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
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "extra_turbines.csv"
OVERPASS = "https://overpass-api.de/api/interpreter"
COLS = ["wind_farm", "oem_manufacturer", "latitude", "longitude", "country", "rated_power", "rotor_diameter",
        "hub_height", "turbine_type", "commissioning_date"]

# name: (bbox south, west, north, east), fallback attributes. Check the fallbacks against a reliable source.
PRESETS = {
    "tahkoluoto": {
        "bbox": (61.55, 21.20, 61.72, 21.50),
        "wind_farm": "Tahkoluoto", "country": "Finland",
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


def fetch(name: str, p: dict) -> list[dict]:
    s, w, n, e = p["bbox"]
    q = f'[out:json][timeout:60];node["generator:source"="wind"]({s},{w},{n},{e});out;'
    r = requests.post(OVERPASS, data={"data": q}, timeout=90,
                      headers={"User-Agent": "offshore-wake-monitor (personal, non-commercial)"})
    r.raise_for_status()
    rows = []
    for el in r.json().get("elements", []):
        t = el.get("tags", {})
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
    print(f"{name}: {len(rows)} turbines from OpenStreetMap")
    for x in rows:
        print("   ", x["latitude"], x["longitude"], x["turbine_type"], x["rated_power"], "MW", x["commissioning_date"])
    return rows


def main(names: list[str]) -> None:
    names = names or list(PRESETS)
    existing = list(csv.DictReader(open(OUT, encoding="utf-8"))) if OUT.exists() else []
    farms = {PRESETS[n]["wind_farm"] for n in names}
    keep = [r for r in existing if r["wind_farm"] not in farms]
    new = [row for n in names for row in fetch(n, PRESETS[n])]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=COLS)
        wr.writeheader()
        wr.writerows(keep + new)
    print(f"wrote {len(keep) + len(new)} rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
