"""Build web/data/site.json from the raw data.

    python scripts/build_site.py

Inputs (data/raw/):
    eww/<date>_eww_opendatabase.csv       Open European offshore wind turbine database (EuroWindWakes), one row
                                          per turbine: farm, OEM, lat/lon, rated power, rotor, hub, type, COD
    eww/power_curves/<type>.csv            power (kW) and Ct curves per turbine type (PyWake generic curves)
    European_offshore_wind_farm_outline.geojson   farm and zone outlines (own compilation, WGS84)
    global_turbines.csv                   Global offshore wind turbine dataset (Zhang et al. 2021, CC0): turbines
                                          detected in Sentinel-1 SAR up to 2021, outside Europe used here
                                          (scripts/fetch_global_turbines.py)
    ne_10m_land.geojson                   Natural Earth land (downloaded if missing)

Output: web/data/site.json
    farms   operating farms: outline, and for farms with turbines a layout in local metres (x east, y north,
            origin at the layout centroid), rotor data and a power-curve key
    types   turbine types: name, rated MW, rotor D, rated speed, power (MW) and Ct curves; farms point to
            them with `ti` (one index, or one per turbine for mixed farms)
    zones   planned / consented / under-construction outlines without operating turbines
    coast   land polygons (fill): detailed around the farms, coarse elsewhere
    dbox    boxes with detailed land; the page doesn't stroke land edges that lie on their borders

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
# Global dataset: country name fixes and region of every country
GLOBAL_COUNTRY = {"Korea": "South Korea", "America": "United States"}
REGION = {"China": "Asia", "Taiwan": "Asia", "Vietnam": "Asia", "South Korea": "Asia", "Japan": "Asia",
          "United States": "North America"}  # everything in the European database: "Europe"
EUROPE_IN_GLOBAL = {"United Kingdom", "Germany", "Denmark", "Netherlands", "Belgium", "Sweden", "Finland", "Ireland",
                    "Spain"}  # covered better by the European database
# Projects where the turbine is known (public project data); others get an estimate (see global_farms)
KNOWN_TYPES = [  # (name contains, type, MW, rotor m, hub m)
    ("Block Island", "GE Haliade 150-6MW", 6.0, 150.0, 100.0),
    ("Coastal Virginia", "SG 6.0-154", 6.0, 154.0, 103.0),
    ("Formosa 1", "SG 6.0-154", 6.0, 154.0, 96.0),
    ("Greater Changhua", "SG 8.0-167 DD", 8.0, 167.0, 109.0),
    ("Southwest Offshore", "Doosan WinDS3000/134", 3.0, 134.0, 87.0),
    ("Tamra", "Doosan WinDS3000/91", 3.0, 91.0, 80.0),
]
DEFAULT_MW = {"Vietnam": 3.6, "South Korea": 3.0, "Taiwan": 6.0, "United States": 6.0}  # China: by year below
TILE_DEG = 20  # land polygons are cut at multiples of this (page skips off-screen tiles, doesn't stroke cuts)
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


def country_of(c: str, lon: float, lat: float) -> str:
    c = GLOBAL_COUNTRY.get(c, c)
    # Taiwan's farms are labelled China in the source. Fujian's farms (Putian, Pingtan, Changle) are north of
    # 25N up to ~120E; Taiwan's (Changhua, Formosa) are south of 25N from ~119.8E, or east of 120.5E
    if c == "China" and lat < 26.5 and ((lat < 25.0 and 119.6 <= lon <= 122.5) or lon >= 120.5):
        return "Taiwan"
    return c


def clusters(pts: list[tuple[float, float]], km: float = 2.5) -> list[list[int]]:
    """Single-linkage groups of points closer than `km` (a project name can cover separate sites)."""
    n, parent = len(pts), list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tree = STRtree([Point(p) for p in pts])
    for i, p in enumerate(pts):
        for j in tree.query(Point(p).buffer(km / 111 / max(0.2, cos(radians(p[1]))))):
            j = int(j)
            dx = (pts[j][0] - p[0]) * 111.32 * cos(radians(p[1]))
            dy = (pts[j][1] - p[1]) * 110.57
            if dx * dx + dy * dy <= km * km:
                parent[find(i)] = find(int(j))
    groups = collections.defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=len, reverse=True)


def global_farms(add_type) -> list[dict]:
    """Farms outside Europe from the global SAR turbine dataset. Turbine types are unknown except for a few
    projects (KNOWN_TYPES); otherwise rated power = project capacity / turbines detected when that is 2-8.5 MW,
    else a regional default, rotor from 330 W/m2 specific power, hub = D/2 + 25 m. Farms are marked est."""
    path = RAW / "global_turbines.csv"
    if not path.exists():
        return []
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        lon, lat = float(r["lon"]), float(r["lat"])
        c = country_of(r["country"], lon, lat)
        if c in EUROPE_IN_GLOBAL or not c:
            continue
        rows.append({**r, "lon": lon, "lat": lat, "c": c, "project": r["project"] or "Unnamed"})
    kept, tree_pts = [], []  # the same turbine is sometimes detected twice: drop points within 60 m
    grid = collections.defaultdict(list)
    for r in rows:
        gx, gy = int(r["lon"] * 200), int(r["lat"] * 200)
        near = [q for ix in (gx - 1, gx, gx + 1) for iy in (gy - 1, gy, gy + 1) for q in grid[(ix, iy)]]
        if any(((q["lon"] - r["lon"]) * 111320 * cos(radians(r["lat"]))) ** 2 + ((q["lat"] - r["lat"]) * 110574) ** 2
               < 60 ** 2 for q in near):
            continue
        grid[(gx, gy)].append(r)
        kept.append(r)
    print(f"  global dataset: {len(rows)} turbines outside Europe, {len(rows) - len(kept)} duplicates dropped")
    rows = kept
    by_proj = collections.defaultdict(list)
    for r in rows:
        by_proj[(r["c"], r["project"])].append(r)
    out = []
    for (c, proj), ts in sorted(by_proj.items()):
        try:
            per = float(ts[0]["project_mw"]) / len(ts)
        except ValueError:
            per = None
        groups = clusters([(t["lon"], t["lat"]) for t in ts], km=3.0)
        big = [g for g in groups if len(g) >= 4] or groups[:1]
        for g in [g for g in groups if g not in big]:  # 1-3 stray turbines join the nearest larger group
            x, y = ts[g[0]]["lon"], ts[g[0]]["lat"]
            dist = lambda h: min(((ts[i]["lon"] - x) * cos(radians(y))) ** 2 + (ts[i]["lat"] - y) ** 2 for i in h)
            near = min(big, key=dist)
            if dist(near) ** 0.5 * 111 <= 10:
                near.extend(g)
            else:
                big.append(g)
        groups = sorted(big, key=len, reverse=True)
        for gi, g in enumerate(groups):
            gt = [ts[i] for i in g]
            year = sorted(t["first_seen"] for t in gt)[len(gt) // 2][:4]  # median: stray early detections
            known = next((k for k in KNOWN_TYPES if k[0].lower() in proj.lower()), None)
            if known:
                tname, mw, d, hub = known[1:]
                basis = "known turbine type"
            else:
                if per is not None and 2.0 <= per <= 8.5:
                    mw, basis = round(per * 2) / 2, "project capacity / turbines detected"
                else:
                    mw = DEFAULT_MW.get(c, 4.0 if year < "2019" else 5.5)
                    basis = "regional default for " + year
                d = round((4 * mw * 1e6 / (pi * 330)) ** 0.5)
                hub = round(d / 2 + 25)
                tname = f"Unknown (~{mw:g} MW, ~{d} m rotor)"
            ti = add_type(tname, mw, float(d), "unknown" if not known else tname.split()[0])
            pts = [(t["lon"], t["lat"]) for t in gt]
            lon0, lat0 = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            kx, ky = 111320 * cos(radians(lat0)), 110574
            geom = MultiPoint(pts).convex_hull.buffer(300 / ky)
            name = proj if len(groups) == 1 else f"{proj} ({gi + 1})"
            if name == "Unnamed":
                name = f"Unnamed, {lat0:.2f}° {lon0:.2f}°"
            out.append({
                "id": 800000 + len(out), "n": name, "c": c, "rg": REGION.get(c, "Other"),
                "cap": round(mw * len(gt), 1), "inst": round(mw * len(gt), 1),
                "a": round(geom.area * kx * ky / 1e6, 1), "ol": [flat(x, 3) for x in rings(geom, 0.003)],
                "lon": round(lon0, 4), "lat": round(lat0, 4), "mw": mw, "D": float(d), "h": float(hub), "y": year,
                "t": tname, "oem": "" if not known else tname.split()[0], "ti": ti,
                "xy": [round(v) for p in pts for v in ((p[0] - lon0) * kx, (p[1] - lat0) * ky)],
                "o": [[round(v) for x, y in r for v in ((x - lon0) * kx, (y - lat0) * ky)] for r in rings(geom, 0.0002)],
                "est": basis, "own": ts[0]["owner"], "pmw": ts[0]["project_mw"], "src": "gowt",
            })
    return out


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
        farms.append({"id": int(p["wind_farm_id"]), "n": fix_name(p["name"]), "c": p["country"], "rg": "Europe",
                      "cap": round(p["capacity_mw"] or 0, 1), "a": round(p["boundary_area_km2"] or 0, 1),
                      "ol": [flat(x, 3) for x in rings(g, 0.003)], "lon": round(c.x, 4), "lat": round(c.y, 4)})

    # 3b) the rest of the world from the global SAR turbine dataset
    def add_type(name, mw, d, oem):
        key = curve_key(name)
        if key not in type_index:
            c = curves.get(key) or generic_curve(mw, d)
            type_index[key] = len(types)
            types.append({"name": name, "key": key, "oem": oem, "mw": mw, "D": d, "ur": round(rated_speed(c), 2), **c})
        return type_index[key]
    for fm in farms:
        fm["rg"] = "Europe"
    gl = global_farms(add_type)
    for fm in gl:
        fm["ur"] = types[fm["ti"]]["ur"]
    print(f"+ {len(gl)} farms outside Europe from {sum(len(f['xy']) // 2 for f in gl)} turbines (global SAR dataset)")
    farms += gl

    # 4) remaining non-operational polygons are future zones
    zones = []
    for i, p in enumerate(props):
        if i in used_polys or p["status"] == "Operational":
            continue
        r = rings(polys[i], 0.004)
        if r:
            zones.append({"id": int(p["wind_farm_id"]), "n": fix_name(p["name"]), "c": p["country"], "rg": "Europe",
                          "s": STATUS.get(p["status"], "pl"), "st": p["status"], "mw": round(p["capacity_mw"] or 0),
                          "a": round(p["boundary_area_km2"] or 0), "r": [flat(x, 3) for x in r]})

    farms.sort(key=lambda f: -f["cap"])
    zones.sort(key=lambda z: -z["a"])

    land_path = RAW / "ne_10m_land.geojson"
    if not land_path.exists():
        print("downloading Natural Earth land ...")
        urllib.request.urlretrieve(LAND_URL, land_path)
    land = unary_union([shape(f["geometry"]) for f in json.loads(land_path.read_text(encoding="utf-8"))["features"]])
    # detailed land around the farms (Europe box + a box around every other farm), coarse land elsewhere.
    # The page strokes coastlines from these polygons but skips edges on the box borders ("dbox").
    eu_box = box(-14, 34, 34, 72)
    boxes = [box(round(f["lon"] - 3), round(f["lat"] - 2.5), round(f["lon"] + 3), round(f["lat"] + 2.5))
             for f in farms if f.get("rg") != "Europe"]
    other = unary_union(boxes).difference(eu_box) if boxes else Polygon()
    detail = unary_union([eu_box, other])
    parts = [(land.intersection(eu_box), 0.01), (land.intersection(other), 0.02), (land.difference(detail), 0.1)]
    coast = []
    for g, tol in parts:  # simplify, then cut into tiles so the page can skip land outside the view
        g = g.simplify(tol, preserve_topology=True)  # (simplifying after cutting would move the cut edges)
        for tx in range(-180, 180, TILE_DEG):
            for ty in range(-100, 100, TILE_DEG):  # cut lines at multiples of TILE_DEG
                t = g.intersection(box(tx, ty, tx + TILE_DEG, ty + TILE_DEG))
                if not t.is_empty:
                    coast += [flat(r, 2) for r in rings(t, 0) if Polygon(r).area > 0.004]
    dbox = [[round(v, 2) for v in b.bounds] for b in [eu_box] + boxes]

    site = {"source": Path(csv_path).name, "farms": farms, "types": types, "zones": zones, "coast": coast, "dbox": dbox, "tile": TILE_DEG}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(site, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    n_lay = sum("xy" in f for f in farms)
    print(f"{len(turbines)} turbines -> {len(farms)} operating farms ({n_lay} with layouts), "
          f"{len(zones)} zones, {len(types)} turbine types with power curves -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
