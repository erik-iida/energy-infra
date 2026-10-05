"""Build tests/fixtures/data/: a small, deterministic copy of every file the page loads (docs/DATA_CONTRACT.md).

    python tests/fixtures/make_fixtures.py

Inputs: the committed files in data/static/ (site, zones, capture, gas, gie, grid, bathy) and the generated ones the deploy
builds (build/data/browse/, build/data/newsletter/: run `STORE_DIR=<store copy> python scripts/build_browse.py` and
`python scripts/build_newsletter_site.py` first). feed.json is synthetic (same shape as the
pipeline writes, values from smooth formulas), so the smoke test does not depend on live APIs. The fixed "now" of the
fixtures is NOW below; the smoke test pins the browser clock to it.

Re-run when the data contract changes, then commit the result. Never commit real private data here (no spark spreads).
"""
from __future__ import annotations

import io
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "static"          # committed inputs
BUILT = ROOT / "build" / "data"         # a local run of build_browse / build_newsletter_site (spec 3 step 3 layout)
OUT = Path(__file__).resolve().parent / "data"
NOW = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)  # last past hour of the synthetic feed
FARMS = [23352, 23253, 6738, 6713, 6556, 6554, 6432, 6426, 6476, 6484, 6510, 900107, 850000, 850002, 6359, 6307,
         900102, 23470, 900104, 900112]
TS_ZONES = ["RO", "HU", "BG", "RS", "UA-IPS", "GR", "PL", "LT", "LV", "SE4", "DE-LU", "GB"]
PRICE_ZONES = ["RO", "HU", "BG", "RS", "GR", "PL", "CZ", "SK", "DE-LU", "AT", "FR", "NL", "DK1", "DK2", "NO2", "SE4",
               "GB", "LT", "LV", "EE", "HR", "SI", "IT-North", "ES", "BE", "CH", "FI"]
MODELS = {"jensen": "Jensen (NOJ)", "bastankhah": "Bastankhah & Porté-Agel 2014",
          "niayifar": "Niayifar & Porté-Agel 2016", "turbopark": "TurbOPark (Nygaard 2022)", "nowake": "No wake"}
ZONE_OF = {"Netherlands": "NL", "United Kingdom": None, "Germany": "DE-LU", "Denmark": "DK1", "France": "FR",
           "Belgium": "BE", "Estonia": "EE", "Sweden": "SE4", "Finland": "FI", "Ireland": "IE(SEM)", "Norway": None}


def dump(rel: str, obj, indent=None) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=None if indent else (",", ":"), indent=indent, ensure_ascii=False), encoding="utf-8")


def load(rel: str):
    return json.loads((SRC / rel).read_text(encoding="utf-8"))


def r1(x):
    return None if x is None else round(x, 1)


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%MZ")


def site() -> list[dict]:
    s = load("site.json")
    farms = [f for f in s["farms"] if int(f["id"]) in FARMS]
    # farms point at turbine types by index (f["ti"]: int or per-turbine list): keep the used types, remap the indices
    used = sorted({g for f in farms if f.get("ti") is not None for g in (f["ti"] if isinstance(f["ti"], list) else [f["ti"]])})
    remap = {g: i for i, g in enumerate(used)}
    types = [s["types"][g] for g in used]
    farms = [{**f, "ti": None if f.get("ti") is None else
              ([remap[g] for g in f["ti"]] if isinstance(f["ti"], list) else remap[f["ti"]])} for f in farms]
    def thin(r):  # every 4th point of a coastline (flat lon, lat list), first and last kept
        pts = [(r[i], r[i + 1]) for i in range(0, len(r) - 1, 2)]
        keep = pts if len(pts) <= 8 else pts[::4] + [pts[-1]]
        return [v for q in keep for v in q]
    coast = [thin(r) for r in s["coast"]]
    dump("site.json", {**s, "farms": farms, "types": types, "zones": s["zones"][:40], "coast": coast})
    return farms


def feed(farms: list[dict]) -> None:
    past = [NOW - timedelta(hours=23 - i) for i in range(24)]
    fut = [NOW + timedelta(hours=i + 1) for i in range(24)]
    out = {}
    for k, f in enumerate(farms):
        cap = float(f.get("cap") or f.get("inst") or 100)
        U = [8 + 4 * math.sin((h + k) / 5) for h in range(48)]
        cf = [min(1.0, max(0.0, ((u - 3) / 9) ** 3)) if u < 25 else 0 for u in U]
        P = {m: [r1(cap * c * (1 - loss)) for c in cf] for m, loss in
             zip(MODELS, (0.12, 0.10, 0.09, 0.14, 0.0))}
        out[str(f["id"])] = {"U": [r1(u) for u in U[:24]], "dir": [(240 + 3 * h) % 360 for h in range(24)],
                             "P": {m: v[:24] for m, v in P.items()},
                             "fU": [r1(u) for u in U[24:]], "fdir": [(250 + 2 * h) % 360 for h in range(24)],
                             "fP": {m: v[24:] for m, v in P.items()}}
    prices = {}
    for j, z in enumerate(PRICE_ZONES):
        base = 160 - 4 * j if z not in ("LT", "LV", "EE", "FI") else 40
        v = [r1(base + 70 * math.sin((h - 8 + j % 3) / 24 * 2 * math.pi) + (-60 if z == "GR" and 9 <= h % 24 <= 13 else 0))
             for h in range(48)]
        if z == "GB":
            v = v[:23] + [None] * 25            # Market Index: past hours only
        elif j % 2:
            v = v[:34] + [None] * 14            # tomorrow's auction not in yet for some zones
        prices[z] = v
    tech = {"nuclear": 1400, "fossil_gas": 500, "fossil_brown_coal_lignite": 300, "hydro_run_of_river": 50,
            "biomass": 150, "solar": 2000, "wind_onshore": 300, "wind_offshore": 0}
    names = {"nuclear": "Nuclear", "fossil_gas": "Fossil gas", "fossil_brown_coal_lignite": "Lignite",
             "hydro_run_of_river": "Run-of-river", "biomass": "Biomass", "solar": "Solar", "wind_onshore": "Wind onshore",
             "wind_offshore": "Wind offshore", "load": "Load"}
    system = {}
    for k, (c, zs, name, nb) in enumerate([("hu", ["HU"], "Hungary", ["sk", "at", "ro", "rs", "hr"]),
                                           ("bg", ["BG"], "Bulgaria", ["ro", "rs", "gr", "mk"]),
                                           ("gr", ["GR"], "Greece", ["bg", "mk", "al", "it"]),
                                           ("cz", ["CZ"], "Czechia", ["de", "pl", "sk", "at"]),
                                           ("gb", ["GB"], "Great Britain", ["fr", "nl", "be", "no2", "dk1", "ie"]),
                                           ("lt", ["LT"], "Lithuania", ["lv", "pl", "se"])]):
        ser = {}
        for t, mw in tech.items():
            shape = (lambda h: max(0.0, math.sin((h - 6) / 24 * 2 * math.pi))) if t == "solar" else (lambda h: 0.8 + 0.2 * math.cos(h / 4))
            ser[t] = [r1(mw * (k + 1) / 3 * shape(h)) for h in range(24)]
        ser["load"] = [r1(sum(ser[t][h] for t in tech) * 1.05) for h in range(24)]
        if c == "bg":
            for t in ser:
                ser[t] = ser[t][:20] + [None] * 4     # a TSO reporting late
        flows = {n: [r1(300 * math.sin((h + i) / 6)) for h in range(24)] for i, n in enumerate(nb)}
        flows["sum"] = [r1(sum(flows[n][h] for n in nb)) for h in range(24)]
        system[c] = {"series": ser, "names": names, "flows": flows,
                     "flow_names": {**{n: n.upper() for n in nb}, "sum": "Net import"}, "zones": zs, "name": name,
                     "src": "entsoe", **({"lag_h": 4} if c == "bg" else {})}
    market = {"source": "synthetic test data (tests/fixtures/make_fixtures.py)",
              "farm_zone": {str(f["id"]): ZONE_OF.get(f["c"]) for f in farms}, "prices": prices,
              "restricted_zones": ["IE(SEM)"], "core_zones": sorted(z for z in PRICE_ZONES if z not in ("ES", "FI", "IT-North")),
              "actual_offshore": {}, "system": system, "price_source": {"GB": "elexon_mid"},
              "fx": {"GBP": {"rate": 0.85033, "date": "2026-10-02", "source": "ECB reference rate"}},
              "srmc": srmc_fixture()}
    dump("feed.json", {"schema": 1, "version": 1, "source": "openmeteo", "windy_model": None, "nwp_model": "ecmwf_ifs",
                       "generated": (NOW + timedelta(minutes=50)).isoformat(timespec="seconds"), "ref_heights_m": {"100": len(farms)},
                       "models": MODELS, "hours": [iso(d) for d in past], "fc_hours": [iso(d) for d in fut],
                       "market": market, "farms": out})


def static() -> None:
    shutil.copy(SRC / "zones.json", OUT / "zones.json")
    dump("gas.json", load("gas.json"))
    c = load("capture.json")
    keep = ["RO", "HU", "BG", "PL", "DE-LU", "GR", "NL", "GB"]
    months = c["months"][-13:]
    dump("capture.json", {**c, "months": months,
                          "zones": {z: {m: v for m, v in c["zones"][z].items() if m in months or not m[:2].isdigit()}
                                    for z in keep if z in c["zones"]}})
    g = load("gie.json")
    sub = lambda d: {a: {**v, "d": v["d"][-120:]} if isinstance(v, dict) and "d" in v else v
                     for a, v in d.items() if a in ("EU", "DE", "HU", "PL", "RO", "BG", "NL", "IT", "FR")}
    dump("gie.json", {**g, "storage": sub(g["storage"]), "lng": sub(g["lng"])})
    gr = load("grid.json")
    inbox = lambda c: any(-11 <= c[i] <= 32 and 36 <= c[i + 1] <= 66 for i in range(0, len(c), 2))
    lines = [[l[0], l[1], l[2] if l[0] == 0 else [v for i, v in enumerate(l[2]) if (i // 2) % 3 == 0 or i >= len(l[2]) - 2]]
             for l in gr["lines"] if (l[0] == 0 or l[0] >= 380) and inbox(l[2])]
    for l in lines:
        l[2] = l[2][: len(l[2]) - len(l[2]) % 2]
    dump("grid.json", {**gr, "lines": lines})
    b = load("bathy.json")
    from PIL import Image
    img = Image.open(SRC / "bathy.png").convert("L")
    w, h = max(1, img.width // 16), max(1, img.height // 16)
    small = img.resize((w, h), Image.NEAREST)
    buf = io.BytesIO()
    small.save(buf, format="PNG", optimize=True)
    (OUT / "bathy.png").write_bytes(buf.getvalue())
    dump("bathy.json", {**b, "w": w, "h": h, "res_per_deg": max(1, b.get("res_per_deg", 1) // 16)})


def browse() -> None:
    src = BUILT / "browse"
    idx = json.loads((src / "index.json").read_text())
    keep_days = 8
    zs = [z for z in TS_ZONES if (src / "ts" / f"{z}.json").exists()]
    first = None
    for z in zs:
        t = json.loads((src / "ts" / f"{z}.json").read_text())
        n = len(t["v"][0]) if t["v"] else 0
        cut = max(0, n - 24 * (keep_days + 2))
        first = t["t0"] + cut * t["step"]
        dump(f"browse/ts/{z}.json", {**t, "schema": 1, "t0": first, "v": [col[cut:] for col in t["v"]]})
    dump("browse/index.json", {**idx, "schema": 1, "zones": zs, "avail": {z: idx["avail"][z] for z in zs if z in idx["avail"]}})
    days = json.loads((src / "flags" / "index.json").read_text())["days"][:3]
    for d in days:
        f = json.loads((src / "flags" / f"{d}.json").read_text())
        dump(f"browse/flags/{d}.json", {**f, "schema": 1, "days": days})
    f0 = json.loads((src / "flags" / f"{days[0]}.json").read_text())
    dump("browse/flags.json", {**f0, "schema": 1, "days": days})
    dump("browse/flags/index.json", {"schema": 1, "days": days, "keep_days": 14})
    for name in ("capacity.json", "xflow.json", "agg.json"):
        if (src / name).exists():
            dump(f"browse/{name}", {**json.loads((src / name).read_text()), "schema": 1})


def newsletter() -> None:
    src = BUILT / "newsletter"
    idx = json.loads((src / "index.json").read_text())
    days = [d for d in idx["days"]][:2]
    for d in days:
        shutil.copy(src / f"{d['day']}.md", OUT / "newsletter" / f"{d['day']}.md")
    dump("newsletter/index.json", {**idx, "schema": 1, "days": days, "latest": days[0]["day"]}, indent=1)


def srmc_fixture() -> dict:
    """Synthetic per-technology SRMC table (feed.market.srmc) for the merit order on the Flags drill-down: a made-up gas
    price of 35 EUR/MWh and an EUA of 70 EUR/t, no coal or oil file, for the fixture days. Not real fuel data."""
    import pandas as pd
    from newsletter import fuel
    ttf = pd.Series([35.0], index=[pd.Timestamp("2026-01-01")])
    eua = pd.Series([70.0], index=[pd.Timestamp("2026-01-01")])
    days = pd.date_range(pd.Timestamp(NOW.date()) - pd.Timedelta(days=31), pd.Timestamp(NOW.date()) + pd.Timedelta(days=1))
    return {"days": {d.strftime("%Y-%m-%d"): fuel.srmc_table(d, ttf, eua) for d in days}, "carbon": True,
            "tech": {k: {"label": t["label"], "eta": t["eta"], "ef": t["ef"]} for k, t in fuel.TECH.items()},
            "note": "synthetic test values (tests/fixtures/make_fixtures.py)"}


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "newsletter").mkdir(parents=True)
    farms = site()
    feed(farms)
    static()
    browse()
    newsletter()
    import subprocess
    import sys
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_meta.py"), "--data", str(OUT)], check=True)
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"fixtures: {sum(1 for p in OUT.rglob('*') if p.is_file())} files, {size / 1e6:.2f} MB in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
