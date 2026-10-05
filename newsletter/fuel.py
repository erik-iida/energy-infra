"""Fuel inputs for spark spreads. PRIVATE INPUTS: the gas price comes from yfinance (Yahoo's terms: personal use, no
republishing) and is fetched at run time, never written to the repo, the store release, facts.json or the brief -
only derived spreads leave this module. The repo is public: keep it that way.

  gas     TTF front-month futures (Yahoo `TTF=F`, EUR/MWh, ICE Endex), last settlement on or before the delivery day.
  carbon  EU ETS has no clean free ticker. Optional manual file newsletter/eua_manual.csv (date,eua_eur_t; gitignored,
          one row per month or day, last value on or before the day is used). Without it spreads are FUEL-ONLY
          (gas/eta, no carbon) and the brief says so.
Reference plant: CCGT, 55 % efficiency, 0.202 tCO2 per MWh of gas (thermal). Same SRMC for every zone: zones with
a local gas premium or oil-indexed supply will differ (see DEVNOTES).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ETA = 0.55
EF_GAS = 0.202
EUA_FILE = Path(__file__).resolve().parent / "eua_manual.csv"
COAL_FILE = Path(__file__).resolve().parent / "coal_manual.csv"   # date,api2_eur_t (hand-entered, gitignored; no free API2 source)
OIL_FILE = Path(__file__).resolve().parent / "oil_manual.csv"     # date,brent_eur_bbl (hand-entered, gitignored)

# Per-technology short-run marginal cost for the merit curve (first version, 5 Oct 2026; Erik reviews the parameters).
# eta = electrical efficiency, ef = tCO2 per MWh of fuel (thermal), fuel = which price series feeds it (None = fixed),
# fixed = EUR per MWh_el when no fuel series applies. Order = the canonical merit order used for ties on the page.
# Hydro reservoirs and pumped storage bid opportunity cost, not an SRMC: srmc None -> drawn at the clearing price.
TECH = {
    "vre":      dict(label="Wind, solar, run-of-river", eta=None, ef=0.0, fuel=None, fixed=0.0),
    "biomass":  dict(label="Biomass and waste (must-run)", eta=None, ef=0.0, fuel=None, fixed=0.0),
    "nuclear":  dict(label="Nuclear", eta=None, ef=0.0, fuel=None, fixed=10.0),
    "lignite":  dict(label="Lignite", eta=0.40, ef=0.40, fuel="lignite", fixed=None, fuel_th=4.0),   # mine-mouth fuel ~4 EUR/MWh_th
    "coal":     dict(label="Hard coal", eta=0.42, ef=0.34, fuel="coal", fixed=None),                # API2 EUR/t, 6.98 MWh_th per t
    "gas":      dict(label="Gas (CCGT)", eta=ETA, ef=EF_GAS, fuel="gas", fixed=None),
    "gas_peak": dict(label="Gas (OCGT peaker)", eta=0.38, ef=EF_GAS, fuel="gas", fixed=None),
    "oil":      dict(label="Oil", eta=0.38, ef=0.267, fuel="oil", fixed=None),                      # Brent EUR/bbl, 1.7 MWh_th per bbl
    "hydro":    dict(label="Hydro reservoir, pumped storage", eta=None, ef=0.0, fuel="opportunity", fixed=None),
}
COAL_MWH_PER_T = 6.98
OIL_MWH_PER_BBL = 1.70


def load_ttf() -> pd.Series:
    """Daily TTF front-month close, EUR/MWh, index = naive dates."""
    import yfinance as yf
    d = yf.Ticker("TTF=F").history(period="max", interval="1d", auto_adjust=False)
    c = d["Close"].dropna()
    if c.empty:
        raise RuntimeError("yfinance returned no TTF rows")
    c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()
    return c[~c.index.duplicated(keep="last")].sort_index()


def load_eua(path: Path = EUA_FILE) -> pd.Series | None:
    if not path.exists():
        return None
    d = pd.read_csv(path, parse_dates=["date"])
    return d.set_index("date")["eua_eur_t"].sort_index() if len(d) else None


def load_manual(path: Path, col: str) -> pd.Series | None:
    if not path.exists():
        return None
    d = pd.read_csv(path, parse_dates=["date"])
    return d.set_index("date")[col].sort_index() if len(d) else None


def _on(day: pd.Timestamp, s: pd.Series | None):
    """Last value on or before `day`, else None."""
    if s is None or s.empty:
        return None
    x = s[s.index <= day]
    return float(x.iloc[-1]) if len(x) else None


def srmc_table(day: pd.Timestamp, ttf: pd.Series | None, eua: pd.Series | None = None, coal: pd.Series | None = None,
               oil: pd.Series | None = None) -> dict:
    """{tech: {srmc, fuel_part, carbon_part, complete}} in EUR/MWh_el for one delivery day (TECH above). A technology whose
    fuel series is missing gets the carbon part only and complete=False (the page draws it hatched). Opportunity-cost
    technologies have srmc None. The fuel prices themselves are NOT in the result (private inputs)."""
    e = _on(day, eua)
    px = {"gas": _on(day, ttf), "coal": (lambda v: v / COAL_MWH_PER_T if v is not None else None)(_on(day, coal)),
          "oil": (lambda v: v / OIL_MWH_PER_BBL if v is not None else None)(_on(day, oil))}
    out = {}
    for k, t in TECH.items():
        if t["fuel"] == "opportunity":
            out[k] = {"srmc": None, "fuel_part": None, "carbon_part": None, "complete": True}
            continue
        if t["fuel"] is None:
            out[k] = {"srmc": round(t["fixed"], 1), "fuel_part": round(t["fixed"], 1), "carbon_part": 0.0, "complete": True}
            continue
        th = t.get("fuel_th") if t["fuel"] == "lignite" else px.get(t["fuel"])
        carbon = round(t["ef"] / t["eta"] * e, 1) if e is not None else 0.0
        fuel = round(th / t["eta"], 1) if th is not None else None
        out[k] = {"srmc": round((fuel or 0.0) + carbon, 1), "fuel_part": fuel, "carbon_part": carbon, "complete": fuel is not None}
    return out


def srmc_by_day(days: pd.DatetimeIndex, ttf: pd.Series, eua: pd.Series | None = None) -> tuple[pd.Series, bool]:
    """Short-run marginal cost of the reference CCGT per delivery day (EUR/MWh_el); bool = carbon included."""
    g = ttf.reindex(ttf.index.union(days)).ffill().reindex(days)
    s = g / ETA
    carbon = eua is not None and len(eua) > 0
    if carbon:
        e = eua.reindex(eua.index.union(days)).ffill().reindex(days)
        s = s + EF_GAS / ETA * e
    return s.dropna(), carbon
