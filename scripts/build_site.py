"""Build web/data/site.json from the raw GeoJSON files.

    python scripts/build_site.py

Inputs  (data/raw/):
    European_offshore_wind_turbines.geojson     turbine points (WGS84)
    European_offshore_wind_farm_outline.geojson farm and zone polygons (WGS84)
    ne_10m_land.geojson                          Natural Earth land (downloaded if missing)

Output: web/data/site.json
    farms  - operating farms. Those with turbine positions carry a layout in local
             metres (x east, y north, origin at the layout centroid) plus rotor data.
    zones  - planned / consented / under-construction areas (outlines only)
    coast  - simplified land polygons for the map background
"""
from __future__ import annotations

import collections
import json
import statistics as st
import urllib.request
from math import cos, pi, radians
from pathlib import Path

from shapely.geometry import Polygon, box, shape

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "data" / "site.json"
LAND_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"

RHO, CP = 1.225, 0.45  # air density, electrical Cp below rated -> rated wind speed
# The outline source mangled some Danish characters
NAME_FIX = {"Nordsren": "Nordsøen", "Lillebklt": "Lillebælt", "Trem Mkllebugt": "Treå Møllebugt",
            "Samsa": "Samsø", "Krigers": "Kriegers"}
STATUS = {"Operational": "op", "Under Construction": "uc", "FID Taken, Pre-Construction": "uc",
          "Consented": "cs", "In Planning / Consent Application Submitted": "cs",
          "Lease Awarded, Pre-Planning": "cs"}


def fix_name(s: str) -> str:
    for a, b in NAME_FIX.items():
        s = s.replace(a, b)
    return s


def rings(geom, tol):
    g = geom.simplify(tol, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
    return [list(p.exterior.coords) for p in polys if not p.is_empty and len(p.exterior.coords) > 3]


def flat(ring, nd):
    return [round(v, nd) for xy in ring for v in xy[:2]]


def rated_speed(p_mw: float, d_m: float) -> float:
    """Wind speed where P = 0.5 rho A Cp U^3 reaches rated power, clamped to a sane band."""
    a = pi * d_m ** 2 / 4
    u = (p_mw * 1e6 / (0.5 * RHO * a * CP)) ** (1 / 3)
    return round(min(13.5, max(9.5, u)), 2)


def main() -> None:
    turb = json.loads((RAW / "European_offshore_wind_turbines.geojson").read_text(encoding="utf-8"))
    outl = json.loads((RAW / "European_offshore_wind_farm_outline.geojson").read_text(encoding="utf-8"))

    by_farm = collections.defaultdict(list)
    for f in turb["features"]:
        if f["geometry"]:
            by_farm[int(f["properties"]["wind_farm_id"])].append(f)

    farms, zones = [], []
    for f in outl["features"]:
        p = f["properties"]
        if p["status"] == "Decommissioned" or not f["geometry"]:
            continue
        fid = int(p["wind_farm_id"])
        geom = shape(f["geometry"])
        if p["status"] != "Operational":
            r = rings(geom, 0.004)
            if r:
                zones.append({"id": fid, "n": fix_name(p["name"]), "c": p["country"], "s": STATUS.get(p["status"], "pl"),
                              "st": p["status"], "mw": round(p["capacity_mw"] or 0), "a": round(p["boundary_area_km2"] or 0),
                              "r": [flat(x, 3) for x in r]})
            continue
        c = geom.centroid
        fm = {"id": fid, "n": fix_name(p["name"]), "c": p["country"], "cap": round(p["capacity_mw"] or 0, 1),
              "a": round(p["boundary_area_km2"] or 0, 1), "ol": [flat(x, 3) for x in rings(geom, 0.003)],
              "lon": round(c.x, 4), "lat": round(c.y, 4)}
        ts = by_farm.get(fid)
        if ts:
            pts = [t["geometry"]["coordinates"][:2] for t in ts]
            lon0 = sum(q[0] for q in pts) / len(pts)
            lat0 = sum(q[1] for q in pts) / len(pts)
            kx, ky = 111320 * cos(radians(lat0)), 110574
            props = [t["properties"] for t in ts]
            mw = round(st.median(q["rated_power_mw"] for q in props), 2)
            d = round(st.median(q["rotor_diameter_m"] for q in props))
            fm.update(
                lon=round(lon0, 4), lat=round(lat0, 4), mw=mw, D=d,
                h=round(st.median(q["hub_height_m"] for q in props)),
                y=min(str(q["commissioning_date"]) for q in props)[:4],
                t=collections.Counter(q["turbine_type"] for q in props).most_common(1)[0][0],
                ur=rated_speed(mw, d),
                xy=[round(v) for q in pts for v in ((q[0] - lon0) * kx, (q[1] - lat0) * ky)],
                o=[[round(v) for x, y in r for v in ((x - lon0) * kx, (y - lat0) * ky)] for r in rings(geom, 0.0002)],
            )
        farms.append(fm)

    farms.sort(key=lambda f: -(f["mw"] * len(f["xy"]) / 2 if "xy" in f else f["cap"]))
    zones.sort(key=lambda z: -z["a"])

    land_path = RAW / "ne_10m_land.geojson"
    if not land_path.exists():
        print("downloading Natural Earth land ...")
        urllib.request.urlretrieve(LAND_URL, land_path)
    land = json.loads(land_path.read_text(encoding="utf-8"))
    clip, coast = box(-14, 34, 34, 72), []
    for f in land["features"]:
        for r in rings(shape(f["geometry"]).intersection(clip), 0.01):
            if Polygon(r).area > 0.004:
                coast.append(flat(r, 2))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"farms": farms, "zones": zones, "coast": coast}, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")
    n_lay = sum("xy" in f for f in farms)
    print(f"{len(farms)} operating farms ({n_lay} with layouts), {len(zones)} zones -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
