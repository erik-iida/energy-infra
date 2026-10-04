"""ENTSO-E Transparency Platform client, shared by the hourly feed (pipeline/), the data store collectors (collector/)
and the capture / Data-tab scripts: token, rate limiter, Client.get (XML), series parsing, bidding zone -> EIC codes,
production types (PSR). Token in env ENTSOE_TOKEN. Data: ENTSO-E Transparency Platform, https://transparency.entsoe.eu
"""
from __future__ import annotations

import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime

URL = "https://web-api.tp.entsoe.eu/api"


# bidding zone -> EIC code
ZONE_EIC = {
    "AT": "10YAT-APG------L", "BE": "10YBE----------2", "BG": "10YCA-BULGARIA-R", "CH": "10YCH-SWISSGRIDZ",
    "CZ": "10YCZ-CEPS-----N", "DE-LU": "10Y1001A1001A82H", "DK1": "10YDK-1--------W", "DK2": "10YDK-2--------M",
    "EE": "10Y1001A1001A39I", "ES": "10YES-REE------0", "FI": "10YFI-1--------U", "FR": "10YFR-RTE------C",
    "GR": "10YGR-HTSO-----Y", "HR": "10YHR-HEP------M", "HU": "10YHU-MAVIR----U", "IE(SEM)": "10Y1001A1001A59C",
    "IT-North": "10Y1001A1001A73I", "IT-Centre-North": "10Y1001A1001A70O", "IT-Centre-South": "10Y1001A1001A71M",
    "IT-South": "10Y1001A1001A788", "IT-Calabria": "10Y1001C--00096J", "IT-Sicily": "10Y1001A1001A75E",
    "IT-Sardinia": "10Y1001A1001A74G", "LT": "10YLT-1001A0008Q", "LV": "10YLV-1001A00074", "ME": "10YCS-CG-TSO---S",
    "MK": "10YMK-MEPSO----8", "NL": "10YNL----------L", "NO1": "10YNO-1--------2", "NO2": "10YNO-2--------T",
    "NO3": "10YNO-3--------J", "NO4": "10YNO-4--------9", "NO5": "10Y1001A1001A48H", "PL": "10YPL-AREA-----S",
    "PT": "10YPT-REN------W", "RO": "10YRO-TEL------P", "RS": "10YCS-SERBIATSOV", "SE1": "10Y1001A1001A44P",
    "SE2": "10Y1001A1001A45N", "SE3": "10Y1001A1001A46L", "SE4": "10Y1001A1001A47J", "SI": "10YSI-ELES-----O",
    "SK": "10YSK-SEPS-----K", "BA": "10YBA-JPCC-----D", "UA-IPS": "10Y1001C--000182", "AL": "10YAL-KESH-----5",
}


GB_EIC = "10YGB----------A"


# ENTSO-E production types -> Energy-Charts series ids (the page groups these into technologies)
PSR = {"B01": ("biomass", "Biomass"), "B02": ("fossil_brown_coal_lignite", "Lignite"),
       "B03": ("fossil_coal_derived_gas", "Fossil coal-derived gas"), "B04": ("fossil_gas", "Fossil gas"),
       "B05": ("fossil_hard_coal", "Hard coal"), "B06": ("fossil_oil", "Oil"), "B07": ("others", "Oil shale"),
       "B08": ("others", "Peat"), "B09": ("geothermal", "Geothermal"), "B10": ("hydro_pumped_storage", "Pumped storage"),
       "B11": ("hydro_run_of_river", "Run-of-river"), "B12": ("hydro_water_reservoir", "Reservoir"),
       "B13": ("others", "Marine"), "B14": ("nuclear", "Nuclear"), "B15": ("others", "Other renewable"),
       "B16": ("solar", "Solar"), "B17": ("waste", "Waste"), "B18": ("wind_offshore", "Wind offshore"),
       "B19": ("wind_onshore", "Wind onshore"), "B20": ("others", "Other"), "B25": ("others", "Energy storage")}


def token() -> str:
    return os.environ.get("ENTSOE_TOKEN", "")


class RateLimiter:
    """Request spacing shared by all threads of a process. ENTSO-E allows 400 requests per minute per token, and the
    hourly feed and the collector can run at the same time (4 Oct 2026: together they hit the limit and the feed's
    ENTSO-E part took 680 s of 429 retries). Budgets: hourly feed 240/min (ENTSOE_PER_MIN), collector 150/min (its calls are slower anyway, ~140/min)."""

    def __init__(self, per_min: float):
        self.gap = 60.0 / per_min
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        if t > now:
            time.sleep(t - now)


LIMIT = RateLimiter(float(os.environ.get("ENTSOE_PER_MIN", "240")))


class Client:
    # Time budget for one hourly run: after MAX_WALL_S the remaining calls are skipped (countries keep their last data),
    # so a slow or rate-limited API can't hold the feed. Normal runs need 5-40 s.
    MAX_WALL_S = float(os.environ.get("ENTSOE_MAX_WALL_S", "240"))

    def __init__(self):
        import requests
        self.s = requests.Session()
        self.calls, self.errors = 0, []
        self.t0 = time.time()

    def over_budget(self) -> bool:
        if time.time() - self.t0 <= self.MAX_WALL_S:
            return False
        if not any(e.startswith("skipped") for e in self.errors):
            self.errors.append(f"skipped: time budget of {self.MAX_WALL_S:.0f} s used")
        return True

    def get(self, **params) -> ET.Element | None:
        if self.over_budget():
            return None
        for attempt in range(3):
            LIMIT.wait()
            self.calls += 1
            try:
                r = self.s.get(URL, params={**params, "securityToken": token()}, timeout=60)
            except Exception as ex:
                self.errors.append(f"{params.get('documentType')}: {ex!r}"[:200])
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code == 200 and b"Acknowledgement_MarketDocument" not in r.content[:300]:
                try:
                    return ET.fromstring(r.content)
                except ET.ParseError as ex:
                    self.errors.append(f"parse {params.get('documentType')}: {ex}")
                    return None
            if r.status_code in (429, 503):
                time.sleep(10 * (attempt + 1))
                continue
            text = r.text.replace(token(), "***")
            if "No matching data" not in text:
                self.errors.append(f"{params.get('documentType')} {params.get('in_Domain') or params.get('outBiddingZone_Domain')}: "
                                   f"HTTP {r.status_code} {re.sub(r'<[^>]+>', ' ', text)[:160]}")
            return None
        return None


def _res_minutes(s: str) -> int:
    m = re.fullmatch(r"PT(\d+)M", s or "")
    if m:
        return int(m.group(1))
    return {"PT1H": 60, "P1D": 1440}.get(s, 60)


def series(root: ET.Element | None, value_tag: str):
    """Yield (timeseries element, {unix hour: mean value}) for each TimeSeries; A03 curves are forward-filled."""
    if root is None:
        return
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    for ts in root.iter(ns + "TimeSeries"):
        acc: dict[int, list[float]] = {}
        for per in ts.iter(ns + "Period"):
            ti = per.find(ns + "timeInterval")
            start = datetime.fromisoformat(ti.find(ns + "start").text.replace("Z", "+00:00")).timestamp()
            end = datetime.fromisoformat(ti.find(ns + "end").text.replace("Z", "+00:00")).timestamp()
            step = _res_minutes(per.find(ns + "resolution").text) * 60
            pts = {}
            for p in per.iter(ns + "Point"):
                v = p.find(ns + value_tag)
                if v is not None and v.text not in (None, ""):
                    pts[int(p.find(ns + "position").text)] = float(v.text)
            if not pts:
                continue
            n = int(round((end - start) / step))
            last = None
            for pos in range(1, n + 1):
                last = pts.get(pos, last)
                if last is None:
                    continue
                t = start + (pos - 1) * step
                acc.setdefault(int(t // 3600 * 3600), []).append(last)
        yield ts, ns, {h: sum(v) / len(v) for h, v in acc.items()}


def price_seq(ts: ET.Element, ns: str) -> int:
    """A44 classificationSequence position of a TimeSeries (1 when untagged). Position 1 is the auction result; some
    zones (AT, DE-LU, DK2, ES at the Oct 3 2026 probe) carry an extra position-2 series that is not the auction
    price and must not be averaged in (see DEVNOTES "Data store")."""
    el = ts.find(ns + "classificationSequence_AttributeInstanceComponent.position")
    try:
        return int(el.text) if el is not None and el.text else 1
    except ValueError:
        return 1


def currency(ts: ET.Element, ns: str) -> str:
    el = ts.find(ns + "currency_Unit.name")
    return (el.text or "EUR").strip() if el is not None else "EUR"
