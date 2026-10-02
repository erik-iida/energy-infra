"""ENTSO-E Transparency Platform (token in env ENTSOE_TOKEN): day-ahead prices for every bidding zone, and
generation per technology, load and cross-border physical flows per country. Used for the zones and countries
Energy-Charts can't publish, with a focus on Central-Eastern and South-Eastern Europe.

Output matches the Energy-Charts structures in market.py:
  prices[zone] = [EUR/MWh per hour]               (feed window: 24 h past + 24 h ahead)
  system[cc]   = {series: {energy_charts_id: [MW per past hour]}, names, flows: {sum, <nb>: [MW, + = import]},
                  flow_names, zones}
Data: ENTSO-E Transparency Platform, https://transparency.entsoe.eu
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

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
    "mk": ("North Macedonia", "10YMK-MEPSO----8", [], {"rs": "10YCS-SERBIATSOV", "bg": "10YCA-BULGARIA-R", "gr": "10YGR-HTSO-----Y"}),
    "ee": ("Estonia", "10Y1001A1001A39I", ["EE"], {"fi": "10YFI-1--------U", "lv": "10YLV-1001A00074"}),
    "lv": ("Latvia", "10YLV-1001A00074", ["LV"], {"ee": "10Y1001A1001A39I", "lt": "10YLT-1001A0008Q"}),
    "lt": ("Lithuania", "10YLT-1001A0008Q", ["LT"], {"lv": "10YLV-1001A00074", "pl": "10YPL-AREA-----S", "se": "10Y1001A1001A47J"}),
    "fi": ("Finland", "10YFI-1--------U", ["FI"], {"ee": "10Y1001A1001A39I", "se": "10Y1001A1001A44P", "no": "10YNO-4--------9"}),
    "es": ("Spain", "10YES-REE------0", ["ES"], {"pt": "10YPT-REN------W", "fr": "10YFR-RTE------C"}),
    "pt": ("Portugal", "10YPT-REN------W", ["PT"], {"es": "10YES-REE------0"}),
    "it": ("Italy", "10YIT-GRTN-----B", ["IT-North", "IT-Centre-North", "IT-Centre-South", "IT-South", "IT-Sicily", "IT-Sardinia"],
           {"fr": "10YFR-RTE------C", "ch": "10YCH-SWISSGRIDZ", "at": "10YAT-APG------L", "si": "10YSI-ELES-----O", "gr": "10YGR-HTSO-----Y"}),
}

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


class Client:
    def __init__(self):
        import requests
        self.s = requests.Session()
        self.calls, self.errors = 0, []

    def get(self, **params) -> ET.Element | None:
        for attempt in range(3):
            self.calls += 1
            try:
                r = self.s.get(URL, params={**params, "securityToken": token()}, timeout=60)
            except Exception as ex:
                self.errors.append(f"{params.get('documentType')}: {ex!r}"[:200])
                time.sleep(3 * (attempt + 1))
                continue
            time.sleep(0.2)  # the API allows 400 requests per minute
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
            # several TimeSeries may exist (e.g. 60- and 15-minute products): average them per hour
            for h, v in hv.items():
                have[str(h)] = round(v, 2)
        cache.setdefault("pt", {})[z] = time.time()
    cut = hours[0] - 24 * 3600
    for z in pc:
        pc[z] = {k: v for k, v in pc[z].items() if int(k) >= cut}
    _save_cache(cache)
    return {z: [pc.get(z, {}).get(str(h)) for h in hours] for z in zones if any(pc.get(z, {}).get(str(h)) is not None for h in hours)}


def system(cl: Client, hours: list[int]) -> dict[str, dict]:
    """Generation by technology, load and net physical flows per country (past 24 h)."""
    past = hours[:24]
    a, b = _fmt(past[0]), _fmt(past[-1] + 3600)
    cache = _load_cache()
    sc = cache.setdefault("system", {})
    out = {}
    for cc, (name, eic, zones, nbs) in COUNTRIES.items():
        prev = sc.get(cc)
        if prev and prev.get("t", 0) > time.time() - 50 * 60 and prev.get("h0") == past[0]:
            out[cc] = prev["d"]
            continue
        ser: dict[str, dict[int, float]] = {}
        for ts, ns, hv in series(cl.get(documentType="A75", processType="A16", in_Domain=eic, periodStart=a, periodEnd=b), "quantity"):
            if ts.find(ns + "inBiddingZone_Domain.mRID") is None:  # outBiddingZone = consumption (pumping), skip
                continue
            psr = ts.find(f"{ns}MktPSRType/{ns}psrType")
            key = PSR.get(psr.text if psr is not None else "", ("others", "Other"))[0]
            d = ser.setdefault(key, {})
            for h, v in hv.items():
                d[h] = d.get(h, 0) + v
        for ts, ns, hv in series(cl.get(documentType="A65", processType="A16", outBiddingZone_Domain=eic, periodStart=a, periodEnd=b), "quantity"):
            d = ser.setdefault("load", {})
            for h, v in hv.items():
                d[h] = v
        if not ser:
            continue
        res = {k: [None if h not in d else round(d[h], 1) for h in past] for k, d in ser.items()}
        names = {k: next((n for p, (kk, n) in PSR.items() if kk == k), k) for k in res}
        names["load"] = "Load"
        flows, fnames = {}, {}
        do_flows = not (prev and prev.get("tf", 0) > time.time() - 3 * 3600 and prev.get("h0") == past[0])
        if do_flows:
            for nb, neic in nbs.items():
                imp = exp = None
                for _, _, hv in series(cl.get(documentType="A11", in_Domain=eic, out_Domain=neic, periodStart=a, periodEnd=b), "quantity"):
                    imp = hv
                for _, _, hv in series(cl.get(documentType="A11", in_Domain=neic, out_Domain=eic, periodStart=a, periodEnd=b), "quantity"):
                    exp = hv
                if imp is None and exp is None:
                    continue
                flows[nb] = [round((imp or {}).get(h, 0) - (exp or {}).get(h, 0), 1) if (imp and h in imp) or (exp and h in exp) else None
                             for h in past]
                fnames[nb] = nb.upper()
            if flows:
                flows["sum"] = [round(sum(v[i] for v in flows.values() if v[i] is not None), 1)
                                if any(v[i] is not None for v in flows.values()) else None for i in range(len(past))]
                fnames["sum"] = "Net import"
        elif prev:
            flows, fnames = prev["d"].get("flows", {}), prev["d"].get("flow_names", {})
        out[cc] = {"series": res, "names": names, "flows": flows, "flow_names": fnames, "zones": zones, "name": name,
                   "src": "entsoe"}
        sc[cc] = {"t": time.time(), "tf": time.time() if do_flows else (prev or {}).get("tf", 0), "h0": past[0], "d": out[cc]}
    _save_cache(cache)
    return out
