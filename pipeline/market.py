"""Power-market data for the hourly feed, all from the ENTSO-E Transparency Platform (plus GB / IE open data).

What it provides to the monitor (feed.json "market"):
  * day-ahead prices per bidding zone for the feed window (last 24 h + next 24 h once published)
  * generation by technology, load and cross-border physical flows per country, last 24 h (System tab)
  * actual offshore wind generation per country (last 24 h) to check the model against
Energy-Charts was the source for prices and the western / Nordic countries until 4 Oct 2026; it failed from GitHub's
runners most hours (circuit breaker, ~50 s lost per run) while ENTSO-E answered for all countries, so the feed now
uses one source (pipeline/entsoe.py, cached in state/entsoe_cache.json). GB / IE: pipeline/gbie_live.py.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import entsoe

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


# every current physical bidding zone with a day-ahead price (price comparison heatmap);
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


def build(farms: list[dict], hours_iso: list[str]) -> dict:
    """Returns the market block for feed.json."""
    hours = [int(datetime.fromisoformat(h.replace("Z", ":00+00:00")).timestamp()) for h in hours_iso]
    core = {z for f in farms if (z := farm_zone(f))} | {z for zs in SYSTEM_COUNTRIES.values() for z in zs}
    market = {
        "source": "ENTSO-E Transparency Platform",
        "farm_zone": {str(f["id"]): farm_zone(f) for f in farms},
        "prices": {}, "price_source": {}, "restricted_zones": [], "core_zones": [], "actual_offshore": {}, "system": {},
        "diag": {"seconds": {}},
    }
    t1 = time.time()
    if not entsoe.token():
        print("market: ENTSOE_TOKEN not set; prices and system data skipped")
    else:
        try:
            ec = entsoe.Client()
            ep = entsoe.prices(ec, sorted(set(ALL_PRICE_ZONES) | {"MK", "BA"}), hours)
            market["prices"] = ep
            market["price_source"] = {z: "entsoe" for z in ep}
            market["system"] = entsoe.system(ec, hours)
            cee = {z for c in ("cz", "sk", "hu", "ro", "bg", "si", "hr", "rs", "gr", "me", "ee", "lv", "lt") for z in entsoe.COUNTRIES[c][2]}
            market["core_zones"] = sorted((core | cee) & set(ep))
            ufx = entsoe.fx_table().get("UAH", {})
            if ufx.get("rate"):
                market["fx"] = {"UAH": {"rate": ufx["rate"], "date": ufx.get("date"), "source": ufx.get("source")}}
            market["diag"]["entsoe"] = {"calls": ec.calls, "errors": ec.errors[-15:], "prices": sorted(ep),
                                        "system": sorted(market["system"])}
            print(f"entsoe: {ec.calls} calls, {len(ec.errors)} errors, prices {len(ep)} zones, system {sorted(market['system'])}")
        except Exception as ex:  # never block the feed
            market["diag"]["entsoe"] = {"error": repr(ex)[:300]}
            print(f"entsoe: failed {ex!r}")
    market["diag"]["seconds"]["entsoe"] = round(time.time() - t1, 1)
    t1 = time.time()
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
    market["diag"]["seconds"]["gb_ie"] = round(time.time() - t1, 1)
    # model check: actual national offshore wind output (past 24 h) from the system data
    for name, cc in COUNTRY_CODE.items():
        d = market["system"].get("gb" if cc == "uk" else cc) or {}
        v = (d.get("series") or {}).get("wind_offshore")
        if v and any(x is not None for x in v) and not d.get("lag_h"):
            market["actual_offshore"][cc] = v
    print(f"market: prices {len(market['prices'])} zones, system {len(market['system'])} countries, "
          f"actual offshore {sorted(market['actual_offshore'])}")
    return market
