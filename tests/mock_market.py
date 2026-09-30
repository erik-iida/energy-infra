"""Offline test of pipeline.market against a fake Energy-Charts API (same response format, no network).

    python -m tests.mock_market
"""
import json
import math
import shutil
from datetime import datetime, timedelta, timezone

import requests

from pipeline import config
import pipeline.market as M

M.MIN_GAP_S = 0
CALLS = []


def _parse(s, end=False):
    if len(s) == 10:
        d = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return d + timedelta(days=1) if end else d
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class _R:
    def __init__(self, code, j):
        self.status_code, self._j, self.text = code, j, json.dumps(j)[:200]

    def json(self):
        return self._j


def fake_get(self, url, params, timeout):
    ep = url.rsplit("/", 1)[-1]
    CALLS.append((ep, params.get("bzn") or params.get("country")))
    a, b = _parse(params["start"]), _parse(params["end"], True)
    now = datetime.now(timezone.utc)
    rows, t = [], a
    while t < b:
        h = t.timestamp() / 3600
        if ep == "price":
            rows.append({"timestamp": t.isoformat(), "values": {"day_ahead_price": 80 + 60 * math.sin(h / 5)}})
        elif t <= now:
            rows.append({"timestamp": t.isoformat(), "values": {"wind_offshore": 3000 + 2500 * math.sin(h / 7)}})
        t += timedelta(minutes=15)
    if ep == "price":
        lic = ("restricted to private and internal use" if params["bzn"] == "SE4"
               else "CC BY 4.0 (creativecommons.org/licenses/by/4.0) from Bundesnetzagentur | SMARD.de")
        return _R(200, {"license": lic, "series": [{"id": "day_ahead_price", "name": "p"}], "data": rows})
    has_off = params["country"] != "uk"
    series = [{"id": "solar", "name": "s"}] + ([{"id": "wind_offshore", "name": "w"}] if has_off else [])
    if not has_off:
        rows = [{"timestamp": r["timestamp"], "values": {"solar": 0}} for r in rows]
    return _R(200, {"license": "CC BY 4.0, attribution: energy-charts.info", "series": series, "data": rows})


def main():
    shutil.rmtree(config.STATE_DIR, ignore_errors=True)
    requests.Session.get = fake_get
    site = json.loads(config.SITE_JSON.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hrs = [(now + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00Z") for h in range(-23, 25)]
    for run in range(1, 13):
        CALLS.clear()
        mk, hist = M.build(site["farms"], hrs)
        if run in (1, 2, 12):
            print(f"run {run}: {len(CALLS)} calls, history months per area:",
                  {k: len(v["months"]) for k, v in hist["areas"].items()})
    assert mk["restricted_zones"] == ["SE4"], mk["restricted_zones"]
    assert "SE4" not in mk["prices"] and "DK1" in mk["prices"]
    assert "uk" not in mk["actual_offshore"]
    assert all(len(v["months"]) >= 6 for v in hist["areas"].values()), hist["areas"].keys()
    print("sample", hist["areas"]["dk"]["months"][-1])
    print("OK")
    shutil.rmtree(config.STATE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
