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


def srmc_by_day(days: pd.DatetimeIndex, ttf: pd.Series, eua: pd.Series | None = None) -> tuple[pd.Series, bool]:
    """Short-run marginal cost of the reference CCGT per delivery day (EUR/MWh_el); bool = carbon included."""
    g = ttf.reindex(ttf.index.union(days)).ffill().reindex(days)
    s = g / ETA
    carbon = eua is not None and len(eua) > 0
    if carbon:
        e = eua.reindex(eua.index.union(days)).ffill().reindex(days)
        s = s + EF_GAS / ETA * e
    return s.dropna(), carbon
