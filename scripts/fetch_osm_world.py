"""Fetch wind turbines from OpenStreetMap: offshore outside Europe, and (demo) all onshore turbines in Estonia.

    python scripts/fetch_osm_world.py

Writes data/raw/osm/osm_wind.json and data/raw/osm/osm_wind_log.txt. Runs on GitHub Actions (osm-world
workflow); the cloud build environment can't reach Overpass.

How:
  1. Positions only ("out skel") for every wind generator in a few coastal bounding boxes.
  2. Keep the ones at sea: outside Natural Earth 10m land, or less than ~500 m inside it (intertidal farms and
     coastline inaccuracy). scripts/build_site.py later drops those already in the satellite dataset.
  3. Full tags for the kept turbines, by id.
  4. Wind power plants (power=plant, plant:source=wind) in the same boxes, centre + tags, for farm names.
  5. Estonia: every wind generator and plant inside the country (Overpass area), onshore demo.
Every turbine and plant gets a country from Natural Earth admin-0 (nearest country within ~250 km at sea).

Data (c) OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import requests
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT_DIR = RAW / "osm"
OUT = OUT_DIR / "osm_wind.json"
LOG = OUT_DIR / "osm_wind_log.txt"
LAND = RAW / "ne_10m_land.geojson"
ADMIN = RAW / "ne_50m_admin_0_countries.geojson"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "offshore-wake-monitor/1.0 (+https://github.com/erik-iida/energy-infra)"}

# (name, south, west, north, east): coasts with offshore wind outside Europe
BOXES = [  # small coastal boxes keep each Overpass query light
    ("cn-bohai", 38.0, 117.5, 41.5, 122.5), ("cn-shandong-n", 36.0, 119.0, 38.0, 123.0),
    ("cn-shandong-s", 34.0, 119.0, 36.0, 122.0), ("cn-jiangsu-n", 32.5, 119.5, 34.0, 122.5),
    ("cn-jiangsu-s", 30.5, 120.5, 32.5, 123.0), ("cn-zhejiang-n", 28.0, 120.5, 30.5, 123.5),
    ("cn-zhejiang-s", 26.0, 119.0, 28.0, 122.0), ("cn-fujian", 23.5, 117.0, 26.0, 120.3),
    ("cn-guangdong-e", 21.5, 113.0, 23.5, 117.5), ("cn-guangdong-w", 20.0, 109.5, 22.5, 113.0),
    ("cn-hainan-guangxi", 18.0, 107.5, 21.5, 111.5), ("taiwan", 22.0, 119.5, 25.5, 122.5),
    ("korea", 33.0, 124.5, 38.5, 130.0), ("japan-sw", 30.0, 128.0, 35.0, 135.0),
    ("japan-c", 33.0, 135.0, 42.0, 142.0), ("japan-n", 40.0, 138.0, 46.0, 146.0),
    ("vietnam", 8.0, 104.0, 11.5, 109.5), ("us-ne", 40.0, -74.5, 42.0, -69.5),
    ("us-nj-de", 38.5, -75.5, 40.5, -73.0), ("us-va-md", 36.0, -77.0, 38.5, -74.5),
]
INLAND_KEEP_DEG = 0.005  # keep turbines up to ~500 m inside the Natural Earth coastline
log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    log_lines.append(msg)


def overpass(q: str, what: str) -> list[dict] | None:
    """One try per server; a part that fails stays undone and the next run retries it."""
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": q}, timeout=120, headers=UA)
            if r.status_code == 200:
                els = r.json().get("elements", [])
                log(f"  {what}: {url.split('/')[2]} -> {len(els)} elements")
                return els
            log(f"  {what}: {url.split('/')[2]} -> HTTP {r.status_code} {r.text[:120]!r}")
        except Exception as ex:
            log(f"  {what}: {url.split('/')[2]} -> {ex!r}")
        time.sleep(10)
    return None


def ne(path: Path, name: str) -> dict:
    if not path.exists():
        urllib.request.urlretrieve(NE + name, path)
    return json.loads(path.read_text(encoding="utf-8"))


EE_BOX = (57.4, 21.6, 59.9, 28.3)


def estonia(turbines: dict, plants: dict, country) -> bool:
    """All wind generators and plants in Estonia: bounding box query (lighter than an area query), then
    keep the ones Natural Earth puts in Estonia."""
    log("estonia (onshore demo)")
    s, w, n, e = EE_BOX
    ee = overpass(f'[out:json][timeout:100];node["power"="generator"]["generator:source"="wind"]({s},{w},{n},{e});out;',
                  "turbines")
    for el in ee or []:
        if country(el["lon"], el["lat"]) == "Estonia":
            turbines[el["id"]] = {"id": el["id"], "lat": el["lat"], "lon": el["lon"], "set": "estonia",
                                  "tags": el.get("tags", {}), "country": "Estonia"}
    pl = overpass(f'[out:json][timeout:100];nwr["power"="plant"]["plant:source"="wind"]({s},{w},{n},{e});out center tags;',
                  "plants")
    for el in pl or []:
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is not None and country(c["lon"], c["lat"]) == "Estonia":
            plants[f'{el["type"]}/{el["id"]}'] = {"id": f'{el["type"]}/{el["id"]}', "lat": c["lat"], "lon": c["lon"],
                                                 "set": "estonia", "tags": el.get("tags", {}), "country": "Estonia"}
    log(f"  {sum(1 for t in turbines.values() if t['set'] == 'estonia')} turbines in Estonia")
    return ee is not None and pl is not None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    land_all = [shape(f["geometry"]) for f in ne(LAND, "ne_10m_land.geojson")["features"]]
    adm = ne(ADMIN, "ne_50m_admin_0_countries.geojson")["features"]
    cgeo = [shape(f["geometry"]) for f in adm]
    cname = [f["properties"].get("NAME") or f["properties"].get("NAME_EN") for f in adm]
    ctree = STRtree(cgeo)

    def country(lon: float, lat: float) -> str:
        p = Point(lon, lat)
        inside = [int(i) for i in ctree.query(p) if cgeo[int(i)].contains(p)]
        if inside:
            return cname[inside[0]]
        i = int(ctree.nearest(p))
        return cname[i] if cgeo[i].distance(p) < 2.5 else ""

    turbines: dict[int, dict] = {}
    plants: dict[str, dict] = {}
    done: list[str] = []
    if OUT.exists():  # resume: keep what earlier runs fetched, skip finished parts
        old = json.loads(OUT.read_text(encoding="utf-8"))
        turbines = {t["id"]: t for t in old["turbines"]}
        plants = {p["id"]: p for p in old["plants"]}
        done = old.get("done", [])
        log(f"resuming: {len(turbines)} turbines, {len(plants)} plants, done {done}")

    def save() -> None:
        for x in list(turbines.values()) + list(plants.values()):
            if "country" not in x:
                x["country"] = country(x["lon"], x["lat"])
        OUT.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%d"), "boxes": BOXES, "done": done,
                                   "turbines": sorted(turbines.values(), key=lambda t: t["id"]),
                                   "plants": sorted(plants.values(), key=lambda p: p["id"]),
                                   "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"},
                                  ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    if set(done) >= {"estonia"} | {b[0] for b in BOXES}:
        log("all parts fetched; nothing to do (delete data/raw/osm/osm_wind.json to refetch)")
        return
    if "estonia" not in done:
        if estonia(turbines, plants, country):
            done.append("estonia")
        save()
    for name, s, w, n, e in BOXES:
        if name in done:
            continue
        log(f"{name}: {s},{w},{n},{e}")
        skel = overpass(f'[out:json][timeout:100];node["power"="generator"]["generator:source"="wind"]'
                        f'({s},{w},{n},{e});out skel qt;', "positions")
        if skel is None:
            continue
        bb = box(w - 1, s - 1, e + 1, n + 1)
        land = unary_union([g.intersection(bb) for g in land_all if g.intersects(bb)])
        core = prep(land.buffer(-INLAND_KEEP_DEG))
        sea = [el for el in skel if el["id"] not in turbines and not core.contains(Point(el["lon"], el["lat"]))]
        log(f"  {len(skel)} wind generators, {len(sea)} at sea or on the coast")
        ids = [el["id"] for el in sea]
        tags_ok = True
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            full = overpass(f'[out:json][timeout:100];node(id:{",".join(map(str, chunk))});out;', f"tags {i}")
            tags_ok = tags_ok and full is not None
            for el in full or []:
                turbines[el["id"]] = {"id": el["id"], "lat": el["lat"], "lon": el["lon"], "set": "offshore",
                                      "tags": el.get("tags", {})}
        pl = overpass(f'[out:json][timeout:100];nwr["power"="plant"]["plant:source"="wind"]'
                      f'({s},{w},{n},{e});out center tags;', "plants")
        for el in pl or []:
            c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
            if c.get("lat") is None:
                continue
            plants[f'{el["type"]}/{el["id"]}'] = {"id": f'{el["type"]}/{el["id"]}', "lat": c["lat"], "lon": c["lon"],
                                                 "set": "offshore", "tags": el.get("tags", {})}
        if skel is not None and pl is not None and tags_ok:
            done.append(name)
        save()

    # plants only matter near the turbines we keep (they name the farms)
    tt = STRtree([Point(t["lon"], t["lat"]) for t in turbines.values()]) if turbines else None
    keep_pl = {}
    for k, p in plants.items():
        if tt is not None:
            pt = Point(p["lon"], p["lat"])
            j = int(tt.nearest(pt))
            if tt.geometries[j].distance(pt) < 0.1:  # ~10 km
                keep_pl[k] = p
    by = {}
    for t in turbines.values():
        by[(t["set"], t["country"])] = by.get((t["set"], t["country"]), 0) + 1
    for k, v in sorted(by.items()):
        log(f"  {k[0]:8} {k[1] or '?':20} {v}")
    plants.clear()
    plants.update(keep_pl)
    save()
    log(f"wrote {len(turbines)} turbines, {len(keep_pl)} plants -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    finally:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
