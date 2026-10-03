"""Probe (Actions): which fuel / carbon series does yfinance return? Private use only: the log holds shapes, date
ranges and a plausibility bucket, NOT the price series (Yahoo's terms don't allow republishing; this repo is public).
Writes data/raw/fuel/probe_yf_log.txt."""
import sys
from pathlib import Path

import pandas as pd

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "fuel" / "probe_yf_log.txt"
CANDIDATES = {"TTF=F": "Dutch TTF gas front month (EUR/MWh expected)", "KRBN": "KraneShares global carbon ETF (proxy)",
              "KEUA": "KraneShares European carbon ETF (proxy)", "EUA=F": "guess: EUA futures",
              "CFI2Z6.NYB": "guess", "NG=F": "Henry Hub gas (control, USD/MMBtu)", "EURUSD=X": "control FX"}
out = []
try:
    import yfinance as yf
    out.append(f"yfinance {yf.__version__}")
except Exception as e:
    out.append(f"yfinance import failed: {e!r}")
    yf = None
for t, note in CANDIDATES.items():
    if yf is None:
        break
    try:
        d = yf.Ticker(t).history(period="max", interval="1d", auto_adjust=False)
    except Exception as e:
        out.append(f"{t} ({note}): error {e!r}"[:300])
        continue
    if d is None or d.empty:
        out.append(f"{t} ({note}): no rows")
        continue
    c = d["Close"].dropna()
    gaps = c.index.to_series().diff().dt.days.dropna()
    out.append(f"{t} ({note}): {len(c)} daily rows {c.index.min():%Y-%m-%d}..{c.index.max():%Y-%m-%d}, "
               f"max gap {int(gaps.max()) if len(gaps) else 0} d, last close has {len(str(int(abs(c.iloc[-1]))))} integer digit(s), "
               f"non-positive closes {(c <= 0).sum()}")
    try:
        info = yf.Ticker(t).fast_info
        out.append(f"   currency {info.get('currency')}, exchange {info.get('exchange')}")
    except Exception as e:
        out.append(f"   fast_info failed: {e!r}"[:200])
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out))
