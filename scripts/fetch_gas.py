"""Gas flows from the ENTSOG Transparency Platform (public API, no token).

    python scripts/fetch_gas.py           # download raw data, then build data/static/gas.json
    python scripts/fetch_gas.py --local   # rebuild gas.json from data/raw/gas/*.json

Raw: connection points (positions), daily physical flows for the last 8 gas days.
Data: ENTSOG Transparency Platform, https://transparency.entsog.eu
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import paths as config  # noqa: E402
RAW = ROOT / "data" / "raw" / "gas"
OUT = config.static_file("gas.json")
LOG = RAW / "gas_log.txt"
API = "https://transparency.entsog.eu/api/v1/"
UA = {"User-Agent": "energy-infra-monitor/1.0 (+https://github.com/erik-iida/energy-infra)"}
log_lines: list[str] = []


def log(m: str) -> None:
    print(m, flush=True)
    log_lines.append(m)


def get(endpoint: str, **params) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(API + endpoint, params={"limit": -1, **params}, headers=UA, timeout=90)
            if r.status_code == 200:
                return r.json()
            log(f"  {endpoint} {params}: HTTP {r.status_code} {r.text[:150]!r}")
        except Exception as ex:
            log(f"  {endpoint} {params}: {ex!r}")
        time.sleep(10 * (attempt + 1))
    return None


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    cp = get("connectionpoints")
    if cp:
        (RAW / "connectionpoints.json").write_text(json.dumps(cp), encoding="utf-8")
        items = cp.get("connectionpoints", cp.get("connectionPoints", []))
        log(f"connection points: {len(items)}; keys {list(items[0])[:60] if items else None}")
    ipd = get("interconnections")
    if ipd:
        (RAW / "interconnections.json").write_text(json.dumps(ipd), encoding="utf-8")
        items = ipd.get("interconnections", [])
        log(f"interconnections: {len(items)}; keys {list(items[0])[:60] if items else None}")
    flows = []
    today = date.today()
    for d in range(8, 0, -1):  # one request per gas day keeps each query under the 60 s timeout
        a = today - timedelta(days=d)
        r = get("operationaldatas", indicator="Physical Flow", periodType="day", **{"from": a.isoformat(), "to": a.isoformat()},
                timezone="CET")
        if r:
            items = r.get("operationaldatas", r.get("operationalDatas", []))
            log(f"flows {a}: {len(items)} rows" + (f"; keys {list(items[0])}" if items and d == 8 else ""))
            flows += items
        time.sleep(2)
    (RAW / "flows.json").write_text(json.dumps(flows), encoding="utf-8")


# ---- georeferencing: ENTSOG positions are schematic map coordinates (tpMapX/Y). A cubic fit to known points
# plus inverse-distance correction from the 5 nearest anchors gives ~20 km median error (leave-one-out).
A={'Ellund':(54.807,9.289),'Dornum':(53.643,7.437),'Emden (EPT1)':(53.36,7.21),'Mallnow':(52.44,14.49),'Swinoujscie':(53.93,14.27),'Zeebrugge IZT':(51.33,3.20),
'Easington':(53.65,0.12),'Inkoo':(60.04,24.0),'Gate LNG':(51.97,4.05),'Dunkerque LNG':(51.04,2.27),'Sines':(37.95,-8.86),'Barcelona':(41.34,2.16),'Revithoussa':(37.96,23.40),
'Krk':(45.25,14.56),'Klaipeda':(55.67,21.14),'Baumgarten':(48.32,16.86),'Oltingue':(47.49,7.39),'Greifswald':(54.14,13.68),'Tarvisio':(46.50,13.58),'Mazara':(37.65,12.59),
'Melendugno':(40.27,18.43),'Kipi':(40.95,26.30),'Moffat':(55.33,-3.44),'Bacton':(52.86,1.46),'Wilhelmshaven':(53.57,8.13),'Brunsb':(53.89,9.20),'Eemshaven':(53.45,6.83),
'Fos':(43.42,4.85),'Montoir':(47.30,-2.15),'Le Havre':(49.47,0.14),'Huelva':(37.15,-6.95),'Bilbao':(43.36,-3.06),'Rovigo':(45.09,12.59),'Piombino':(42.93,10.53),
'Alexandroupolis':(40.79,25.83),'Nybro':(55.67,8.30),'Imatra':(61.19,28.77),'Mosonmagyar':(47.87,17.27),'Oude Statenzijl':(53.20,7.20),'Bocholtz':(50.82,6.03),
'Eynatten':(50.69,6.08),'Taisnières':(50.15,3.97),'Medelsheim':(49.11,7.25),'Waidhaus':(49.64,12.49),'Lanžhot':(48.70,16.97),'Kondratki':(52.55,23.75),
'Wysokoje':(52.12,23.68),'Isaccea':(45.27,28.46),'Negru Voda':(43.82,28.21),'Kulata':(41.38,23.37),'Gorizia':(45.94,13.62),'Passo Gries':(46.46,8.38),
'Irun':(43.34,-1.79),'Badajoz':(38.88,-6.97),'Tuy':(42.05,-8.64),'Almeria':(36.83,-2.46),'Tarifa':(36.01,-5.60),'Gela':(37.07,14.25),'Kiemenai':(56.40,24.10),
'Karksi':(57.94,25.56),'Värska':(57.95,27.63),'Dragør':(55.59,12.68),'Faxe':(55.25,12.12),'Egtved':(55.62,9.29),'Budince':(48.55,22.13),'Beregdaróc':(48.20,22.55)}


def georef(cp: list[dict]):
    import numpy as np
    X, Y = [], []
    for n, (la, lo) in A.items():
        m = [p for p in cp if p["pointLabel"].lower().startswith(n.lower()) and p["tpMapX"] is not None] or \
            [p for p in cp if n.lower() in p["pointLabel"].lower() and p["tpMapX"] is not None]
        if m:
            X.append((m[0]["tpMapX"], m[0]["tpMapY"]))
            Y.append((lo, la))
    X, Y = np.array(X, float), np.array(Y, float)

    def feats(x):
        cols = [np.ones(len(x))]
        for d in range(1, 4):
            for i in range(d + 1):
                cols.append(x[:, 0] ** (d - i) * x[:, 1] ** i)
        return np.column_stack(cols)
    c, *_ = np.linalg.lstsq(feats(X), Y, rcond=None)
    res = Y - feats(X) @ c

    def f(x: float, y: float) -> tuple[float, float]:
        q = np.array([[x, y]])
        out = (feats(q) @ c)[0]
        d = np.hypot(*(X - q[0]).T) + 1e-6
        idx = np.argsort(d)[:5]
        w = 1 / d[idx] ** 2
        out = out + (w[:, None] * res[idx]).sum(0) / w.sum()
        return round(float(out[0]), 3), round(float(out[1]), 3)
    log(f"georef: {len(X)} anchor points")
    return f


TYPE = {"Cross-Border Transmission IP within EU": "ip", "Cross-Border Transmission IP between EU and Non-EU (import)": "imp",
        "Cross-Border Transmission IP between EU and Non-EU": "ip", "Cross-Border Transmission IP between EU and ExtEU": "ip",
        "Cross-Border Transmission IP between ExtEU and Non-EU (import)": "imp", "LNG Entry point": "lng",
        "Aggregated production point - TP": "prod"}


def build() -> None:
    cp = json.loads((RAW / "connectionpoints.json").read_text(encoding="utf-8"))
    cp = cp.get("connectionpoints", cp.get("connectionPoints", []))
    flows = json.loads((RAW / "flows.json").read_text(encoding="utf-8"))
    pos = georef(cp)
    days = sorted({f["periodFrom"][:10] for f in flows})
    # per point, day, operator country: entry and exit energy (GWh/d)
    agg: dict = {}
    for f in flows:
        if f.get("value") is None or f.get("unit") != "kWh/d":
            continue
        try:
            v = float(f["value"])
        except (TypeError, ValueError):
            continue
        c = (f.get("operatorKey") or "")[:2].upper()
        k = (f["pointKey"], f["periodFrom"][:10], c, f["directionKey"])
        agg[k] = agg.get(k, 0) + v / 1e6
    byp: dict = {}
    for k, v in agg.items():
        byp.setdefault(k[0], {})[k] = v
    pts = []
    for p in cp:
        t = TYPE.get(p.get("pointType"))
        if not t or p.get("tpMapX") is None or p.get("isInvalid"):
            continue
        rows = byp.get(p["pointKey"], {})
        if not rows:
            continue
        ctry = sorted({k[2] for k in rows})
        series, dirs = [], []
        for d in days:
            ent = {c: rows.get((p["pointKey"], d, c, "entry"), 0) for c in ctry}
            ext = {c: rows.get((p["pointKey"], d, c, "exit"), 0) for c in ctry}
            to = max(ent, key=ent.get) if any(ent.values()) else None
            frm = max(ext, key=ext.get) if any(ext.values()) else None
            v = max(max(ent.values() or [0]), max(ext.values() or [0]))
            series.append(round(v, 1))
            dirs.append([frm if frm != to else None, to])
        if not any(series):
            continue
        lon, lat = pos(p["tpMapX"], p["tpMapY"])
        pts.append({"k": p["pointKey"], "n": p["pointLabel"], "t": t, "lon": lon, "lat": lat, "v": series, "d": dirs[-1],
                    "from": p.get("importFromCountryLabel")})
    # country balance: pipeline imports by source country, LNG and production, per day (GWh/d)
    cb: dict = {}
    for pt in pts:
        for i, d in enumerate(days):
            key = None
            rows = byp.get(pt["k"], {})
            ent = {k[2]: v for k, v in rows.items() if k[1] == d and k[3] == "entry"}
            ext = {k[2]: v for k, v in rows.items() if k[1] == d and k[3] == "exit"}
            for c, v in ent.items():
                if pt["t"] == "lng":
                    src = "LNG"
                elif pt["t"] == "prod":
                    src = "Production"
                else:
                    others = {cc: vv for cc, vv in ext.items() if cc != c}
                    src = max(others, key=others.get) if others else (pt.get("from") or "Import")
                cb.setdefault(c, {}).setdefault(src, [0.0] * len(days))[i] += v
    cb = {c: {s: [round(x, 1) for x in v] for s, v in d.items()} for c, d in cb.items()}
    OUT.write_text(json.dumps({"src": "ENTSOG Transparency Platform", "unit": "GWh/d", "days": days, "points": pts,
                               "countries": cb}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log(f"wrote {OUT.relative_to(ROOT)}: {len(pts)} points ({', '.join(t + ' ' + str(sum(1 for q in pts if q['t'] == t)) for t in ('ip', 'imp', 'lng', 'prod'))}), "
        f"{len(cb)} countries, {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    try:
        if "--local" not in sys.argv:
            download()
        build()
    finally:
        RAW.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
