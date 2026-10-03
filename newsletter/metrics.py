"""Daily market metrics from the data store (collector/store.py): one row per zone, CET delivery day and metric.

Prices: ENTSO-E A44 at native resolution, seq 1 only (the auction result), EUR only (UA-IPS is published in UAH and
left out until its conversion is wired in), averaged to hours first so TB2/TB4 mean the same as on the site
(mean of the 2 / 4 highest minus the 2 / 4 lowest hourly prices of the CET day). A day needs >= 23 priced hours
(23 / 24 / 25 with DST) to count.
Capture price per technology: sum(generation x price) / sum(generation) over the hours that have both; the day needs
>= 20 such hours of generation data (zeros count, so solar's night hours do). Capture rate = capture price / the zone's baseload that day.
"""
from __future__ import annotations

import pandas as pd

CET = "Europe/Brussels"
TECH = {"B16": "solar", "B18": "wind_offshore", "B19": "wind_onshore"}
MIN_PRICE_HOURS = 23
MIN_CAPTURE_HOURS = 20


def hourly_prices(da: pd.DataFrame) -> pd.DataFrame:
    """zone, h (UTC hour start), price - from raw da_price rows."""
    if da is None or da.empty:
        return pd.DataFrame(columns=["zone", "h", "price"])
    d = da[(da["seq"] == 1) & (da["currency"] == "EUR")].copy()
    d["h"] = d["ts"].dt.floor("h")
    return d.groupby(["zone", "h"], as_index=False)["price"].mean()


def hourly_generation(ga: pd.DataFrame) -> pd.DataFrame:
    """zone, tech, h, mw (hourly mean) for solar and wind - from raw gen_actual rows."""
    if ga is None or ga.empty:
        return pd.DataFrame(columns=["zone", "tech", "h", "mw"])
    d = ga[(ga["dir"] == "gen") & (ga["psr"].isin(TECH))].copy()
    d["tech"] = d["psr"].map(TECH)
    d["h"] = d["ts"].dt.floor("h")
    return d.groupby(["zone", "tech", "h"], as_index=False)["mw"].mean()


def _local_day(h: pd.Series) -> pd.Series:
    return h.dt.tz_convert(CET).dt.tz_localize(None).dt.normalize()


def price_metrics(hp: pd.DataFrame) -> pd.DataFrame:
    """zone, day, metric, value for baseload, tb2, tb4, neg_hours, price_min, price_max, price_hours."""
    if hp.empty:
        return pd.DataFrame(columns=["zone", "day", "metric", "value"])
    hp = hp.assign(day=_local_day(hp["h"]))
    rows = []
    for (zone, day), g in hp.groupby(["zone", "day"]):
        v = sorted(g["price"])
        n = len(v)
        rows.append((zone, day, "price_hours", float(n)))
        if n < MIN_PRICE_HOURS:
            continue
        rows += [(zone, day, "baseload", sum(v) / n),
                 (zone, day, "tb2", sum(v[-2:]) / 2 - sum(v[:2]) / 2),
                 (zone, day, "tb4", sum(v[-4:]) / 4 - sum(v[:4]) / 4),
                 (zone, day, "top4", sum(v[-4:]) / 4),
                 (zone, day, "neg_hours", float(sum(1 for x in v if x < 0))),
                 (zone, day, "price_min", v[0]), (zone, day, "price_max", v[-1])]
    return pd.DataFrame(rows, columns=["zone", "day", "metric", "value"])


def capture_metrics(hp: pd.DataFrame, hg: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """zone, day, metric (capture_<tech>, cr_<tech>), value. `base` = price_metrics rows."""
    cols = ["zone", "day", "metric", "value"]
    if hp.empty or hg.empty:
        return pd.DataFrame(columns=cols)
    j = hg.merge(hp, on=["zone", "h"])
    if j.empty:
        return pd.DataFrame(columns=cols)
    j["mw"] = j["mw"].clip(lower=0)  # zero hours (solar at night) count as covered, negative readings as zero
    j["day"] = _local_day(j["h"])
    j["wp"] = j["mw"] * j["price"]
    g = j.groupby(["zone", "tech", "day"]).agg(e=("mw", "sum"), wp=("wp", "sum"), n=("mw", "size")).reset_index()
    g = g[(g["n"] >= MIN_CAPTURE_HOURS) & (g["e"] > 0)]
    g["capture"] = g["wp"] / g["e"]
    bl = base[base["metric"] == "baseload"].rename(columns={"value": "baseload"})[["zone", "day", "baseload"]]
    g = g.merge(bl, on=["zone", "day"], how="left")
    out = [g.assign(metric="capture_" + g["tech"], value=g["capture"])[cols]]
    ok = g[g["baseload"].abs() >= 5]  # a capture *rate* is meaningless around zero baseload
    out.append(ok.assign(metric="cr_" + ok["tech"], value=ok["capture"] / ok["baseload"])[cols])
    return pd.concat(out, ignore_index=True)


def spark_metrics(pm: pd.DataFrame, srmc: pd.Series) -> pd.DataFrame:
    """spark_base / spark_top4 = baseload / mean of the 4 highest hourly prices minus the reference gas SRMC of the day
    (fuel-only or clean, see fuel.py). The SRMC itself is deliberately NOT returned: it is derived from private data."""
    cols = ["zone", "day", "metric", "value"]
    if srmc is None or srmc.empty or pm.empty:
        return pd.DataFrame(columns=cols)
    w = pm[pm["metric"].isin(["baseload", "top4"])].pivot_table(index=["zone", "day"], columns="metric", values="value").reset_index()
    w["srmc"] = w["day"].map(srmc)
    w = w.dropna(subset=["srmc"])
    out = [w.assign(metric="spark_base", value=w["baseload"] - w["srmc"])[cols],
           w.assign(metric="spark_top4", value=w["top4"] - w["srmc"])[cols]]
    return pd.concat(out, ignore_index=True)


def all_metrics(da: pd.DataFrame, ga: pd.DataFrame, srmc: pd.Series | None = None) -> pd.DataFrame:
    hp, hg = hourly_prices(da), hourly_generation(ga)
    pm = price_metrics(hp)
    parts = [pm, capture_metrics(hp, hg, pm)]
    if srmc is not None:
        parts.append(spark_metrics(pm, srmc))
    return pd.concat(parts, ignore_index=True)
