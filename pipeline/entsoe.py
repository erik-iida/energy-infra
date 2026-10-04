"""ENTSO-E data for the hourly feed: day-ahead prices for every bidding zone, and generation per technology, load and
cross-border physical flows per country (System tab). The only market source of the feed since 4 Oct 2026 (market.py);
series ids keep the Energy-Charts naming the page was built on. The client, zone codes and FX live in common/.

Output:
  prices[zone] = [EUR/MWh per hour]               (feed window: 24 h past + 24 h ahead)
  system[cc]   = {series: {series id (Energy-Charts naming, see PSR): [MW per past hour]}, names, flows: {sum, <nb>: [MW, + = import]},
                  flow_names, zones}
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from common.entsoe import (  # noqa: F401  (re-exported: pipeline.market and tests use entsoe.<name>)
    GB_EIC, LIMIT, PSR, URL, ZONE_EIC, Client, RateLimiter, currency, price_seq, series, token,
)
from common.fx import (  # noqa: F401
    ZONE_CURRENCY, eur_rate, fetch_ecb_gbp, fx_table, gbp_per_eur, parse_ecb_gbp, refresh_fx, to_eur,
)

from . import config

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
            elif sc.get(cc):  # not fetched this time (time budget, outage): keep the last data, marked as late, for 6 h
                old = sc[cc]
                shift = max(0, int((past0[0] - old.get("h0", past0[0])) // 3600))
                if shift <= 6:
                    out[cc] = {**old["d"], **({"lag_h": old["d"].get("lag_h", 0) + shift} if shift else {})}
    _save_cache(cache)
    return out
