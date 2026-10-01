"""Build web/data/site.json from the raw data.

    python scripts/build_site.py

Inputs (data/raw/):
    eww/<date>_eww_opendatabase.csv       Open European offshore wind turbine database (EuroWindWakes), one row
                                          per turbine: farm, OEM, lat/lon, rated power, rotor, hub, type, COD
    eww/power_curves/<type>.csv            power (kW) and Ct curves per turbine type (PyWake generic curves)
    European_offshore_wind_farm_outline.geojson   farm and zone outlines (own compilation, WGS84)
    ne_10m_land.geojson                   Natural Earth land (downloaded if missing)

Output: web/data/site.json
    farms   operating farms: outline, and for farms with turbines a layout in local metres (x east, y north,
            origin at the layout centroid), rotor data and a power-curve key
    types   turbine types: name, rated MW, rotor D, rated speed, power (MW) and Ct curves; farms point to
            them with `ti` (one index, or one per turbine for mixed farms)
    zones   planned / consented / under-construction outlines without operating turbines
    coast   simplified land polygons

Matching: the turbine database has no link to the outline file, so turbines are matched by location.
A farm is one wind farm of the turbine database; its outline is the union of the outline polygons that hold
its turbines. Turbines outside every polygon go to the nearest polygon within 2 km, else to the polygon most of
their farm's turbines use, else the farm gets a convex hull as outline.
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import statistics as st
import urllib.request
from math import cos, pi, radians
from pathlib import Path

from shapely.geometry import MultiPoint, Point, Polygon, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EWW = RAW / "eww"
OUT = ROOT / "web" / "data" / "site.json"
LAND_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"

# Danish characters lost somewhere upstream (both source files)
NAME_FIX = {"Nordsren": "Nordsøen", "Lillebklt": "Lillebælt", "Trem Mkllebugt": "Treå Møllebugt", "Samsa": "Samsø",
            "Krigers": "Kriegers", "Renland": "Rønland", "Tunm Knob": "Tunø Knob", "Sprogo": "Sprogø",
            "Rodsand II": "Rødsand II"}
STATUS = {"Operational": "op", "Under Construction": "uc", "FID Taken, Pre-Construction": "uc",
          "Consented": "cs", "In Planning / Consent Application Submitted": "cs",
          "Lease Awarded, Pre-Planning": "cs"}
PRIORITY = {"Operational": 0, "Under Construction": 1, "FID Taken, Pre-Construction": 2}


def fix_name(s: str) -> str:
    for a, b in NAME_FIX.items():
        if s == a or (a in s and len(a) > 6):
            s = s.replace(a, b)
    return s


def rings(geom, tol):
    g = geom.simplify(tol, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
    return [list(p.exterior.coords) for p in polys if not p.is_empty and len(p.exterior.coords) > 3]


def flat(ring, nd):
    return [round(v, nd) for xy in ring for v in xy[:2]]


def curve_key(turbine_type: str) -> str:
    return turbine_type.replace(" ", "_").replace("/", "_")


def load_curves() -> dict:
    out = {}
    for p in sorted(glob.glob(str(EWW / "power_curves" / "*.csv"))):
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        out[Path(p).stem] = {"ws": [float(r["ws"]) for r in rows],
                             "p": [round(float(r["power"]) / 1000, 4) for r in rows],  # kW -> MW
                             "ct": [round(float(r["ct"]), 4) for r in rows]}
    return out


def generic_curve(mw: float, d: float) -> dict:
    """For turbine types without a database curve: P = rated * (U/U_rated)^3 (Cp 0.45), cut-in 4, cut-out 25."""
    ur = min(13.5, max(9.5, (mw * 1e6 / (0.5 * 1.225 * pi * d * d / 4 * 0.45)) ** (1 / 3)))
    ws = [x / 2 for x in range(8, 51)]
    p = [round(mw * min(1.0, (w / ur) ** 3), 4) for w in ws]
    ct = [round(0.8 if w <= ur else max(0.05, 0.8 * (ur / w) ** 3), 4) for w in ws]
    return {"ws": ws, "p": p, "ct": ct}


def rated_speed(c: dict) -> float:
    pmax = max(c["p"])
    return next(ws for ws, p in zip(c["ws"], c["p"]) if p >= 0.99 * pmax)


def main() -> None:
    csv_path = sorted(glob.glob(str(EWW / "*_eww_opendatabase.csv")))[-1]
    turbines = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    extra = RAW / "extra_turbines.csv"  # farms the database lacks (scripts/fetch_osm_turbines.py)
    if extra.exists():
        rows = list(csv.DictReader(open(extra, encoding="utf-8")))
        known = {t["wind_farm"] for t in turbines}
        rows = [r for r in rows if r["wind_farm"] not in known]
        print(f"+ {len(rows)} extra turbines from {extra.name}: {sorted({r['wind_farm'] for r in rows})}")
        turbines += rows
    curves = load_curves()
    outl = json.loads((RAW / "European_offshore_wind_farm_outline.geojson").read_text(encoding="utf-8"))

    polys, props = [], []
    for f in outl["features"]:
        if f["geometry"] and f["properties"]["status"] != "Decommissioned":
            polys.append(shape(f["geometry"]).buffer(0))
            props.append(f["properties"])
    tree = STRtree(polys)

    # 1) assign every turbine to an outline polygon (or none)
    by_farm = collections.defaultdict(list)
    for t in turbines:
        pt = Point(float(t["longitude"]), float(t["latitude"]))
        inside = [i for i in tree.query(pt) if polys[i].contains(pt)]
        if inside:
            inside.sort(key=lambda i: (PRIORITY.get(props[i]["status"], 9), polys[i].area))
            t["_pi"] = int(inside[0])
        else:
            i = int(tree.nearest(pt))
            t["_pi"] = i if polys[i].distance(pt) * 111 <= 2.0 else None
        by_farm[t["wind_farm"]].append(t)
    for name, ts in by_farm.items():  # stragglers follow their farm's majority polygon
        cnt = collections.Counter(t["_pi"] for t in ts if t["_pi"] is not None)
        if cnt:
            major = cnt.most_common(1)[0][0]
            for t in ts:
                if t["_pi"] is None:
                    t["_pi"] = major

    # 2) build farms from the turbine database
    farms, used_polys, used_ids = [], set(), set()
    types, type_index = [], {}

    def type_id(t: dict) -> int:
        key = curve_key(t["turbine_type"])
        if key not in type_index:
            c = curves.get(key) or generic_curve(float(t["rated_power"]), float(t["rotor_diameter"]))
            type_index[key] = len(types)
            types.append({"name": t["turbine_type"], "key": key, "oem": t["oem_manufacturer"],
                          "mw": float(t["rated_power"]), "D": float(t["rotor_diameter"]),
                          "ur": round(rated_speed(c), 2), **c})
        return type_index[key]
    for name, ts in sorted(by_farm.items()):
        cnt = collections.Counter(t["_pi"] for t in ts if t["_pi"] is not None)
        pis = [i for i, n in cnt.items() if n >= max(2, 0.1 * len(ts))] or list(cnt)
        used_polys.update(cnt)  # every polygon holding any of its turbines counts as used
        pts = [(float(t["longitude"]), float(t["latitude"])) for t in ts]
        lon0, lat0 = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        kx, ky = 111320 * cos(radians(lat0)), 110574
        hull = MultiPoint(pts).convex_hull.buffer(500 / ky)
        # a large planned zone that happens to contain an old farm is not that farm's site
        pis = [i for i in pis if props[i]["status"] == "Operational" or polys[i].area <= 3 * hull.area]
        if pis:
            geom = unary_union([polys[i] for i in pis])
            area = sum(props[i]["boundary_area_km2"] or 0 for i in pis)
            fid = int(props[cnt.most_common(1)[0][0]]["wind_farm_id"])
        else:  # no outline: hull around the turbines, 300 m margin
            geom = MultiPoint(pts).convex_hull.buffer(300 / ky)
            area = geom.area * kx * ky / 1e6
            fid = 900000 + len(farms)
        if fid in used_ids:
            fid = 900000 + len(farms)
        used_ids.add(fid)
        types_here = collections.Counter(t["turbine_type"] for t in ts)
        ttype = types_here.most_common(1)[0][0]
        main_ts = [t for t in ts if t["turbine_type"] == ttype]
        fm = {
            "id": fid, "n": fix_name(name), "c": ts[0]["country"],
            "cap": round(sum(float(t["rated_power"]) for t in ts), 1), "a": round(area, 1),
            "ol": [flat(x, 3) for x in rings(geom, 0.003)],
            "lon": round(lon0, 4), "lat": round(lat0, 4),
            "mw": round(st.median(float(t["rated_power"]) for t in main_ts), 3),
            "D": round(st.median(float(t["rotor_diameter"]) for t in main_ts), 1),
            "h": round(st.median(float(t["hub_height"]) for t in main_ts), 1),
            "y": min(t["commissioning_date"] for t in ts)[:4],
            "t": ttype, "oem": ts[0]["oem_manufacturer"],
            "inst": round(sum(float(t["rated_power"]) for t in ts), 1),
            "xy": [round(v) for p in pts for v in ((p[0] - lon0) * kx, (p[1] - lat0) * ky)],
            "o": [[round(v) for x, y in r for v in ((x - lon0) * kx, (y - lat0) * ky)] for r in rings(geom, 0.0002)],
        }
        tids = [type_id(t) for t in ts]
        fm["ti"] = tids[0] if len(set(tids)) == 1 else tids
        fm["ur"] = types[type_id(main_ts[0])]["ur"]
        if len(types_here) > 1:
            fm["mixed"] = dict(types_here)
        farms.append(fm)

    # 3) operational outlines without any database turbines stay as farms without a layout
    used_geom = unary_union([polys[i] for i in used_polys])
    for i, p in enumerate(props):
        if i in used_polys or p["status"] != "Operational":
            continue
        g = polys[i]
        if g.area and g.intersection(used_geom).area > 0.5 * g.area:  # duplicate of a farm we already have
            continue
        c = g.centroid
        farms.append({"id": int(p["wind_farm_id"]), "n": fix_name(p["name"]), "c": p["country"],
                      "cap": round(p["capacity_mw"] or 0, 1), "a": round(p["boundary_area_km2"] or 0, 1),
                      "ol": [flat(x, 3) for x in rings(g, 0.003)], "lon": round(c.x, 4), "lat": round(c.y, 4)})

    # 4) remaining non-operational polygons are future zones
    zones = []
    for i, p in enumerate(props):
        if i in used_polys or p["status"] == "Operational":
            continue
        r = rings(polys[i], 0.004)
        if r:
            zones.append({"id": int(p["wind_farm_id"]), "n": fix_name(p["name"]), "c": p["country"],
                          "s": STATUS.get(p["status"], "pl"), "st": p["status"], "mw": round(p["capacity_mw"] or 0),
                          "a": round(p["boundary_area_km2"] or 0), "r": [flat(x, 3) for x in r]})

    farms.sort(key=lambda f: -f["cap"])
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

    site = {"source": Path(csv_path).name, "farms": farms, "types": types, "zones": zones, "coast": coast}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(site, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    n_lay = sum("xy" in f for f in farms)
    print(f"{len(turbines)} turbines -> {len(farms)} operating farms ({n_lay} with layouts), "
          f"{len(zones)} zones, {len(types)} turbine types with power curves -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
