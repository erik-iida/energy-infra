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
]


def percentile(hist: pd.Series, value: float) -> float:
    return float((hist <= value).mean())


def evaluate(metrics: pd.DataFrame, day: pd.Timestamp, rules=RULES, window: int = WINDOW_DAYS,
             min_hist: int = MIN_HIST) -> list[dict]:
    """Fired signals for `day`, strongest first. metrics: zone, day, metric, value."""
    out = []
    start = day - pd.Timedelta(days=window)
    for r in rules:
        m = metrics[metrics["metric"] == r.metric]
        today = m[m["day"] == day].set_index("zone")["value"]
        hist = m[(m["day"] >= start) & (m["day"] < day)]
        for zone, v in today.items():
            h = hist.loc[hist["zone"] == zone, "value"]
            if len(h) < min_hist or pd.isna(v):
                continue
            if r.min_abs is not None and abs(v) < r.min_abs:
                continue
            p = percentile(h, v)
            side = "high" if (r.hi is not None and p >= r.hi) else "low" if (r.lo is not None and p <= r.lo) else None
            if side is None:
                continue
            scale = 100.0 if r.unit == "%" else 1.0
            out.append({"zone": zone, "metric": r.metric, "label": r.label, "unit": r.unit, "side": side,
                        "value": round(v * scale, 1), "pct": round(p, 3), "n_hist": int(len(h)),
                        "median": round(float(h.median()) * scale, 1),
                        "p10": round(float(h.quantile(0.1)) * scale, 1), "p90": round(float(h.quantile(0.9)) * scale, 1),
                        "score": round(r.weight * (p if side == "high" else 1 - p), 4)})
    return sorted(out, key=lambda s: -s["score"])
