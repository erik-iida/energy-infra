"""Gas flows from the ENTSOG Transparency Platform (public API, no token).

    python scripts/fetch_gas.py           # download raw data, then build web/data/gas.json
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
RAW = ROOT / "data" / "raw" / "gas"
OUT = ROOT / "web" / "data" / "gas.json"
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


if __name__ == "__main__":
    try:
        if "--local" not in sys.argv:
            download()
    finally:
        RAW.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
# touched to trigger
