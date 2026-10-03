"""Universal signal framework: every rule looks at one metric per zone, compares the target day with that zone's own
trailing history and fires when the day sits in the tail of it. Add a rule = add a line to RULES.

A rule fires when percentile >= hi (value unusually high) or <= lo (unusually low), the trailing window has at least
`min_hist` days, and the absolute gate `min_abs` holds (so "90th percentile of a tiny number" does not fire).
percentile = share of the trailing days whose value is <= the target day's value (0..1).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

WINDOW_DAYS = 90
MIN_HIST = 30


@dataclass(frozen=True)
class Rule:
    metric: str
    label: str
    unit: str
    hi: float | None = 0.90
    lo: float | None = None
    min_abs: float | None = None  # |value| must be at least this
    weight: float = 1.0           # ranking among fired signals


RULES = [
    Rule("tb4", "4-hour storage spread (TB4)", "EUR/MWh", hi=0.90, min_abs=40, weight=1.2),
    Rule("tb2", "2-hour storage spread (TB2)", "EUR/MWh", hi=0.90, min_abs=40, weight=1.0),
    Rule("neg_hours", "negative-price hours", "h", hi=0.90, min_abs=3, weight=1.1),
    Rule("spark_top4", "top-4-hour spark spread", "EUR/MWh", hi=0.90, lo=0.10, weight=1.0),
    Rule("baseload", "baseload price", "EUR/MWh", hi=0.95, lo=0.05, weight=0.9),
    Rule("cr_wind_onshore", "onshore wind capture rate", "%", hi=None, lo=0.10, weight=1.0),
    Rule("cr_wind_offshore", "offshore wind capture rate", "%", hi=None, lo=0.10, weight=1.0),
    Rule("cr_solar", "solar capture rate", "%", hi=None, lo=0.10, weight=0.8),
    # residual load = load - wind - solar (registry.py): tight evenings, deep surplus, steep ramps
    Rule("res_peak", "peak residual load", "MW", hi=0.90, min_abs=500, weight=1.0),
    Rule("res_min", "lowest residual load (wind + solar surplus)", "MW", hi=None, lo=0.10, min_abs=300, weight=0.9),
    Rule("res_ramp3", "3-hour residual-load ramp", "MW", hi=0.90, min_abs=500, weight=0.9),
    # physical cross-border flows of the whole zone; min_abs is a ratio (0.05 = 5 % of load)
    Rule("import_share", "net import share of load", "%", hi=0.90, lo=0.10, min_abs=0.05, weight=1.0),
]


# Display-only rows (never fire: no hi / lo): the 'what else was unusual' table under a flag on the site's Flags tab.
CONTEXT = [
    Rule("price_max", "highest hourly price", "EUR/MWh", hi=None),
    Rule("price_min", "lowest hourly price", "EUR/MWh", hi=None),
    Rule("gen_wind_onshore", "onshore wind output", "MW", hi=None),
    Rule("gen_wind_offshore", "offshore wind output", "MW", hi=None),
    Rule("gen_solar", "solar output", "MW", hi=None),
    Rule("wind_share_load", "wind output as share of load", "%", hi=None),
    Rule("solar_share_load", "solar output as share of load", "%", hi=None),
    Rule("vre_share", "wind + solar share of load", "%", hi=None),
    Rule("gas_share", "gas share of generation", "%", hi=None),
    Rule("load_mean", "load, daily mean", "MW", hi=None),
    Rule("res_mean", "residual load, daily mean", "MW", hi=None),
    Rule("net_import", "net import, daily mean", "MW", hi=None),
]


def percentile(hist: pd.Series, value: float) -> float:
    return float((hist <= value).mean())


def scan(metrics: pd.DataFrame, day: pd.Timestamp, rules=RULES, window: int = WINDOW_DAYS,
         min_hist: int = MIN_HIST) -> list[dict]:
    """Every (zone, rule) with a value on `day`: value, percentile against the zone's own trailing `window` days, the
    trailing median / p10 / p90, and `side` ("high" / "low") when the rule fires, else None. `status`: "ok" (enough
    history and passes the absolute gate), "short" (fewer than `min_hist` trailing days) or "gated" (below min_abs)."""
    out = []
    start = day - pd.Timedelta(days=window)
    for r in rules:
        m = metrics[metrics["metric"] == r.metric]
        today = m[m["day"] == day].set_index("zone")["value"]
        hist = m[(m["day"] >= start) & (m["day"] < day)]
        scale = 100.0 if r.unit == "%" else 1.0
        for zone, v in today.items():
            if pd.isna(v):
                continue
            h = hist.loc[hist["zone"] == zone, "value"]
            row = {"zone": zone, "metric": r.metric, "label": r.label, "unit": r.unit, "side": None,
                   "value": round(v * scale, 1), "pct": None, "n_hist": int(len(h)), "status": "ok",
                   "median": None, "p10": None, "p90": None, "score": 0.0}
            if len(h) < min_hist:
                row["status"] = "short"
            else:
                p = percentile(h, v)
                row.update(pct=round(p, 3), median=round(float(h.median()) * scale, 1),
                           p10=round(float(h.quantile(0.1)) * scale, 1), p90=round(float(h.quantile(0.9)) * scale, 1))
                if r.min_abs is not None and abs(v) < r.min_abs:
                    row["status"] = "gated"
                else:
                    side = "high" if (r.hi is not None and p >= r.hi) else "low" if (r.lo is not None and p <= r.lo) else None
                    if side:
                        row["side"] = side
                        row["score"] = round(r.weight * (p if side == "high" else 1 - p), 4)
            out.append(row)
    return out


def evaluate(metrics: pd.DataFrame, day: pd.Timestamp, rules=RULES, window: int = WINDOW_DAYS,
             min_hist: int = MIN_HIST) -> list[dict]:
    """Fired signals for `day`, strongest first. metrics: zone, day, metric, value."""
    fired = [r for r in scan(metrics, day, rules, window, min_hist) if r["side"]]
    for r in fired:
        del r["status"]
    return sorted(fired, key=lambda s: -s["score"])
