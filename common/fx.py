"""Exchange rates for prices that ENTSO-E publishes in a currency other than EUR (UA-IPS in UAH, GB Market Index in GBP).
data/fx.json keeps a dated history (refreshed once a day by the capture job; everything else only reads it): NBU for UAH,
ECB for GBP. Without a stored rate a series is dropped, never shown in the wrong currency.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import paths
from .entsoe import currency

# ---------------------------------------------------------------- currencies
# Day-ahead prices are mostly in EUR; Ukraine (UA-IPS) publishes in UAH. Non-EUR prices are converted with the
# LATEST official rate (National Bank of Ukraine, UAH per EUR) kept in data/fx.json: refresh_fx() (run by the
# capture workflow, which commits the file) updates it once a day and keeps a dated history; everything else only
# reads it. Without a stored rate the series is dropped, never shown in the wrong currency.
FX_FILE = paths.ROOT / "data" / "fx.json"


NBU_LATEST = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json"


ZONE_CURRENCY = {"UA-IPS": "UAH"}  # for cells stored before the currency was recorded


def fx_table() -> dict:
    try:
        return json.loads(FX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


ECB_HIST = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.csv"


ECB_HIST_ZIP = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"


# ECB Data Portal (SDMX), daily GBP per EUR reference rate; the first source tried (plain CSV, one row per day)
ECB_API = "https://data-api.ecb.europa.eu/service/data/EXR/D.GBP.EUR.SP00.A?format=csvdata&startPeriod={since}"


GBP_FROM = "2023-01-01"  # history kept in data/fx.json (daily conversion of stored GB prices)


def _refresh_uah(fx: dict, log) -> None:
    u = fx.setdefault("UAH", {"source": "National Bank of Ukraine official rate", "unit": "UAH per EUR", "history": {}})
    if u.get("checked") == datetime.now(timezone.utc).date().isoformat():
        return
    import requests
    try:
        r = requests.get(NBU_LATEST, timeout=30, headers={"User-Agent": "energy-infra-monitor"})
        row = r.json()[0]
        rate, d = float(row["rate"]), datetime.strptime(row["exchangedate"], "%d.%m.%Y").date().isoformat()
        u["rate"], u["date"] = rate, d
        u["history"][d] = rate
        u["checked"] = datetime.now(timezone.utc).date().isoformat()
        log(f"fx: UAH/EUR {rate} on {d}")
    except Exception as ex:
        log(f"fx: NBU fetch failed {ex!r}"[:200] + (f"; keeping {u.get('rate')} from {u.get('date')}" if u.get("rate") else ""))


def parse_ecb_gbp(text: str, since: str = GBP_FROM) -> dict[str, float]:
    """{date: GBP per EUR} from either ECB format: the reference-rate history csv (Date, ..., GBP, ...) or the Data
    Portal csvdata (TIME_PERIOD, OBS_VALUE). Header names are stripped (the history csv pads them)."""
    import csv
    import io
    out = {}
    rd = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    head = [h.strip() for h in next(rd, [])]
    if "TIME_PERIOD" in head and "OBS_VALUE" in head:
        di, vi = head.index("TIME_PERIOD"), head.index("OBS_VALUE")
    elif "Date" in head and "GBP" in head:
        di, vi = head.index("Date"), head.index("GBP")
    else:
        return out
    for row in rd:
        if len(row) <= max(di, vi):
            continue
        d, v = row[di].strip(), row[vi].strip()
        if d >= since and v not in ("", "N/A"):
            try:
                out[d] = float(v)
            except ValueError:
                pass
    return out


def fetch_ecb_gbp(log=print, since: str = GBP_FROM) -> dict[str, float]:
    """GBP per EUR history: ECB Data Portal API, then the reference-rate zip, then the csv. Logs what each answered."""
    import io
    import zipfile
    import requests
    h = {"User-Agent": "energy-infra-monitor (hobby project)"}
    for name, url in (("data-api", ECB_API.format(since=since)), ("hist.zip", ECB_HIST_ZIP), ("hist.csv", ECB_HIST)):
        try:
            r = requests.get(url, timeout=60, headers=h)
            r.raise_for_status()
            if r.content[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    text = z.read(z.namelist()[0]).decode("utf-8", "replace")
            else:
                text = r.text
            out = parse_ecb_gbp(text, since)
            if out:
                log(f"fx: ECB {name}: {len(out)} GBP rows")
                return out
            log(f"fx: ECB {name}: no GBP rows (HTTP {r.status_code}, {r.headers.get('content-type', '?')}, starts {text[:60]!r})")
        except Exception as ex:
            log(f"fx: ECB {name} failed {ex!r}"[:200])
    return {}


def _refresh_gbp(fx: dict, log) -> None:
    """GB prices (Elexon, GBP) are shown and used in EUR: ECB euro foreign exchange reference rates, daily history in data/fx.json."""
    g = fx.setdefault("GBP", {"source": "European Central Bank euro foreign exchange reference rate", "unit": "GBP per EUR", "history": {}})
    if g.get("checked") == datetime.now(timezone.utc).date().isoformat():
        return
    try:
        h = fetch_ecb_gbp(log)
        if not h:
            raise ValueError("no GBP rows")
        g["history"].update(h)
        d = max(g["history"])
        g["rate"], g["date"] = g["history"][d], d
        g["checked"] = datetime.now(timezone.utc).date().isoformat()
        log(f"fx: GBP/EUR {g['rate']} on {d} ({len(g['history'])} days)")
    except Exception as ex:
        log(f"fx: ECB fetch failed {ex!r}"[:200] + (f"; keeping {g.get('rate')} from {g.get('date')}" if g.get("rate") else ""))


def refresh_fx(log=print) -> dict:
    """Fetch the latest NBU UAH/EUR rate and the ECB GBP/EUR history once a day and store them in data/fx.json."""
    fx = fx_table()
    _refresh_uah(fx, log)
    _refresh_gbp(fx, log)
    FX_FILE.parent.mkdir(parents=True, exist_ok=True)
    FX_FILE.write_text(json.dumps(fx, indent=1, sort_keys=True), encoding="utf-8")
    return fx


def gbp_per_eur(day: str | None = None) -> float | None:
    """GBP per EUR for an ISO date (the last rate on or before it; ECB publishes working days only), latest when no date."""
    g = fx_table().get("GBP", {})
    h = g.get("history") or {}
    if day and h:
        ds = [d for d in h if d <= day]
        return h[max(ds)] if ds else None
    return g.get("rate")


def eur_rate(cur: str) -> float | None:
    """Latest stored units of `cur` per 1 EUR; 1.0 for EUR, None if no rate is stored."""
    if cur == "EUR":
        return 1.0
    return fx_table().get(cur, {}).get("rate")


def to_eur(ts: ET.Element, ns: str, hv: dict[int, float], errors: list[str] | None = None) -> dict[int, float]:
    """Convert one price TimeSeries (already hourly) to EUR/MWh at the latest stored rate; {} if none."""
    cur = currency(ts, ns)
    r = eur_rate(cur)
    if r is None:
        if errors is not None:
            errors.append(f"no stored {cur}/EUR rate: series dropped")
        return {}
    return hv if r == 1.0 else {h: v / r for h, v in hv.items()}
