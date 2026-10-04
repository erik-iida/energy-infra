"""ENTSO-E Transparency Platform (token in env ENTSOE_TOKEN): day-ahead prices for every bidding zone, and
generation per technology, load and cross-border physical flows per country. The only market source of the hourly
feed since 4 Oct 2026 (market.py); series ids keep the Energy-Charts naming the page was built on.

Output:
  prices[zone] = [EUR/MWh per hour]               (feed window: 24 h past + 24 h ahead)
  system[cc]   = {series: {series id (Energy-Charts naming, see PSR): [MW per past hour]}, names, flows: {sum, <nb>: [MW, + = import]},
                  flow_names, zones}
Data: ENTSO-E Transparency Platform, https://transparency.entsoe.eu
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import config

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

# Countries added to the System tab from ENTSO-E: code -> (name, generation/load area EIC, price zones, neighbours)
# neighbours: code -> EIC of the neighbouring area used for physical flows
COUNTRIES = {
    "ie": ("Ireland", "10Y1001A1001A59C", ["IE(SEM)"], {}),  # load and flow to GB are filled by pipeline/gbie_live.py
    "cz": ("Czechia", "10YCZ-CEPS-----N", ["CZ"], {"de": "10Y1001A1001A82H", "pl": "10YPL-AREA-----S", "sk": "10YSK-SEPS-----K", "at": "10YAT-APG------L"}),
    "sk": ("Slovakia", "10YSK-SEPS-----K", ["SK"], {"cz": "10YCZ-CEPS-----N", "pl": "10YPL-AREA-----S", "hu": "10YHU-MAVIR----U", "ua": "10Y1001C--000182"}),
    "hu": ("Hungary", "10YHU-MAVIR----U", ["HU"], {"sk": "10YSK-SEPS-----K", "at": "10YAT-APG------L", "si": "10YSI-ELES-----O", "hr": "10YHR-HEP------M",
                                                    "rs": "10YCS-SERBIATSOV", "ro": "10YRO-TEL------P", "ua": "10Y1001C--000182"}),
    "ro": ("Romania", "10YRO-TEL------P", ["RO"], {"hu": "10YHU-MAVIR----U", "rs": "10YCS-SERBIATSOV", "bg": "10YCA-BULGARIA-R", "ua": "10Y1001C--000182"}),
    "bg": ("Bulgaria", "10YCA-BULGARIA-R", ["BG"], {"ro": "10YRO-TEL------P", "rs": "10YCS-SERBIATSOV", "mk": "10YMK-MEPSO----8", "gr": "10YGR-HTSO-----Y"}),
    "si": ("Slovenia", "10YSI-ELES-----O", ["SI"], {"at": "10YAT-APG------L", "it": "10Y1001A1001A73I", "hr": "10YHR-HEP------M", "hu": "10YHU-MAVIR----U"}),
    "hr": ("Croatia", "10YHR-HEP------M", ["HR"], {"si": "10YSI-ELES-----O", "hu": "10YHU-MAVIR----U", "rs": "10YCS-SERBIATSOV", "ba": "10YBA-JPCC-----D"}),
    "rs": ("Serbia", "10YCS-SERBIATSOV", ["RS"], {"hu": "10YHU-MAVIR----U", "ro": "10YRO-TEL------P", "bg": "10YCA-BULGARIA-R", "mk": "10YMK-MEPSO----8",
                                                   "me": "10YCS-CG-TSO---S", "ba": "10YBA-JPCC-----D", "hr": "10YHR-HEP------M", "al": "10YAL-KESH-----5"}),
    "gr": ("Greece", "10YGR-HTSO-----Y", ["GR"], {"bg": "10YCA-BULGARIA-R", "mk": "10YMK-MEPSO----8", "al": "10YAL-KESH-----5", "it": "10Y1001A1001A788"}),
    "ba": ("Bosnia and Herzegovina", "10YBA-JPCC-----D", [], {"hr": "10YHR-HEP------M", "rs": "10YCS-SERBIATSOV", "me": "10YCS-CG-TSO---S"}),
    "me": ("Montenegro", "10YCS-CG-TSO---S", ["ME"], {"rs": "10YCS-SERBIATSOV", "ba": "10YBA-JPCC-----D", "al": "10YAL-KESH-----5", "it": "10Y1001A1001A71M"}),
    "mk": ("North Macedonia", "10YMK-MEPSO----8", ["MK"], {"rs": "10YCS-SERBIATSOV", "bg": "10YCA-BULGARIA-R", "gr": "10YGR-HTSO-----Y"}),
    "ee": ("Estonia", "10Y1001A1001A39I", ["EE"], {"fi": "10YFI-1--------U", "lv": "10YLV-1001A00074"}),
    "lv": ("Latvia", "10YLV-1001A00074", ["LV"], {"ee": "10Y1001A1001A39I", "lt": "10YLT-1001A0008Q"}),
    "lt": ("Lithuania", "10YLT-1001A0008Q", ["LT"], {"lv": "10YLV-1001A00074", "pl": "10YPL-AREA-----S", "se": "10Y1001A1001A47J"}),
    "fi": ("Finland", "10YFI-1--------U", ["FI"], {"ee": "10Y1001A1001A39I", "se": "10Y1001A1001A44P", "no": "10YNO-4--------9"}),
    "es": ("Spain", "10YES-REE------0", ["ES"], {"pt": "10YPT-REN------W", "fr": "10YFR-RTE------C"}),
    "pt": ("Portugal", "10YPT-REN------W", ["PT"], {"es": "10YES-REE------0"}),
    "it": ("Italy", "10YIT-GRTN-----B", ["IT-North", "IT-Centre-North", "IT-Centre-South", "IT-South", "IT-Sicily", "IT-Sardinia"],
           {"fr": "10YFR-RTE------C", "ch": "10YCH-SWISSGRIDZ", "at": "10YAT-APG------L", "si": "10YSI-ELES-----O", "gr": "10YGR-HTSO-----Y"}),
}

# Western and Nordic countries (moved from Energy-Charts to ENTSO-E on 4 Oct 2026). Generation / load area = one bidding
# zone, or a list of zones that are summed (DK, NO, SE). Neighbours: code -> neighbour EIC, or a list of
# (own zone EIC, neighbour zone EIC) borders whose flows are added up.
_Z = ZONE_EIC
GB_EIC = "10YGB----------A"
COUNTRIES.update({
    "de": ("Germany", _Z["DE-LU"], ["DE-LU"], {"fr": _Z["FR"], "nl": _Z["NL"], "be": _Z["BE"], "pl": _Z["PL"], "cz": _Z["CZ"],
                                              "at": _Z["AT"], "ch": _Z["CH"], "no": _Z["NO2"], "se": _Z["SE4"],
                                              "dk": [(_Z["DE-LU"], _Z["DK1"]), (_Z["DE-LU"], _Z["DK2"])]}),
    "fr": ("France", _Z["FR"], ["FR"], {"de": _Z["DE-LU"], "be": _Z["BE"], "ch": _Z["CH"], "it": _Z["IT-North"], "es": _Z["ES"],
                                       "gb": GB_EIC}),
    "nl": ("Netherlands", _Z["NL"], ["NL"], {"de": _Z["DE-LU"], "be": _Z["BE"], "no": _Z["NO2"], "dk": _Z["DK1"], "gb": GB_EIC}),
    "be": ("Belgium", _Z["BE"], ["BE"], {"fr": _Z["FR"], "nl": _Z["NL"], "de": _Z["DE-LU"], "gb": GB_EIC}),
    "dk": ("Denmark", [_Z["DK1"], _Z["DK2"]], ["DK1", "DK2"],
           {"de": [(_Z["DK1"], _Z["DE-LU"]), (_Z["DK2"], _Z["DE-LU"])], "nl": [(_Z["DK1"], _Z["NL"])], "no": [(_Z["DK1"], _Z["NO2"])],
            "se": [(_Z["DK1"], _Z["SE3"]), (_Z["DK2"], _Z["SE4"])], "gb": [(_Z["DK1"], GB_EIC)]}),
    "no": ("Norway", [_Z["NO1"], _Z["NO2"], _Z["NO3"], _Z["NO4"], _Z["NO5"]], ["NO2"],
           {"se": [(_Z["NO1"], _Z["SE3"]), (_Z["NO3"], _Z["SE2"]), (_Z["NO4"], _Z["SE1"]), (_Z["NO4"], _Z["SE2"])],
            "fi": [(_Z["NO4"], _Z["FI"])], "dk": [(_Z["NO2"], _Z["DK1"])], "de": [(_Z["NO2"], _Z["DE-LU"])],
            "nl": [(_Z["NO2"], _Z["NL"])], "gb": [(_Z["NO2"], GB_EIC)]}),
    "se": ("Sweden", [_Z["SE1"], _Z["SE2"], _Z["SE3"], _Z["SE4"]], ["SE3", "SE4"],
           {"no": [(_Z["SE3"], _Z["NO1"]), (_Z["SE2"], _Z["NO3"]), (_Z["SE1"], _Z["NO4"]), (_Z["SE2"], _Z["NO4"])],
            "fi": [(_Z["SE1"], _Z["FI"]), (_Z["SE3"], _Z["FI"])], "dk": [(_Z["SE3"], _Z["DK1"]), (_Z["SE4"], _Z["DK2"])],
            "de": [(_Z["SE4"], _Z["DE-LU"])], "pl": [(_Z["SE4"], _Z["PL"])], "lt": [(_Z["SE4"], _Z["LT"])]}),
    "pl": ("Poland", _Z["PL"], ["PL"], {"de": _Z["DE-LU"], "cz": _Z["CZ"], "sk": _Z["SK"], "lt": _Z["LT"], "se": _Z["SE4"],
                                       "ua": _Z["UA-IPS"]}),
    "at": ("Austria", _Z["AT"], ["AT"], {"de": _Z["DE-LU"], "cz": _Z["CZ"], "hu": _Z["HU"], "si": _Z["SI"], "it": _Z["IT-North"],
                                        "ch": _Z["CH"]}),
    "ch": ("Switzerland", _Z["CH"], ["CH"], {"de": _Z["DE-LU"], "fr": _Z["FR"], "it": _Z["IT-North"], "at": _Z["AT"]}),
})

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
    ENTSO-E part took 680 s of 429 retries). Budgets: hourly feed 200/min (ENTSOE_PER_MIN), collector 190/min."""

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


LIMIT = RateLimiter(float(os.environ.get("ENTSOE_PER_MIN", "200")))


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


# ---------------------------------------------------------------- currencies
# Day-ahead prices are mostly in EUR; Ukraine (UA-IPS) publishes in UAH. Non-EUR prices are converted with the
# LATEST official rate (National Bank of Ukraine, UAH per EUR) kept in data/fx.json: refresh_fx() (run by the
# capture workflow, which commits the file) updates it once a day and keeps a dated history; everything else only
# reads it. Without a stored rate the series is dropped, never shown in the wrong currency.
FX_FILE = config.ROOT / "data" / "fx.json"
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


def _fmt(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y%m%d%H%M")


def _load_cache() -> dict:
    p = config.STATE_DIR / "entsoe_cache.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_cache(c: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / "entsoe_cache.json").write_text(json.dumps(c, separators=(",", ":")))


def prices(cl: Client, zones: list[str], hours: list[int]) -> dict[str, list]:
    """Day-ahead prices per zone over the feed window; cached per zone, refetched when hours are missing."""
    cache = _load_cache()
    pc = cache.setdefault("prices", {})
    if cache.get("fx") != 2:  # cached before the stored-rate conversion: refetch UA-IPS
        pc.pop("UA-IPS", None)
        cache.get("pt", {}).pop("UA-IPS", None)
        cache["fx"] = 2
    tomorrow_due = datetime.now(timezone.utc).hour >= 11
    for z in zones:
        eic = ZONE_EIC.get(z)
        if not eic:
            continue
        have = pc.setdefault(z, {})
        miss_past = any(str(h) not in have for h in hours[:24])
        miss_fut = any(str(h) not in have for h in hours[24:])
        if not (miss_past or (miss_fut and tomorrow_due)) and cache.get("pt", {}).get(z, 0) > time.time() - 6 * 3600:
            continue
        root = cl.get(documentType="A44", in_Domain=eic, out_Domain=eic, periodStart=_fmt(hours[0]),
                      periodEnd=_fmt(hours[-1] + 3600))
        for ts, ns, hv in series(root, "price.amount"):
            if price_seq(ts, ns) != 1:  # not the auction result (see price_seq)
                continue
            hv = to_eur(ts, ns, hv, cl.errors)
            # several TimeSeries may exist (e.g. 60- and 15-minute products): average them per hour
            for h, v in hv.items():
                have[str(h)] = round(v, 2)
        cache.setdefault("pt", {})[z] = time.time()
    cut = hours[0] - 24 * 3600
    for z in pc:
        pc[z] = {k: v for k, v in pc[z].items() if int(k) >= cut}
    _save_cache(cache)
    return {z: [pc.get(z, {}).get(str(h)) for h in hours] for z in zones if any(pc.get(z, {}).get(str(h)) is not None for h in hours)}


def _borders(eic, nb) -> list[tuple[str, str]]:
    """(own zone, neighbour zone) pairs for one neighbour entry of COUNTRIES."""
    if isinstance(nb, list):
        return nb
    return [(eic if isinstance(eic, str) else eic[0], nb)]


def _country(cl: Client, cc: str, spec: tuple, past0: list[int], a: str, b: str, prev: dict | None) -> tuple[dict | None, dict | None]:
    """Generation by technology, load and net physical flows for one country (past 24 h). Returns (data, cache entry)."""
    name, eic, zones, nbs = spec
    areas = [eic] if isinstance(eic, str) else list(eic)
    past = past0
    ser: dict[str, dict[int, float]] = {}
    reported: list[set[int]] = []  # hours with generation, per area (a multi-zone country is complete only where all report)
    for area in areas:
        hrs: set[int] = set()
        for ts, ns, hv in series(cl.get(documentType="A75", processType="A16", in_Domain=area, periodStart=a, periodEnd=b), "quantity"):
            if ts.find(ns + "inBiddingZone_Domain.mRID") is None:  # outBiddingZone = consumption (pumping), skip
                continue
            psr = ts.find(f"{ns}MktPSRType/{ns}psrType")
            key = PSR.get(psr.text if psr is not None else "", ("others", "Other"))[0]
            d = ser.setdefault(key, {})
            for h, v in hv.items():
                d[h] = d.get(h, 0) + v
                hrs.add(h)
        reported.append(hrs)
        lv: dict[int, float] = {}
        for ts, ns, hv in series(cl.get(documentType="A65", processType="A16", outBiddingZone_Domain=area, periodStart=a, periodEnd=b), "quantity"):
            lv.update(hv)  # several TimeSeries: later ones (revisions) win, as before
        if lv:
            d = ser.setdefault("load", {})
            for h, v in lv.items():
                d[h] = d.get(h, 0) + v
    if not ser:
        return None, None
    if len(areas) > 1:  # drop hours where one of the zones has not reported yet (a partial sum would show a false dip)
        ok = set.intersection(*reported) if all(reported) else set()
        ser = {k: {h: v for h, v in d.items() if h in ok} for k, d in ser.items()}
        ser = {k: d for k, d in ser.items() if d}
        if not ser:
            return None, None
    gen_hours = [h for k, d in ser.items() if k != "load" for h in d]
    lag = 0
    if gen_hours and max(gen_hours) < past0[-1] - 3 * 3600:  # data ends early: show the latest 24 h available
        last = max(gen_hours)
        past = [last - 3600 * (23 - i) for i in range(24)]
        lag = int((past0[-1] - last) // 3600)
    res = {k: [None if h not in d else round(d[h], 1) for h in past] for k, d in ser.items()}
    names = {k: next((n for p, (kk, n) in PSR.items() if kk == k), k) for k in res}
    names["load"] = "Load"
    flows, fnames = {}, {}
    do_flows = not (prev and prev.get("tf", 0) > time.time() - 3 * 3600 and prev.get("h0") == past[0])
    if do_flows:
        for nb, spec_nb in nbs.items():
            imp: dict[int, float] = {}
            exp: dict[int, float] = {}
            got = False
            for own, other in _borders(eic, spec_nb):
                for _, _, hv in series(cl.get(documentType="A11", in_Domain=own, out_Domain=other, periodStart=a, periodEnd=b), "quantity"):
                    got = True
                    for h, v in hv.items():
                        imp[h] = imp.get(h, 0) + v
                for _, _, hv in series(cl.get(documentType="A11", in_Domain=other, out_Domain=own, periodStart=a, periodEnd=b), "quantity"):
                    got = True
                    for h, v in hv.items():
                        exp[h] = exp.get(h, 0) + v
            if not got:
                continue
            flows[nb] = [round(imp.get(h, 0) - exp.get(h, 0), 1) if (h in imp or h in exp) else None for h in past]
            fnames[nb] = nb.upper()
        if flows:
            flows["sum"] = [round(sum(v[i] for v in flows.values() if v[i] is not None), 1)
                            if any(v[i] is not None for v in flows.values()) else None for i in range(len(past))]
            fnames["sum"] = "Net import"
    elif prev:
        flows, fnames = prev["d"].get("flows", {}), prev["d"].get("flow_names", {})
    out = {"series": res, "names": names, "flows": flows, "flow_names": fnames, "zones": zones, "name": name, "src": "entsoe"}
    if lag:
        out["lag_h"] = lag
    entry = {"t": time.time(), "tf": time.time() if do_flows else (prev or {}).get("tf", 0), "h0": past0[0], "d": out}
    return out, entry


def system(cl: Client, hours: list[int], workers: int = 6) -> dict[str, dict]:
    """Generation by technology, load and net physical flows per country (past 24 h), countries fetched in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    past0 = hours[:24]
    a, b = _fmt(past0[0] - 24 * 3600), _fmt(past0[-1] + 3600)  # 48 h window: some TSOs (e.g. Romania) publish late
    cache = _load_cache()
    sc = cache.setdefault("system", {})
    out, todo = {}, []
    for cc, spec in COUNTRIES.items():
        prev = sc.get(cc)
        if prev and prev.get("t", 0) > time.time() - 50 * 60 and prev.get("h0") == past0[0]:
            out[cc] = prev["d"]
        else:
            todo.append((cc, spec, prev))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {cc: ex.submit(_country, cl, cc, spec, past0, a, b, prev) for cc, spec, prev in todo}
        for cc, fu in futs.items():
            try:
                d, entry = fu.result()
            except Exception as e:  # one country must never stop the others
                cl.errors.append(f"system {cc}: {e!r}"[:200])
                continue
            if d is not None:
                out[cc], sc[cc] = d, entry
            elif sc.get(cc):  # not fetched this time (time budget, outage): keep the last data, marked as late
                old = sc[cc]
                shift = max(0, int((past0[0] - old.get("h0", past0[0])) // 3600))
                out[cc] = {**old["d"], **({"lag_h": old["d"].get("lag_h", 0) + shift} if shift else {})}
    _save_cache(cache)
    return out
