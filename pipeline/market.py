"""Power-market data from the Energy-Charts API (Fraunhofer ISE), https://api.energy-charts.info

What it provides to the monitor:
  * day-ahead prices per bidding zone for the feed window (last 24 h + next 24 h once published)
  * actual offshore wind generation per country (last 24 h) to check the model against
  * a monthly history per market area of baseload price, offshore capture price and capture rate,
    built from ACTUAL national offshore generation (no modelling), filled in a few months per run

Licences: each response states its licence. Only data whose licence is CC BY is written to the public
site; zones marked "private and internal use" are skipped (see is_open()).
The API rate-limits bursts, so calls are spaced out and results cached in state/.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import config, entsoe

EC_URL = "https://api.energy-charts.info/v2"
MIN_GAP_S = 3.0  # seconds between calls (the API answers bursts with HTTP 429)
HISTORY_UNITS_PER_RUN = 3  # (market area, month) pairs to backfill per run
HISTORY_MONTHS = 24

# Bidding zone of each country's offshore farms. Denmark is split by longitude (see farm_zone).
ZONE_BY_COUNTRY = {
    "Germany": "DE-LU", "Netherlands": "NL", "Belgium": "BE", "France": "FR", "Sweden": "SE4",
    "Ireland": "IE(SEM)", "Portugal": "PT", "Spain": "ES", "Finland": "FI", "Norway": None,
    "United Kingdom": None,
}
COUNTRY_CODE = {
    "Germany": "de", "Netherlands": "nl", "Belgium": "be", "Denmark": "dk", "France": "fr",
    "Sweden": "se", "Ireland": "ie", "Portugal": "pt", "Spain": "es", "Finland": "fi",
    "United Kingdom": "uk",
}
# Countries on the System tab (country code -> bidding zones shown for it)
SYSTEM_COUNTRIES = {
    "de": ["DE-LU"], "fr": ["FR"], "nl": ["NL"], "be": ["BE"], "dk": ["DK1", "DK2"], "no": ["NO2"],
    "se": ["SE3", "SE4"], "pl": ["PL"], "at": ["AT"], "ch": ["CH"],
}
# Market areas for the monthly history (country code -> zones it trades in)
HISTORY_AREAS = {"de": ["DE-LU"], "nl": ["NL"], "be": ["BE"], "dk": ["DK1", "DK2"], "fr": ["FR"]}


# every current physical bidding zone with a day-ahead price in Energy-Charts (price comparison heatmap);
# historic (DE-AT-LU) and virtual zones (NO2NSL, Italian poles like IT-Brindisi, IT-SACOAC) are left out
ALL_PRICE_ZONES = ["AT", "BE", "BG", "CH", "CZ", "DE-LU", "DK1", "DK2", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
                   "IE(SEM)", "IT-North", "IT-Centre-North", "IT-Centre-South", "IT-South", "IT-Calabria", "IT-Sicily",
                   "IT-Sardinia", "LT", "LV", "ME", "NL", "NO1", "NO2", "NO3", "NO4", "NO5", "PL", "PT", "RO", "RS",
                   "SE1", "SE2", "SE3", "SE4", "SI", "SK", "UA-IPS"]


def farm_zone(f: dict) -> str | None:
    if f["c"] == "Denmark":
        # East of the Great Belt is DK2; Anholt lands in Jutland (DK1). Sprogø is assumed DK2.
        return "DK2" if f["lon"] >= 10.9 and f["n"] != "Anholt" else "DK1"
    return ZONE_BY_COUNTRY.get(f["c"])


def is_open(licence: str | None) -> bool:
    return bool(licence) and "CC BY" in licence.upper().replace("CC-BY", "CC BY")


# ---------------------------------------------------------------- HTTP
class Client:
    def __init__(self):
        import requests

        self.s = requests.Session()
        self.s.headers["User-Agent"] = "offshore-wake-monitor (personal, non-commercial)"
        self.last = 0.0
        self.calls = 0
        self.errors: list[str] = []

    def get(self, endpoint: str, **params) -> dict | None:
        for attempt in range(2):
            wait = MIN_GAP_S - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.calls += 1
            try:
                r = self.s.get(f"{EC_URL}/{endpoint}", params=params, timeout=90)
            except Exception as e:  # dropped connection etc.: wait and retry once
                if attempt == 0:
                    time.sleep(30)
                    continue
                self.errors.append(f"{endpoint} {params}: {e}")
                return None
            if r.status_code in (429, 502, 503, 504) and attempt == 0:
                time.sleep(30)
                continue
            if r.status_code != 200:
                self.errors.append(f"{endpoint} {params}: HTTP {r.status_code} {r.text[:120]}")
                return None
            return r.json()
        return None


def hourly(resp: dict, sid: str) -> dict[int, float]:
    """Average a series to UTC hours. Returns {unix hour start: value}."""
    acc = defaultdict(list)
    for row in resp.get("data", []):
        v = row["values"].get(sid)
        if v is None:
            continue
        t = datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc)
        acc[int(t.replace(minute=0, second=0, microsecond=0).timestamp())].append(float(v))
    return {h: sum(v) / len(v) for h, v in acc.items()}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _load(name: str) -> dict:
    p = config.STATE_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


def _save(name: str, d: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / name).write_text(json.dumps(d, separators=(",", ":")))


# ---------------------------------------------------------------- recent window (feed)
def recent(cl: Client, zones: set[str], countries: set[str], hours: list[int]) -> dict:
    """Prices for `hours` (past + future) per zone; actual offshore MW, generation mix and load per country,
    and cross-border physical flows for SYSTEM_COUNTRIES (past 24 h)."""
    cache = _load("market_recent.json")
    pc = cache.setdefault("prices", {})
    lic = cache.setdefault("licence", {})
    now_h = hours[23]
    start, end = hours[0], hours[-1] + 3600
    restricted_day = cache.setdefault("restricted_day", {})
    for z in sorted(zones):
        # zones whose licence is private-use are never published: re-check them once a day only
        if restricted_day.get(z) == _utc_today().isoformat():
            continue
        have = pc.setdefault(z, {})
        missing_past = any(str(h) not in have for h in hours[:24])
        missing_future = any(str(h) not in have for h in hours[24:])
        # tomorrow's auction is published around 12-13 UTC; don't poll for it before then
        tomorrow_expected = datetime.now(timezone.utc).hour >= 11
        if not (missing_past or (missing_future and tomorrow_expected)) and cache.get("t", {}).get(z, 0) > time.time() - 6 * 3600:
            continue
        r = cl.get("price", bzn=z, start=_iso(start), end=_iso(end))
        if not r:
            continue
        lic[f"price:{z}"] = r.get("license") or ""
        if not is_open(lic[f"price:{z}"]):
            restricted_day[z] = _utc_today().isoformat()
        for h, v in hourly(r, "day_ahead_price").items():
            have[str(h)] = round(v, 2)
        cache.setdefault("t", {})[z] = time.time()
    actual, system = {}, {}
    no_off = cache.setdefault("no_offshore", {})
    past = hours[:24]
    for c in sorted(set(countries) | set(SYSTEM_COUNTRIES)):
        if c not in SYSTEM_COUNTRIES and no_off.get(c) == _utc_today().isoformat():
            continue
        r = cl.get("public_power", country=c, start=_iso(hours[0]), end=_iso(now_h + 3600))
        if not r:
            continue
        lic[f"power:{c}"] = r.get("license") or ""
        series = r.get("series", [])
        ids = {sd["id"] for sd in series}
        if "wind_offshore" in ids:
            hv = hourly(r, "wind_offshore")
            actual[c] = [None if h not in hv else round(hv[h], 1) for h in past]
        elif c not in SYSTEM_COUNTRIES:
            no_off[c] = _utc_today().isoformat()
        if c in SYSTEM_COUNTRIES:
            mw = [sd for sd in series if (sd.get("unit") or r.get("unit") or "MW") == "MW"]
            out = {}
            for sd in mw:
                hv = hourly(r, sd["id"])
                vals = [None if h not in hv else round(hv[h], 1) for h in past]
                if any(v is not None for v in vals):
                    out[sd["id"]] = vals
            system[c] = {"series": out, "names": {sd["id"]: sd["name"] for sd in mw if sd["id"] in out}}
    for c in sorted(SYSTEM_COUNTRIES):
        r = cl.get("cbpf", country=c, start=_iso(hours[0]), end=_iso(now_h + 3600))
        if not r or c not in system:
            continue
        lic[f"flows:{c}"] = r.get("license") or ""
        scale = 1000.0 if (r.get("unit") or "").upper() == "GW" else 1.0
        fl = {}
        for sd in r.get("series", []):
            hv = hourly(r, sd["id"])
            vals = [None if h not in hv else round(hv[h] * scale, 1) for h in past]
            if any(v is not None for v in vals):
                fl[sd["id"]] = vals
        system[c]["flows"] = fl  # MW, positive = import
        system[c]["flow_names"] = {sd["id"]: sd["name"] for sd in r.get("series", []) if sd["id"] in fl}
    # keep three days of prices
    cut = hours[0] - 24 * 3600
    for z in pc:
        pc[z] = {k: v for k, v in pc[z].items() if int(k) >= cut}
    _save("market_recent.json", cache)
    prices = {z: [pc.get(z, {}).get(str(h)) for h in hours] for z in zones}
    return {"prices": prices, "actual": actual, "system": system, "licence": lic}


# ---------------------------------------------------------------- monthly history (actual data)
def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _months(n: int) -> list[str]:
    d = _utc_today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return out  # newest first


def _month_range(m: str) -> tuple[str, str]:
    y, mo = map(int, m.split("-"))
    first = date(y, mo, 1)
    last = (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1))
    return first.isoformat(), min(last, _utc_today()).isoformat()


def history(cl: Client, zone_weights: dict[str, dict[str, float]]) -> dict:
    """Fill a few missing (area, month) cells per run. The current and previous month are refreshed daily."""
    st = _load("market_history.json")
    cells = st.setdefault("cells", {})
    lic = st.setdefault("licence", {})
    months = _months(HISTORY_MONTHS)
    today = _utc_today().isoformat()
    todo = []
    for m in months:
        for c in HISTORY_AREAS:
            key = f"{c}|{m}"
            cell = cells.get(key)
            fresh_needed = m in months[:2] and (not cell or cell.get("day") != today)
            if cell is None or fresh_needed:
                todo.append((c, m))
    for c, m in todo[:HISTORY_UNITS_PER_RUN]:
        a, b = _month_range(m)
        r = cl.get("public_power", country=c, start=a, end=b)
        if not r:
            continue
        lic[f"power:{c}"] = r.get("license") or ""
        if "wind_offshore" not in {s["id"] for s in r.get("series", [])}:
            cells[f"{c}|{m}"] = {"day": today, "none": True}
            continue
        gen = hourly(r, "wind_offshore")
        zp = {}
        for z in HISTORY_AREAS[c]:
            rp = cl.get("price", bzn=z, start=a, end=b)
            if rp:
                lic[f"price:{z}"] = rp.get("license") or ""
                zp[z] = hourly(rp, "day_ahead_price")
        if len(zp) != len(HISTORY_AREAS[c]):
            continue
        w = zone_weights.get(c) or {z: 1 / len(zp) for z in zp}
        hrs = sorted(set(gen) & set.intersection(*(set(v) for v in zp.values())))
        if not hrs:  # nothing yet (e.g. a month that has just started): mark and move on
            cells[f"{c}|{m}"] = {"day": today, "empty": True}
            continue
        price = {h: sum(w.get(z, 0) * zp[z][h] for z in zp) / sum(w.get(z, 0) for z in zp) for h in hrs}
        g = [max(0.0, gen[h]) for h in hrs]
        p = [price[h] for h in hrs]
        e = sum(g)
        cells[f"{c}|{m}"] = {
            "day": today, "hours": len(hrs), "baseload": round(sum(p) / len(p), 2),
            "capture": round(sum(gi * pi for gi, pi in zip(g, p)) / e, 2) if e > 0 else None,
            "gwh": round(e / 1000, 1), "neg_hours": sum(1 for x in p if x < 0),
            "neg_share": round(sum(gi for gi, pi in zip(g, p) if pi < 0) / e, 4) if e > 0 else None,
        }
    _save("market_history.json", st)
    return st


def history_public(st: dict) -> dict:
    """Monthly series per area, only where every price zone involved is openly licensed."""
    lic = st.get("licence", {})
    out = {}
    for c, zones in HISTORY_AREAS.items():
        if not all(is_open(lic.get(f"price:{z}")) for z in zones):
            continue
        rows = []
        for key, cell in st.get("cells", {}).items():
            cc, m = key.split("|")
            if cc == c and cell.get("capture") is not None:
                rows.append({"m": m, **{k: cell[k] for k in ("baseload", "capture", "gwh", "neg_hours", "neg_share", "hours")}})
        if rows:
            rows.sort(key=lambda r: r["m"])
            out[c] = {"zones": zones, "months": rows}
    return out


def zone_weights(farms: list[dict]) -> dict[str, dict[str, float]]:
    """Installed offshore MW per zone within each history country (used to blend DK1/DK2 prices)."""
    w: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in farms:
        cc, z = COUNTRY_CODE.get(f["c"]), farm_zone(f)
        if cc in HISTORY_AREAS and z:
            inst = f.get("inst") or f.get("cap", 0)
            w[cc][z] += inst
    return {c: dict(v) for c, v in w.items()}


def build(farms: list[dict], hours_iso: list[str]) -> tuple[dict, dict]:
    """Returns (market block for feed.json, market_history.json content)."""
    cl = Client()
    hours = [int(datetime.fromisoformat(h.replace("Z", ":00+00:00")).timestamp()) for h in hours_iso]
    core = {z for f in farms if (z := farm_zone(f))} | {z for zs in SYSTEM_COUNTRIES.values() for z in zs}
    zones = core | set(ALL_PRICE_ZONES)
    countries = {COUNTRY_CODE[f["c"]] for f in farms if f["c"] in COUNTRY_CODE}
    rec = recent(cl, zones, countries, hours)
    hist = history(cl, zone_weights(farms))
    lic = {**hist.get("licence", {}), **rec["licence"]}
    open_zones = {z for z in zones if is_open(lic.get(f"price:{z}"))}
    market = {
        "source": "Energy-Charts (Fraunhofer ISE), prices: Bundesnetzagentur | SMARD.de",
        "farm_zone": {str(f["id"]): farm_zone(f) for f in farms},
        "prices": {z: v for z, v in rec["prices"].items() if z in open_zones},
        "restricted_zones": sorted(zones - open_zones),
        "core_zones": sorted(core & open_zones),  # zones with farms or in the System tab (line chart)
        "actual_offshore": {c: v for c, v in rec["actual"].items() if is_open(lic.get(f"power:{c}"))},
        "system": {c: {**({k: v for k, v in d.items() if k in ("series", "names")} if is_open(lic.get(f"power:{c}")) else {}),
                       **({k: v for k, v in d.items() if k in ("flows", "flow_names")} if is_open(lic.get(f"flows:{c}")) else {}),
                       "zones": SYSTEM_COUNTRIES[c]}
                   for c, d in rec["system"].items()},
        "licences": {k: v for k, v in sorted(lic.items())},
        "diag": {"calls": cl.calls, "errors": cl.errors[-10:]},
    }
    if entsoe.token():  # ENTSO-E fills the zones and countries Energy-Charts can't publish (CEE / SEE first)
        try:
            ec = entsoe.Client()
            want = [z for z in sorted(set(ALL_PRICE_ZONES) | {"MK", "BA"}) if z not in market["prices"]]
            ep = entsoe.prices(ec, want, hours)
            for z, v in ep.items():
                market["prices"][z] = v
            market["price_source"] = {z: "entsoe" for z in ep}
            market["restricted_zones"] = sorted(set(market["restricted_zones"]) - set(ep))
            es = entsoe.system(ec, hours)
            for c, d in es.items():
                if c not in market["system"] or not market["system"][c].get("series"):
                    market["system"][c] = d
            cee = {z for c in ("cz", "sk", "hu", "ro", "bg", "si", "hr", "rs", "gr", "me", "ee", "lv", "lt") for z in entsoe.COUNTRIES[c][2]}
            market["core_zones"] = sorted(set(market["core_zones"]) | (cee & set(market["prices"])))
            market["source"] += "; ENTSO-E Transparency Platform"
            ufx = entsoe.fx_table().get("UAH", {})
            if ufx.get("rate"):
                market["fx"] = {"UAH": {"rate": ufx["rate"], "date": ufx.get("date"), "source": ufx.get("source")}}
            market["diag"]["entsoe"] = {"calls": ec.calls, "errors": ec.errors[-15:], "prices": sorted(ep), "system": sorted(es)}
            print(f"entsoe: {ec.calls} calls, {len(ec.errors)} errors, prices {len(ep)} zones, system {sorted(es)}")
        except Exception as ex:  # never block the feed
            market.setdefault("diag", {})["entsoe"] = {"error": repr(ex)[:300]}
            print(f"entsoe: failed {ex!r}")
    try:  # Great Britain and Ireland: open sources without keys (Elexon BMRS, EirGrid); never blocks the feed
        from . import gbie_live
        gf = gbie_live.fetch(hours)
        gl = gbie_live.system(hours, market["system"].get("ie"), gf)
        for c, d in gl.items():
            market["system"][c] = d
        market["source"] += "; Great Britain: Contains BMRS data (c) Elexon Limited copyright and database right " + str(datetime.now(timezone.utc).year) + "; Ireland load: Supported by EirGrid Group Data"
        market.setdefault("diag", {})["gbie"] = {"system": sorted(gl)}
        if not entsoe.gbp_per_eur():  # data/fx.json has no GBP rate yet (capture.yml refreshes it): fetch it for this run
            entsoe.refresh_fx(print)
        gp = gbie_live.prices(gf, hours)
        if gp:  # GB has no day-ahead auction series in open data: the Elexon Market Index (APX trades) stands in, published after delivery
            market["prices"]["GB"] = gp[0]
            market.setdefault("price_source", {})["GB"] = "elexon_mid"
            market["core_zones"] = sorted(set(market["core_zones"]) | {"GB"})
            market["restricted_zones"] = sorted(set(market["restricted_zones"]) - {"GB"})
            market.setdefault("fx", {})["GBP"] = {"rate": gp[1], "date": entsoe.fx_table().get("GBP", {}).get("date"), "source": "ECB reference rate"}
            market["source"] += "; GB price: Market Index Data (APX / EPEX SPOT trades) via Elexon BMRS"
        market["diag"]["gbie"]["price"] = bool(gp)
        print(f"gbie: system {sorted(gl)}, price {'yes' if gp else 'no'}")
    except Exception as ex:
        market.setdefault("diag", {})["gbie"] = {"error": repr(ex)[:300]}
        print(f"gbie: failed {ex!r}")
    hist_pub = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "Capture price = generation-weighted day-ahead price using ACTUAL national offshore wind "
                        "output (Energy-Charts). DK blends DK1/DK2 prices by installed offshore MW per zone.",
                "areas": history_public(hist)}
    print(f"market: {cl.calls} calls, {len(cl.errors)} errors, open zones {sorted(open_zones)}, "
          f"restricted {market['restricted_zones']}, history areas {sorted(hist_pub['areas'])}")
    return market, hist_pub
