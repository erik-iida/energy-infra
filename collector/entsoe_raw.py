"""ENTSO-E Transparency Platform fetchers at native resolution (15/30/60 min), for the data store.

Unlike pipeline/entsoe.py (hourly means for the page), nothing is averaged or converted here: each row is one
published point. Prices stay in the published currency (UA-IPS: UAH); convert downstream with data/fx.json.

Datasets (one request per zone or border direction and window):
  da_price      A44                 day-ahead price                         zone, ts, res_min, seq, price, currency
  gen_actual    A75 / A16           actual generation per production type    zone, ts, res_min, psr, dir, mw
  gen_forecast  A69 / A01           day-ahead wind and solar forecast       zone, ts, res_min, psr, mw
  load          A65 / A16 and A01   actual load and day-ahead load forecast  zone, ts, res_min, kind, mw
  flows         A11                 cross-border physical flow              from_zone, to_zone, ts, res_min, mw
Every row also has `fetched` (UTC). psr is the ENTSO-E code (B01..B25); names in pipeline/entsoe.PSR.
"""
from __future__ import annotations

import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd

from common.entsoe import URL, ZONE_EIC, RateLimiter, token

# Bidding-zone borders for physical flows. Generated from entsoe-py's NEIGHBOURS (MIT) mapped to our zone codes,
# plus the borders it lacks (GR-IT South, ME-IT Centre-South, Ukraine). Each border is fetched in both directions.
BORDERS = [
    ("AL", "GR"), ("AL", "ME"), ("AL", "RS"), ("AT", "CH"), ("AT", "CZ"), ("AT", "DE-LU"), ("AT", "HU"), ("AT", "IT-North"),
    ("AT", "SI"), ("BA", "HR"), ("BA", "ME"), ("BA", "RS"), ("BE", "DE-LU"), ("BE", "FR"), ("BE", "NL"), ("BG", "GR"),
    ("BG", "MK"), ("BG", "RO"), ("BG", "RS"), ("CH", "DE-LU"), ("CH", "FR"), ("CH", "IT-North"), ("CZ", "DE-LU"),
    ("CZ", "PL"), ("CZ", "SK"), ("DE-LU", "DK1"), ("DE-LU", "DK2"), ("DE-LU", "FR"), ("DE-LU", "NL"), ("DE-LU", "NO2"),
    ("DE-LU", "PL"), ("DE-LU", "SE4"), ("DK1", "DK2"), ("DK1", "NL"), ("DK1", "NO2"), ("DK1", "SE3"), ("DK2", "SE4"),
    ("EE", "FI"), ("EE", "LV"), ("ES", "FR"), ("ES", "PT"), ("FI", "NO4"), ("FI", "SE1"), ("FI", "SE3"),
    ("FR", "IT-North"), ("GR", "MK"), ("HR", "HU"), ("HR", "RS"), ("HR", "SI"), ("HU", "RO"), ("HU", "RS"), ("HU", "SI"),
    ("HU", "SK"), ("IT-Calabria", "IT-Sicily"), ("IT-Calabria", "IT-South"), ("IT-Centre-North", "IT-Centre-South"),
    ("IT-Centre-North", "IT-North"), ("IT-Centre-North", "IT-Sardinia"), ("IT-Centre-South", "IT-Sardinia"),
    ("IT-Centre-South", "IT-South"), ("IT-North", "SI"), ("LT", "LV"), ("LT", "PL"), ("LT", "SE4"), ("ME", "RS"),
    ("MK", "RS"), ("NL", "NO2"), ("NO1", "NO2"), ("NO1", "NO3"), ("NO1", "NO5"), ("NO1", "SE3"), ("NO2", "NO5"),
    ("NO3", "NO4"), ("NO3", "NO5"), ("NO3", "SE2"), ("NO4", "SE1"), ("NO4", "SE2"), ("PL", "SE4"), ("PL", "SK"),
    ("RO", "RS"), ("SE1", "SE2"), ("SE2", "SE3"), ("SE3", "SE4"),
    ("GR", "IT-South"), ("IT-Centre-South", "ME"), ("HU", "UA-IPS"), ("PL", "UA-IPS"), ("RO", "UA-IPS"), ("SK", "UA-IPS"),
]
NO_PRICE = {"AL"}  # no day-ahead market data published

# A44 classificationSequence position: only position 1 (or untagged) is the auction result. DE-LU also carries a
# position-2 series that differs from the auction by ~10 EUR/MWh on average, covers days whose auction hasn't run and
# is not what the site shows (Oct 3 2026 probe, DEVNOTES "Data store"). Dropped rows are counted per zone and
# reported in collector_log.json (`seq_dropped`) so a change in ENTSO-E's tagging doesn't go unnoticed.
PRICE_SEQ_KEEP = 1
SEQ_DROPPED: dict[str, int] = {}
_SEQ_LOCK = threading.Lock()


LIMIT = RateLimiter(float(os.environ.get("COLLECT_PER_MIN", "150")))  # + hourly feed 240/min < 400/min (pipeline/entsoe.py)


class Client:
    def __init__(self):
        import requests
        self.s = requests.Session()
        self.calls = 0
        self.errors: list[str] = []

    def get(self, **params) -> ET.Element | None:
        tag = f"{params.get('documentType')} {params.get('in_Domain') or params.get('outBiddingZone_Domain') or ''}"
        for attempt in range(4):
            LIMIT.wait()
            self.calls += 1
            try:
                r = self.s.get(URL, params={**params, "securityToken": token()}, timeout=120)
            except Exception as ex:
                msg = repr(ex).replace(token(), "***") if token() else repr(ex)
                if attempt == 3:
                    self.errors.append(f"{tag}: {msg}"[:200])
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                if b"Acknowledgement_MarketDocument" in r.content[:400]:
                    txt = re.sub(r"<[^>]+>", " ", r.text)
                    if "No matching data" not in txt:
                        self.errors.append(f"{tag}: {' '.join(txt.split())[:160]}")
                    return None
                try:
                    return ET.fromstring(r.content)
                except ET.ParseError as ex:
                    self.errors.append(f"{tag}: parse {ex}")
                    return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(15 * (attempt + 1))
                continue
            txt = re.sub(r"<[^>]+>", " ", r.text.replace(token(), "***") if token() else r.text)
            if "No matching data" not in txt:
                self.errors.append(f"{tag}: HTTP {r.status_code} {' '.join(txt.split())[:160]}")
            return None
        return None


def _res_min(s: str) -> int:
    m = re.fullmatch(r"PT(\d+)M", s or "")
    return int(m.group(1)) if m else {"PT1H": 60, "P1D": 1440, "P7D": 10080}.get(s, 60)


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def points(root: ET.Element | None, value_tag: str):
    """Yield (TimeSeries element, ns, res_min, [(utc datetime, value)]) per Period at native resolution.
    Curve type A03 (variable-sized blocks) omits repeated values: they are forward-filled."""
    if root is None:
        return
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    for ts in root.iter(ns + "TimeSeries"):
        ct = ts.find(ns + "curveType")
        ffill = ct is not None and ct.text == "A03"
        for per in ts.iter(ns + "Period"):
            ti = per.find(ns + "timeInterval")
            start, end = _t(ti.find(ns + "start").text), _t(ti.find(ns + "end").text)
            res = _res_min(per.find(ns + "resolution").text)
            vals = {}
            for p in per.iter(ns + "Point"):
                v = p.find(ns + value_tag)
                if v is not None and v.text not in (None, ""):
                    vals[int(p.find(ns + "position").text)] = float(v.text)
            if not vals:
                continue
            n = int(round((end - start).total_seconds() / 60 / res))
            out, last = [], None
            for pos in range(1, n + 1):
                if pos in vals:
                    last = vals[pos]
                elif not ffill:
                    continue
                if last is None:
                    continue
                out.append((start + pd.Timedelta(minutes=res * (pos - 1)), last))
            yield ts, ns, res, out


def _txt(ts, ns, path: str, default=None):
    el = ts.find(ns + path.replace("/", "/" + ns))
    return el.text if el is not None and el.text else default


def _fmt(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


# ------------------------------------------------------------------ per-zone and per-border fetches
def fetch_zone(zone: str, a: datetime, b: datetime) -> tuple[dict[str, list[dict]], int, list[str]]:
    """All per-zone datasets for one zone and window. Returns ({dataset: rows}, calls, errors)."""
    eic = ZONE_EIC[zone]
    cl = Client()
    w = {"periodStart": _fmt(a), "periodEnd": _fmt(b)}
    rows: dict[str, list[dict]] = {"da_price": [], "gen_actual": [], "gen_forecast": [], "load": []}

    if zone not in NO_PRICE:
        for i, (ts, ns, res, pts) in enumerate(points(cl.get(documentType="A44", in_Domain=eic, out_Domain=eic, **w),
                                                      "price.amount")):
            cur = _txt(ts, ns, "currency_Unit.name", "EUR")
            seq = int(_txt(ts, ns, "classificationSequence_AttributeInstanceComponent.position", 1) or 1)
            if seq != PRICE_SEQ_KEEP:
                with _SEQ_LOCK:
                    SEQ_DROPPED[zone] = SEQ_DROPPED.get(zone, 0) + len(pts)
                continue
            rows["da_price"] += [{"zone": zone, "ts": t, "res_min": res, "seq": seq, "price": v, "currency": cur}
                                 for t, v in pts]

    for ts, ns, res, pts in points(cl.get(documentType="A75", processType="A16", in_Domain=eic, **w), "quantity"):
        d = "gen" if ts.find(ns + "inBiddingZone_Domain.mRID") is not None else "cons"
        psr = _txt(ts, ns, "MktPSRType/psrType", "B20")
        rows["gen_actual"] += [{"zone": zone, "ts": t, "res_min": res, "psr": psr, "dir": d, "mw": v} for t, v in pts]

    for ts, ns, res, pts in points(cl.get(documentType="A69", processType="A01", in_Domain=eic, **w), "quantity"):
        if ts.find(ns + "inBiddingZone_Domain.mRID") is None:
            continue
        psr = _txt(ts, ns, "MktPSRType/psrType", "B20")
        rows["gen_forecast"] += [{"zone": zone, "ts": t, "res_min": res, "psr": psr, "mw": v} for t, v in pts]

    for kind, pt in (("actual", "A16"), ("da_forecast", "A01")):
        for ts, ns, res, pts in points(cl.get(documentType="A65", processType=pt, outBiddingZone_Domain=eic, **w),
                                       "quantity"):
            rows["load"] += [{"zone": zone, "ts": t, "res_min": res, "kind": kind, "mw": v} for t, v in pts]
    return rows, cl.calls, cl.errors


def fetch_flow(frm: str, to: str, a: datetime, b: datetime) -> tuple[list[dict], int, list[str]]:
    cl = Client()
    rows = []
    for ts, ns, res, pts in points(cl.get(documentType="A11", in_Domain=ZONE_EIC[to], out_Domain=ZONE_EIC[frm],
                                          periodStart=_fmt(a), periodEnd=_fmt(b)), "quantity"):
        rows += [{"from_zone": frm, "to_zone": to, "ts": t, "res_min": res, "mw": v} for t, v in pts]
    return rows, cl.calls, cl.errors


def frames(rows: dict[str, list[dict]], fetched: datetime) -> dict[str, pd.DataFrame]:
    """Row lists -> typed DataFrames (UTC timestamps, categorical-friendly strings, float32 values)."""
    out = {}
    for ds, r in rows.items():
        if not r:
            continue
        df = pd.DataFrame(r)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        for c in ("res_min", "seq"):
            if c in df:
                df[c] = df[c].astype("int16")
        for c in ("price", "mw"):
            if c in df:
                df[c] = df[c].astype("float64")
        df["fetched"] = pd.Timestamp(fetched).tz_convert("UTC") if pd.Timestamp(fetched).tzinfo else \
            pd.Timestamp(fetched, tz="UTC")
        out[ds] = df
    return out
