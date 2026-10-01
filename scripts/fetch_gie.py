"""Gas storage (AGSI+) and LNG terminals (ALSI) from GIE. Needs a free API key in env GIE_KEY.

    python scripts/fetch_gie.py           # download (needs GIE_KEY), then build web/data/gie.json
    python scripts/fetch_gie.py --local   # rebuild from data/raw/gie/*.json

Data: GIE AGSI+ / ALSI transparency platforms (Gas Infrastructure Europe), https://agsi.gie.eu, https://alsi.gie.eu
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "gie"
OUT = ROOT / "web" / "data" / "gie.json"
LOG = RAW / "gie_log.txt"
log_lines: list[str] = []


def log(m: str) -> None:
    print(m, flush=True)
    log_lines.append(m)


def get(base: str, key: str, **params) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(base, params=params, headers={"x-key": key, "User-Agent": "energy-infra-monitor/1.0"}, timeout=60)
            if r.status_code == 200:
                return r.json()
            log(f"  {base} {params}: HTTP {r.status_code} {r.text[:150]!r}")
        except Exception as ex:
            log(f"  {base} {params}: {ex!r}")
        time.sleep(5 * (attempt + 1))
    return None


def pages(base: str, key: str, **params) -> list[dict]:
    out, page = [], 1
    while True:
        r = get(base, key, size=300, page=page, **params)
        if not r:
            break
        data = r.get("data", [])
        out += data if isinstance(data, list) else [data]
        if page >= int(r.get("last_page", 1) or 1):
            break
        page += 1
        time.sleep(1.2)
    return out


def download(key: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    frm, to = (date.today() - timedelta(days=400)).isoformat(), date.today().isoformat()
    for name, base in (("agsi", "https://agsi.gie.eu/api"), ("alsi", "https://alsi.gie.eu/api")):
        about = get(base + "/about", key, show="listing")
        if about is not None:
            (RAW / f"{name}_about.json").write_text(json.dumps(about), encoding="utf-8")
            log(f"{name} about: type {type(about).__name__}, keys {list(about)[:10] if isinstance(about, dict) else len(about)}")
        eu = pages(base, key, type="eu", **{"from": frm, "to": to})
        log(f"{name} eu: {len(eu)} rows; sample {json.dumps(eu[0])[:700] if eu else None}")
        (RAW / f"{name}_eu.json").write_text(json.dumps(eu), encoding="utf-8")
        cc = {}
        for c in ("AT", "BE", "BG", "HR", "CZ", "DK", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "NL", "PL", "PT", "RO",
                  "SK", "SI", "ES", "SE", "GB", "UA", "RS", "EE", "MT", "CY"):
            rows = pages(base, key, country=c, **{"from": frm, "to": to})
            if rows:
                cc[c] = rows
            time.sleep(1.2)
        log(f"{name} countries with data: {sorted(cc)}; sample {json.dumps(next(iter(cc.values()))[0])[:900] if cc else None}")
        (RAW / f"{name}_countries.json").write_text(json.dumps(cc), encoding="utf-8")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build() -> None:
    """web/data/gie.json: per area (EU + countries), daily series oldest -> newest:
    storage: day, full %, gas in storage TWh, injection / withdrawal GWh/d, working gas volume TWh
    lng: day, send-out GWh/d, inventory GWh"""
    out = {"src": "GIE AGSI+ / ALSI", "storage": {}, "lng": {}}
    for name in ("agsi", "alsi"):
        eu = RAW / f"{name}_eu.json"
        cc = RAW / f"{name}_countries.json"
        if not eu.exists() or not cc.exists():
            continue
        areas = {"EU": json.loads(eu.read_text(encoding="utf-8")), **json.loads(cc.read_text(encoding="utf-8"))}
        for a, rows in areas.items():
            rows = sorted(rows, key=lambda r: r.get("gasDayStart", ""))
            if name == "agsi":
                ser = [[r["gasDayStart"], num(r.get("full")), num(r.get("gasInStorage")), num(r.get("injection")),
                        num(r.get("withdrawal")), num(r.get("workingGasVolume"))] for r in rows if num(r.get("full")) is not None]
                if ser and max(x[5] or 0 for x in ser) > 0:
                    out["storage"][a] = {"n": rows[0].get("name", a), "d": ser}
            else:
                ser = []
                for r in rows:
                    so = num(r.get("sendOut"))
                    inv = r.get("inventory")
                    inv = num(inv.get("gwh")) if isinstance(inv, dict) else None
                    if so is not None:
                        ser.append([r["gasDayStart"], so, inv])
                if ser and any(x[1] for x in ser):
                    out["lng"][a] = {"d": ser}
    if not out["storage"] and not out["lng"]:
        log("no GIE data to build")
        return
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log(f"wrote {OUT.relative_to(ROOT)}: storage {len(out['storage'])} areas, LNG {len(out['lng'])} areas, "
        f"{OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    try:
        if "--local" not in sys.argv:
            k = os.environ.get("GIE_KEY", "")
            if not k:
                log("GIE_KEY not set; skipping download")
            else:
                download(k)
        build()
    finally:
        RAW.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
