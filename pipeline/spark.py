"""Spark spreads for the site's Market tab (feed.market.spark), only when the repo variable SPARK is set (private|public).

Per zone and window (past 24 h / tomorrow): mean of the 4 highest hourly day-ahead prices minus the reference gas
cost, and baseload minus it (newsletter/fuel.py: TTF front month via yfinance, 55 % CCGT, fuel-only unless
newsletter/eua_manual.csv exists). The gas price and the reference cost are never written to the feed.

NOTE: the page also shows the hourly prices, so a reader could back out the reference cost (baseload - spark) and
with it the TTF price to within the rounding. Publishing the spreads therefore publishes the gas price de facto.
That is why this is off by default and gated behind a repo variable.
"""
from __future__ import annotations

import json
import time

from . import config

CACHE = "fuel_cache.json"


def _srmc() -> tuple[float, bool] | None:
    p = config.STATE_DIR / CACHE
    try:
        c = json.loads(p.read_text())
        if time.time() - c["t"] < 6 * 3600:
            return c["srmc"], c["carbon"]
    except Exception:
        pass
    import pandas as pd
    from newsletter import fuel
    today = pd.Timestamp.now(tz="Europe/Brussels").tz_localize(None).normalize()
    s, carbon = fuel.srmc_by_day(pd.DatetimeIndex([today]), fuel.load_ttf(), fuel.load_eua())
    if s.empty:
        return None
    val = float(s.iloc[0])
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"t": time.time(), "srmc": val, "carbon": carbon}))  # state/ lives in the Actions cache, not git
    return val, carbon


def _spread(v: list, srmc: float) -> dict | None:
    ok = sorted(x for x in v if x is not None)
    if len(ok) < 20:
        return None
    return {"top4": round(sum(ok[-4:]) / 4 - srmc, 1), "base": round(sum(ok) / len(ok) - srmc, 1)}


def build(prices: dict[str, list], n_past: int) -> dict | None:
    r = _srmc()
    if r is None:
        return None
    srmc, carbon = r
    out = {}
    for z, v in prices.items():
        d = {k: s for k, s in (("past", _spread(v[:n_past], srmc)), ("next", _spread(v[n_past:], srmc))) if s}
        if d:
            out[z] = d
    return {"zones": out, "carbon": carbon, "eta": 0.55,
            "source": "TTF front-month futures (ICE Endex) via Yahoo Finance; only derived spreads are shown"}
