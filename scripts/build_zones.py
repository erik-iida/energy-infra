"""Bidding-zone outlines for the map's price / spread colouring -> web/data/zones.json

    python scripts/build_zones.py

Sources:
  * entsoe-py bidding-zone GeoJSON (EnergieID, MIT licence), https://github.com/EnergieID/entsoe-py
  * Natural Earth 1:50m admin-0 map units (public domain) for zones entsoe-py doesn't have: Ireland + Northern
    Ireland (IE(SEM)), Montenegro, North Macedonia, Bosnia and Herzegovina, Ukraine (UA-IPS), Albania.
Output: {"src", "zones": {zone: {"p": [[lon, lat, lon, lat, ...] ring, ...], "c": [lon, lat] label point}}}
Rings simplified to ~2 km and rounded to 0.01 deg.
"""
from __future__ import annotations

import io
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data" / "zones.json"
EP = "https://raw.githubusercontent.com/EnergieID/entsoe-py/master/entsoe/geo/geojson/{}.geojson"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_map_units.geojson"
EP_ZONES = {"AT": "AT", "BE": "BE", "BG": "BG", "CH": "CH", "CZ": "CZ", "DE-LU": "DE_LU", "DK1": "DK_1", "DK2": "DK_2",
            "EE": "EE", "ES": "ES", "FI": "FI", "FR": "FR", "GR": "GR", "HR": "HR", "HU": "HU", "IT-Calabria": "IT_CALA",
            "IT-Centre-North": "IT_CNOR", "IT-Centre-South": "IT_CSUD", "IT-North": "IT_NORD", "IT-Sardinia": "IT_SARD",
            "IT-Sicily": "IT_SICI", "IT-South": "IT_SUD", "LT": "LT", "LV": "LV", "NL": "NL", "NO1": "NO_1", "NO2": "NO_2",
            "NO3": "NO_3", "NO4": "NO_4", "NO5": "NO_5", "PL": "PL", "PT": "PT", "RO": "RO", "RS": "RS", "SE1": "SE_1",
            "SE2": "SE_2", "SE3": "SE_3", "SE4": "SE_4", "SI": "SI", "SK": "SK"}
NE_ZONES = {"IE(SEM)": ["Ireland", "Northern Ireland"], "ME": ["Montenegro"], "MK": ["North Macedonia", "Macedonia"],
            "BA": ["Bosnia and Herz.", "Bosnia and Herzegovina", "Republic Srpska", "Federation of Bosnia and Herzegovina",
                   "Brčko District"],
            "UA-IPS": ["Ukraine"], "AL": ["Albania"]}
TOL = 0.02


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def rings(geom) -> list[list[float]]:
    g = geom.simplify(TOL, preserve_topology=True)
    out = []
    for poly in getattr(g, "geoms", [g]):
        if poly.is_empty or poly.area < 0.002:  # drop specks (tiny islands)
            continue
        cs = [round(v, 2) for xy in poly.exterior.coords for v in xy[:2]]
        if len(cs) >= 8:
            out.append(cs)
    return out


def main() -> None:
    zones = {}
    for z, f in EP_ZONES.items():
        gj = get(EP.format(f))
        feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
        geom = unary_union([shape(ft["geometry"]) for ft in feats]).buffer(0)
        zones[z] = geom
    ne = get(NE)["features"]
    for z, names in NE_ZONES.items():
        parts = [shape(ft["geometry"]) for ft in ne
                 if {ft["properties"].get(k) for k in ("NAME", "NAME_LONG", "GEOUNIT", "SUBUNIT", "ADMIN")} & set(names)]
        if not parts:
            print(f"{z}: not found in Natural Earth")
            continue
        g = unary_union(parts).buffer(0)
        if z == "UA-IPS":  # Crimea is not in the Ukrainian market (IPS): keep the mainland
            from shapely.geometry import box
            g = g.difference(box(32.4, 44.3, 36.7, 46.15))
        zones[z] = g
    out = {}
    for z, g in zones.items():
        p = g.representative_point()
        out[z] = {"p": rings(g), "c": [round(p.x, 2), round(p.y, 2)]}
        print(f"{z}: {len(out[z]['p'])} rings, {sum(len(r) for r in out[z]['p']) // 2} points")
    OUT.write_text(json.dumps({"src": "Bidding zones: entsoe-py (EnergieID, MIT); Natural Earth (public domain) for IE(SEM), "
                                      "ME, MK, BA, UA-IPS, AL", "zones": out}, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
