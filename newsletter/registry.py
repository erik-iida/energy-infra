"""The catalogue of daily metrics: one place that says what every number means.

Everything that handles a daily metric (the metric functions in metrics.py, the signal rules in signals.py, the Data tab
export in scripts/build_browse.py, the stored `metrics_daily` table, the newsletter) reads its labels, units and families
from here, so a metric is defined once. A metric row is (zone, CET delivery day, metric id, value); `value` is stored in
the unit of the value as computed (ratios stay ratios, `scale` turns them into the displayed unit).

Classification (the `family` field):
  price_level    where prices sat                        baseload, top-4 mean
  storage_spread what a storage / flexible asset earns   TB2, TB4
  price_shape    how the day's prices were distributed   negative hours, lowest / highest hourly price
  capture        what a technology earned                capture price, capture rate (capture price / baseload)
  residual_load  load the dispatchable fleet, storage and imports must cover: load - wind - solar
  interconnection physical cross-border flows of the zone as a whole
  generation     what ran and how much was used: daily mean wind / solar output, gas share, load (context, no signal rules)
  fuel_spread    PRIVATE (uses yfinance data): never exported, never stored, never published

Each metric states the minimum number of hours a day needs (`min_hours`) so only complete days exist, and `direction`:
what a high value means for the system / for a flexible asset - the one-line semantics a model or a reader needs.
Changing the definition of an existing metric = bump VERSION (stored rows carry it).
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION = 3  # 1 = price + capture metrics, 2 = + residual load + interconnection, 3 = + generation / load / gas share


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    family: str
    unit: str            # displayed unit
    definition: str
    inputs: tuple        # store datasets it is computed from
    min_hours: int       # hours of every input a CET day needs
    direction: str       # what a high value means
    scale: float = 1.0   # displayed = value * scale (ratios -> %)
    tech: str = ""       # colour key on the site (sol, won, woff)
    private: bool = False


P = ("da_price",)
METRICS = [
    Metric("baseload", "Baseload price", "price_level", "EUR/MWh", "mean hourly day-ahead price of the CET day", P, 23,
           "expensive system day"),
    Metric("top4", "Top-4 hours mean", "price_level", "EUR/MWh", "mean of the 4 highest hourly prices", P, 23,
           "expensive peak"),
    Metric("tb2", "TB2 storage spread", "storage_spread", "EUR/MWh",
           "mean of the 2 highest minus the 2 lowest hourly prices (2-hour battery, before losses)", P, 23,
           "more arbitrage value for a 2 h battery"),
    Metric("tb4", "TB4 storage spread", "storage_spread", "EUR/MWh", "same with 4 hours", P, 23,
           "more arbitrage value for a 4 h battery"),
    Metric("neg_hours", "Negative-price hours", "price_shape", "h", "count of hourly prices below zero", P, 23,
           "more surplus hours"),
    Metric("price_min", "Lowest hourly price", "price_shape", "EUR/MWh", "minimum hourly price of the day", P, 23,
           "shallower trough"),
    Metric("price_max", "Highest hourly price", "price_shape", "EUR/MWh", "maximum hourly price of the day", P, 23,
           "higher scarcity peak"),
    Metric("capture_solar", "Solar capture price", "capture", "EUR/MWh",
           "sum(solar generation x price) / sum(solar generation) over the hours with both", ("da_price", "gen_actual"), 20,
           "solar earned more", tech="sol"),
    Metric("cr_solar", "Solar capture rate", "capture", "%", "solar capture price / baseload (|baseload| >= 5 only)",
           ("da_price", "gen_actual"), 20, "solar earned closer to or above baseload", scale=100, tech="sol"),
    Metric("capture_wind_onshore", "Onshore wind capture price", "capture", "EUR/MWh", "as solar, onshore wind (B19)",
           ("da_price", "gen_actual"), 20, "wind earned more", tech="won"),
    Metric("cr_wind_onshore", "Onshore wind capture rate", "capture", "%", "onshore wind capture price / baseload",
           ("da_price", "gen_actual"), 20, "wind earned closer to or above baseload", scale=100, tech="won"),
    Metric("capture_wind_offshore", "Offshore wind capture price", "capture", "EUR/MWh", "as solar, offshore wind (B18)",
           ("da_price", "gen_actual"), 20, "wind earned more", tech="woff"),
    Metric("cr_wind_offshore", "Offshore wind capture rate", "capture", "%", "offshore wind capture price / baseload",
           ("da_price", "gen_actual"), 20, "wind earned closer to or above baseload", scale=100, tech="woff"),
    # --- residual load: hourly means of actual load minus solar, onshore and offshore wind generation. Only the
    # technologies the zone reports that day (>= min_hours hours) are subtracted, and only hours that have load and all of them.
    Metric("res_mean", "Residual load, daily mean", "residual_load", "MW", "mean of (load - wind - solar) over the hours used",
           ("load", "gen_actual"), 20, "more load left for dispatchable plant, storage and imports"),
    Metric("res_peak", "Residual load, daily peak", "residual_load", "MW", "highest hourly residual load",
           ("load", "gen_actual"), 20, "tighter evening peak (scarcity pricing risk)"),
    Metric("res_min", "Residual load, daily minimum", "residual_load", "MW",
           "lowest hourly residual load; negative = wind and solar exceeded load (surplus to storage, export or curtailment)",
           ("load", "gen_actual"), 20, "less midday surplus"),
    Metric("res_ramp3", "Residual load, max 3-hour rise", "residual_load", "MW",
           "largest increase of the hourly residual load over 3 consecutive hours (the evening ramp)",
           ("load", "gen_actual"), 20, "steeper ramp the flexible fleet has to deliver"),
    Metric("vre_share", "Wind + solar share of load", "residual_load", "%", "(wind + solar generation) / load, energy over the hours used",
           ("load", "gen_actual"), 20, "more of the load met by wind and solar", scale=100),
    # --- interconnection: physical flows summed over the zone's borders that are in the store (ENTSO-E zone pairs the
    # collector fetches; borders to zones outside it, e.g. GB, MD, TR, are not included), import positive. A day counts only
    # when the zone has data on the same set of borders as on most days of the window (otherwise the sum is not the net position).
    Metric("net_import", "Net import, daily mean", "interconnection", "MW",
           "mean hourly (sum of physical inflows - sum of outflows) over the borders in the store; negative = net export",
           ("flows",), 20, "more imported"),
    Metric("net_import_max", "Net import, daily maximum", "interconnection", "MW", "highest hourly net import",
           ("flows",), 20, "stronger import hour"),
    Metric("net_import_min", "Net import, daily minimum", "interconnection", "MW",
           "lowest hourly net import (most negative = strongest export hour)", ("flows",), 20, "weaker export hour"),
    Metric("import_share", "Net import as share of load", "interconnection", "%", "daily mean net import / daily mean load",
           ("flows", "load"), 20, "zone leans more on imports", scale=100),
]
# --- generation and load: context for the Flags tab ("what else was unusual"). Daily mean output instead of a capacity
# factor: installed capacity is close to constant over the 90-day window, so its percentile equals the CF percentile.
G = ("gen_actual",)
METRICS += [
    Metric("gen_wind_onshore", "Onshore wind output, daily mean", "generation", "MW", "mean hourly onshore wind (B19) generation",
           G, 20, "windier day onshore", tech="won"),
    Metric("gen_wind_offshore", "Offshore wind output, daily mean", "generation", "MW", "mean hourly offshore wind (B18) generation",
           G, 20, "windier day offshore", tech="woff"),
    Metric("gen_solar", "Solar output, daily mean", "generation", "MW", "mean hourly solar (B16) generation", G, 20,
           "sunnier day", tech="sol"),
    Metric("gas_share", "Gas share of generation", "generation", "%",
           "fossil gas (B04) generation / generation of all types, energy over the hours with both", G, 20,
           "gas set more of the supply", scale=100, tech="gas"),
    Metric("load_mean", "Load, daily mean", "generation", "MW", "mean hourly actual load", ("load",), 20, "higher demand"),
]
BY_ID = {m.id: m for m in METRICS}
FAMILIES = ["price_level", "storage_spread", "price_shape", "capture", "residual_load", "interconnection", "generation"]
# site grouping of the families in the Data tab
GROUP_OF = {"price_level": "Prices & daily spreads", "storage_spread": "Prices & daily spreads",
            "price_shape": "Prices & daily spreads", "capture": "Prices & daily spreads",
            "residual_load": "Residual load & interconnection (daily)", "interconnection": "Residual load & interconnection (daily)",
            "generation": "Generation & load (daily)"}


def public_ids() -> list[str]:
    return [m.id for m in METRICS if not m.private]


def describe() -> str:
    """A markdown table of the catalogue (for DEVNOTES / documentation)."""
    rows = ["| id | family | unit | definition | needs |", "|---|---|---|---|---|"]
    for m in METRICS:
        rows.append(f"| {m.id} | {m.family} | {m.unit} | {m.definition} | {', '.join(m.inputs)} >= {m.min_hours} h |")
    return "\n".join(rows)
