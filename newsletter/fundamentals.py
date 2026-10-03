"""Regional fundamentals from what the zone actually generated (ENTSO-E A75), and the IRENA capacity reference.

Since Oct 3 2026 (newsletter feedback #1) capacity factors no longer use IRENA: its year-end capacity is older than the
fleet. The capacity proxy is the class's highest hourly output in the last PEAK_DAYS days (peak_capacity), so
CF = mean output over the window / that peak ("CF vs 90-day peak", higher than a nameplate CF because the fleet never
runs at 100 % at once). The newsletter reads wind and solar as output share of load instead of installed GW.
IRENA stays only as the installed-GW reference table on the Data tab.

capacity(zone, cls)   latest year-end MW from data/ref/irena_capacity.csv (scripts/ingest_irena.py), summed over the
                      countries behind the bidding zone (DE-LU = DE + LU). Only zones that are a whole country are mapped.
capacity_factors()    energy generated in the window / (capacity x window hours) per zone and class, from raw gen_actual
                      rows. A zone-class needs >= 90 % of the window's hours with data, otherwise it is left out.
fundamentals_table()  one row per zone: solar and wind GW, their 30-day capacity factors, VRE capacity / mean load, and
                      the same window's mean baseload / TB4 / negative hours, so price levels can be read against the
                      zone's installed base.

Caveats printed with the table: IRENA capacity is year-end of its last edition (older than the generation data, so fast
solar growth lifts the capacity factor), ENTSO-E generation may miss small distributed solar (lowers it), and IRENA
splits fossil capacity by fuel only for some countries (fossil_nes = all fossil together).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

REF = Path(__file__).resolve().parent.parent / "data" / "ref"
ISO3 = {"AT": ["AUT"], "BA": ["BIH"], "BE": ["BEL"], "BG": ["BGR"], "CH": ["CHE"], "CZ": ["CZE"],
        "DE-LU": ["DEU", "LUX"], "EE": ["EST"], "ES": ["ESP"], "FI": ["FIN"], "FR": ["FRA"], "GR": ["GRC"],
        "HR": ["HRV"], "HU": ["HUN"], "LT": ["LTU"], "LV": ["LVA"], "ME": ["MNE"], "MK": ["MKD"], "NL": ["NLD"],
        "PL": ["POL"], "PT": ["PRT"], "RO": ["ROU"], "RS": ["SRB"], "SI": ["SVN"], "SK": ["SVK"]}
# every bidding zone in the store -> its country (ISO3), for country-level capacity factors (IE(SEM) also covers Northern
# Ireland and DE-LU also Luxembourg, so those two are only approximate)
ZONE_ISO3 = {"AL": "ALB", "AT": "AUT", "BA": "BIH", "BE": "BEL", "BG": "BGR", "CH": "CHE", "CZ": "CZE", "DE-LU": "DEU",
             "DK1": "DNK", "DK2": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC", "HR": "HRV",
             "HU": "HUN", "GB": "GBR", "IE(SEM)": "IRL", "LT": "LTU", "LV": "LVA", "ME": "MNE", "MK": "MKD", "NL": "NLD", "PL": "POL",
             "PT": "PRT", "RO": "ROU", "RS": "SRB", "SI": "SVN", "SK": "SVK",
             **{f"NO{i}": "NOR" for i in range(1, 6)}, **{f"SE{i}": "SWE" for i in range(1, 5)},
             **{z: "ITA" for z in ("IT-Calabria", "IT-Centre-North", "IT-Centre-South", "IT-North", "IT-Sardinia", "IT-Sicily", "IT-South")}}
# ENTSO-E production types -> IRENA classes (scripts/ingest_irena.py)
PSR_CLS = {"B16": "solar", "B19": "wind_onshore", "B18": "wind_offshore", "B11": "hydro", "B12": "hydro",
           "B10": "pumped", "B14": "nuclear", "B02": "fossil", "B03": "fossil", "B04": "fossil", "B05": "fossil",
           "B06": "fossil", "B07": "fossil", "B08": "fossil"}
FOSSIL_IRENA = ("coal", "gas", "oil", "fossil_nes")
MIN_COVER = 0.90
CLS_CEILING = {"solar": 0.25, "wind_onshore": 0.40, "wind_offshore": 0.60}  # per class, 30-day window (see CF_CEILING)


def plausible_cf(cls: str, cf):
    """The capacity factor, or None where it is above the class's physical ceiling (capacity older than the fleet)."""
    if cf is None or cf != cf:
        return None
    return None if cf > CLS_CEILING.get(cls, 1.0) else cf
# A 30-day capacity factor above these is not physical for the zone: the IRENA capacity is older than the fleet that
# produced the energy. The value is dropped (None) and the zone is flagged `stale` instead of printing a wrong number.
CF_CEILING = {"solar": 0.25, "wind": 0.40}


@lru_cache(maxsize=1)
def _irena() -> pd.DataFrame:
    p = REF / "irena_capacity.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["iso3", "country", "year", "cls", "cap_mw", "gen_gwh"])


def capacity() -> pd.DataFrame:
    """zone, cls, cap_mw, year - latest year with capacity per country, fossil fuels summed into 'fossil'."""
    t = _irena()
    t = t[t["cap_mw"].notna()].copy()
    if t.empty:
        return pd.DataFrame(columns=["zone", "cls", "cap_mw", "year"])
    t["cls"] = t["cls"].where(~t["cls"].isin(FOSSIL_IRENA), "fossil")
    rows = []
    for zone, isos in ISO3.items():
        z = t[t["iso3"].isin(isos)]
        if z.empty:
            continue
        yr = int(z["year"].max())
        g = z[z["year"] == yr].groupby("cls", as_index=False)["cap_mw"].sum()
        rows += [(zone, r.cls, float(r.cap_mw), yr) for r in g.itertuples()]
    return pd.DataFrame(rows, columns=["zone", "cls", "cap_mw", "year"])


def capacity_factors(ga: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, cap: pd.DataFrame | None = None) -> pd.DataFrame:
    """zone, cls, gen_gwh, cap_mw, cf (0..1), cover (0..1) for [start, end) UTC from raw gen_actual rows."""
    cols = ["zone", "cls", "gen_gwh", "cap_mw", "cf", "cover"]
    cap = capacity() if cap is None else cap
    if ga is None or ga.empty or cap.empty:
        return pd.DataFrame(columns=cols)
    d = ga[(ga["dir"] == "gen") & ga["psr"].isin(PSR_CLS) & (ga["ts"] >= start) & (ga["ts"] < end)].copy()
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["cls"] = d["psr"].map(PSR_CLS)
    d["h"] = d["ts"].dt.floor("h")
    # hourly mean MW per zone and class (types of one class are summed within the same instant first)
    inst = d.groupby(["zone", "cls", "ts"], as_index=False)["mw"].sum()
    inst["h"] = inst["ts"].dt.floor("h")
    hr = inst.groupby(["zone", "cls", "h"], as_index=False)["mw"].mean()
    hours = (end - start) / pd.Timedelta(hours=1)
    g = hr.groupby(["zone", "cls"]).agg(mwh=("mw", "sum"), n=("mw", "size")).reset_index()
    g["cover"] = g["n"] / hours
    g = g[g["cover"] >= MIN_COVER]
    g["gen_gwh"] = g["mwh"] / 1000.0
    g = g.merge(cap[["zone", "cls", "cap_mw"]], on=["zone", "cls"], how="left")
    # energy over the window = mean MW x window hours (gaps are filled with the mean of the hours that are there)
    g["cf"] = (g["mwh"] / g["n"]) / g["cap_mw"]
    return g[cols]


PEAK_DAYS = 90
MIN_PEAK_HOURS = 24 * 30  # a peak needs at least 30 days of hourly data in the 90-day window


def hourly_by_class(ga: pd.DataFrame, key: str = "zone") -> pd.DataFrame:
    """key, cls, h, mw: hourly mean output per class (types of one class summed within each instant first)."""
    if ga is None or ga.empty:
        return pd.DataFrame(columns=[key, "cls", "h", "mw"])
    d = ga[(ga["dir"] == "gen") & ga["psr"].isin(PSR_CLS)].assign(cls=lambda x: x["psr"].map(PSR_CLS), mw=lambda x: x["mw"].clip(lower=0))
    inst = d.groupby([key, "cls", "ts"], as_index=False)["mw"].sum()
    inst["h"] = inst["ts"].dt.floor("h")
    return inst.groupby([key, "cls", "h"], as_index=False)["mw"].mean()


def peak_capacity(hc: pd.DataFrame, end: pd.Timestamp, days: int = PEAK_DAYS, key: str = "zone") -> pd.DataFrame:
    """key, cls, cap_mw: the highest hourly output in [end - days, end), the capacity proxy (needs MIN_PEAK_HOURS hours)."""
    w = hc[(hc["h"] >= end - pd.Timedelta(days=days)) & (hc["h"] < end)]
    g = w.groupby([key, "cls"])["mw"].agg(cap_mw="max", n="size").reset_index()
    return g[(g["n"] >= MIN_PEAK_HOURS) & (g["cap_mw"] > 0)][[key, "cls", "cap_mw"]]


def peak_cf(hc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, key: str = "zone") -> pd.DataFrame:
    """key, cls, mean_mw, cap_mw (90-day peak before `end`), cf (0..1), cover for the window [start, end)."""
    cap = peak_capacity(hc, end, key=key)
    w = hc[(hc["h"] >= start) & (hc["h"] < end)]
    hours = (end - start) / pd.Timedelta(hours=1)
    g = w.groupby([key, "cls"])["mw"].agg(mean_mw="mean", n="size").reset_index()
    g["cover"] = g["n"] / hours
    g = g[g["cover"] >= MIN_COVER].merge(cap, on=[key, "cls"], how="inner")
    g["cf"] = g["mean_mw"] / g["cap_mw"]
    return g[[key, "cls", "mean_mw", "cap_mw", "cf", "cover"]]


def _mean_load(ld: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    if ld is None or ld.empty:
        return pd.Series(dtype=float)
    d = ld[(ld["kind"] == "actual") & (ld["ts"] >= start) & (ld["ts"] < end)]
    return d.groupby("zone")["mw"].mean()


def fundamentals_table(ga: pd.DataFrame, ld: pd.DataFrame, metrics: pd.DataFrame, day: pd.Timestamp,
                       zones: list[str], days: int = 30, hp: pd.DataFrame | None = None) -> list[dict]:
    """Rows for `zones` over the `days` CET days ending on `day` (naive timestamp); `ga` should cover PEAK_DAYS for the
    capacity proxy, `hp` = hourly prices (metrics.hourly_prices) for the 30-day capture rates. Missing pieces are None.
    wind = onshore + offshore. Shares = output / load (energy over the hours with both); CF vs the 90-day peak; capture
    rate = output-weighted price / mean price over the window (|mean| >= 5 EUR/MWh only)."""
    end = (day + pd.Timedelta(days=1)).tz_localize("Europe/Brussels").tz_convert("UTC")
    start = end - pd.Timedelta(days=days)
    hc = hourly_by_class(ga)
    hc["grp"] = hc["cls"].map({"solar": "solar", "wind_onshore": "wind", "wind_offshore": "wind"})
    v = hc[hc["grp"].notna()]
    cfc = peak_cf(v, start, end)
    cfc["grp"] = cfc["cls"].map({"solar": "solar", "wind_onshore": "wind", "wind_offshore": "wind"})
    cfg = cfc.groupby(["zone", "grp"]).agg(mean_mw=("mean_mw", "sum"), cap_mw=("cap_mw", "sum")).reset_index()
    vw = v[(v["h"] >= start) & (v["h"] < end)].groupby(["zone", "grp", "h"], as_index=False)["mw"].sum()
    l = ld[(ld["kind"] == "actual") & (ld["ts"] >= start) & (ld["ts"] < end)] if ld is not None and not ld.empty else pd.DataFrame(columns=["zone", "ts", "mw"])
    lh = (l.assign(h=l["ts"].dt.floor("h")).groupby(["zone", "h"], as_index=False)["mw"].mean().rename(columns={"mw": "load"})
          if not l.empty else pd.DataFrame({"zone": pd.Series(dtype=str), "h": pd.Series(dtype="datetime64[ns, UTC]"), "load": pd.Series(dtype=float)}))
    sh = vw.merge(lh, on=["zone", "h"]).groupby(["zone", "grp"])[["mw", "load"]].sum()
    cr = pd.Series(dtype=float)
    if hp is not None and not hp.empty:
        pw = hp[(hp["h"] >= start) & (hp["h"] < end)]
        base = pw.groupby("zone")["price"].mean()
        j = vw.merge(pw, on=["zone", "h"])
        cap_p = (j.assign(r=j["mw"] * j["price"]).groupby(["zone", "grp"])[["r", "mw"]].sum())
        cap_p = cap_p[cap_p["mw"] > 0]
        cr = (cap_p["r"] / cap_p["mw"]).to_frame("cp").join(base.rename("base"), on="zone")
        cr = cr[cr["base"].abs() >= 5]
        cr = cr["cp"] / cr["base"]
    w = metrics[(metrics["day"] > day - pd.Timedelta(days=days)) & (metrics["day"] <= day)]
    pm = w.groupby(["zone", "metric"])["value"].mean() if not w.empty else pd.Series(dtype=float)
    nh = w[w["metric"] == "neg_hours"].groupby("zone")["value"].sum() if not w.empty else pd.Series(dtype=float)
    gi = cfg.set_index(["zone", "grp"]) if not cfg.empty else None
    out = []
    for z in zones:
        def share(g):
            if (z, g) not in sh.index or sh.loc[(z, g), "load"] <= 0:
                return None
            return sh.loc[(z, g), "mw"] / sh.loc[(z, g), "load"]
        def cf(g):
            return None if gi is None or (z, g) not in gi.index else gi.loc[(z, g), "mean_mw"] / gi.loc[(z, g), "cap_mw"]
        def pk(g):
            return None if gi is None or (z, g) not in gi.index else round(gi.loc[(z, g), "cap_mw"] / 1000, 2)
        ws, ss = share("wind"), share("solar")
        if ws is None and ss is None and pm.get((z, "baseload")) is None:
            continue
        out.append({"zone": z, "wind_share": _pct(ws), "solar_share": _pct(ss),
                    "vre_share": _pct((ws or 0) + (ss or 0)) if (ws is not None or ss is not None) else None,
                    "wind_cf": _pct(cf("wind")), "solar_cf": _pct(cf("solar")), "wind_peak_gw": pk("wind"), "solar_peak_gw": pk("solar"),
                    "cr_wind": _pct(cr.get((z, "wind"))), "cr_solar": _pct(cr.get((z, "solar"))),
                    "baseload": _r(pm.get((z, "baseload"))), "tb4": _r(pm.get((z, "tb4"))), "neg_hours": _r(nh.get(z), 0)})
    return out


def _pct(x):
    return None if x is None or x != x else round(100 * float(x), 1)


def _r(x, nd=1):
    return None if x is None or x != x else round(float(x), nd)


def country_capacity() -> pd.DataFrame:
    """iso3, country, cls, cap_mw, year - every IRENA country, latest year with capacity, fossil fuels summed."""
    t = _irena()
    t = t[t["cap_mw"].notna()].copy()
    if t.empty:
        return pd.DataFrame(columns=["iso3", "country", "cls", "cap_mw", "year"])
    t["cls"] = t["cls"].where(~t["cls"].isin(FOSSIL_IRENA), "fossil")
    yr = t.groupby("iso3")["year"].transform("max")
    t = t[t["year"] == yr]
    return t.groupby(["iso3", "country", "cls", "year"], as_index=False)["cap_mw"].sum()


def country_capacity_factors(ga: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """iso3, cls, gen_gwh, cap_mw, cf, cover for countries whose bidding zones are ALL in `ga` (generation of the zones
    is summed instant by instant, so a country with a zone missing would read too low and is left out)."""
    cols = ["iso3", "cls", "gen_gwh", "cap_mw", "cf", "cover"]
    cc = country_capacity()
    if ga is None or ga.empty or cc.empty:
        return pd.DataFrame(columns=cols)
    have = set(ga["zone"])
    need: dict[str, set] = {}
    for z, iso in ZONE_ISO3.items():
        need.setdefault(iso, set()).add(z)
    ok = {iso for iso, zs in need.items() if zs <= have}
    g = ga[ga["zone"].isin([z for z, i in ZONE_ISO3.items() if i in ok])].copy()
    if g.empty:
        return pd.DataFrame(columns=cols)
    g["zone"] = g["zone"].map(ZONE_ISO3)
    cap = cc.rename(columns={"iso3": "zone"})[["zone", "cls", "cap_mw"]]
    if "DEU" in ok:  # DE-LU: Luxembourg's capacity is part of the zone
        lux = cc[cc["iso3"] == "LUX"].rename(columns={"iso3": "zone"})[["zone", "cls", "cap_mw"]].assign(zone="DEU")
        cap = pd.concat([cap, lux]).groupby(["zone", "cls"], as_index=False)["cap_mw"].sum()
    r = capacity_factors(g, start, end, cap)
    return r.rename(columns={"zone": "iso3"})


def country_peak_cf(ga: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """iso3, cls, mean_mw, cap_mw (90-day peak output), cf for countries whose bidding zones are ALL in `ga` (zones are
    summed instant by instant, so a country with a zone missing would read too low and is left out). `ga` should cover
    PEAK_DAYS before `end`; the CF window is [start, end)."""
    cols = ["iso3", "cls", "mean_mw", "cap_mw", "cf", "cover"]
    if ga is None or ga.empty:
        return pd.DataFrame(columns=cols)
    have = set(ga["zone"])
    need: dict[str, set] = {}
    for z, iso in ZONE_ISO3.items():
        need.setdefault(iso, set()).add(z)
    ok = {iso for iso, zs in need.items() if zs <= have}
    g = ga[ga["zone"].isin([z for z, i in ZONE_ISO3.items() if i in ok])].assign(iso3=lambda x: x["zone"].map(ZONE_ISO3))
    if g.empty:
        return pd.DataFrame(columns=cols)
    return peak_cf(hourly_by_class(g, key="iso3"), start, end, key="iso3")[cols]
