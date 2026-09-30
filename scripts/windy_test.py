"""Quick check of the Windy Point Forecast API key for one location (Horns Rev).

Usage (PowerShell):
    $env:WINDY_KEY = "your-key"
    python windy_test.py

Uses one call per model tried (5 in total), well under the daily limit.
"""
import os
import sys
from datetime import datetime, timezone

import requests

KEY = os.environ.get("WINDY_KEY")
if not KEY:
    sys.exit("Set the WINDY_KEY environment variable first.")

URL = "https://api.windy.com/api/point-forecast/v2"
LAT, LON = 55.53, 7.90  # Horns Rev
MODELS = ["ecmwf", "iconEu", "gfs", "arome", "icon"]

for model in MODELS:
    body = {
        "lat": LAT,
        "lon": LON,
        "model": model,
        "parameters": ["wind"],
        "levels": ["surface", "1000h", "950h"],
        "key": KEY,
    }
    r = requests.post(URL, json=body, timeout=20)
    if r.status_code != 200:
        print(f"{model:7s} -> HTTP {r.status_code}: {r.text[:150]}")
        continue
    d = r.json()
    ts = d["ts"]
    step_h = (ts[1] - ts[0]) / 3.6e6 if len(ts) > 1 else float("nan")
    first = datetime.fromtimestamp(ts[0] / 1000, timezone.utc)
    last = datetime.fromtimestamp(ts[-1] / 1000, timezone.utc)
    print(f"{model:7s} -> OK  {len(ts)} steps, every {step_h:.0f} h, {first:%d %b %H:%M} to {last:%d %b %H:%M} UTC")
    for lev in ["surface", "1000h", "950h"]:
        u, v = d.get(f"wind_u-{lev}"), d.get(f"wind_v-{lev}")
        if u and v and u[0] is not None:
            ws = (u[0] ** 2 + v[0] ** 2) ** 0.5
            print(f"          {lev:8s} first step: {ws:4.1f} m/s")
    print("          keys:", ", ".join(k for k in d if k not in ("ts", "units")))
