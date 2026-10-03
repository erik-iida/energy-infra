"""Live 24 h System-tab entries for Great Britain and Ireland from open sources without keys (Elexon BMRS, EirGrid dashboard).
Same shape as pipeline.entsoe.system(): {"series": {id: [24 hourly MW]}, "names", "flows", "flow_names", "zones", "name", "src"}.
Credits: "Contains BMRS data (c) Elexon Limited copyright and database right <year>"; "Supported by EirGrid Group Data"."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from collector import gbie as G

from .entsoe import PSR

NB_KEY = {"FR": "fr", "NL": "nl", "BE": "be", "NO2": "no2", "DK1": "dk1", "IE(SEM)": "ie"}


def _hourly(df: pd.DataFrame, col: str, hours: list[int]) -> list:
    if df is None or df.empty:
        return [None] * len(hours)
    s = df.groupby(df["ts"].dt.floor("h"))[col].mean()
    idx = {int(t.timestamp()): v for t, v in s.items()}
    return [None if h not in idx else round(float(idx[h]), 1) for h in hours]


def _net(fl: pd.DataFrame, own: str, nb: str, hours: list[int]) -> list:
    """Net import into `own` from `nb` (MW, hourly mean)."""
    imp = fl[(fl["from_zone"] == nb) & (fl["to_zone"] == own)].set_index("ts")["mw"]
    exp = fl[(fl["from_zone"] == own) & (fl["to_zone"] == nb)].set_index("ts")["mw"]
    n = (imp - exp).dropna().rename("mw").reset_index()
    return _hourly(n, "mw", hours)


def system(hours: list[int], ie_base: dict | None = None) -> dict[str, dict]:
    """hours = epoch seconds of the 48 feed hours (24 past + 24 forecast); returns {"gb": entry, "ie": entry} (entries that worked)."""
    past = hours[:24]
    a = datetime.fromtimestamp(past[0] - 3600, tz=timezone.utc)
    b = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    fetched = datetime.now(timezone.utc)
    f = G.gb_frames(a, b, fetched)
    out = {}
    g, ld, fl = f["gen_actual"], f["load"], f["flows"]
    if not g.empty:
        names = {v[0]: v[1] for v in PSR.values()}
        ser, nm = {}, {}
        for psr, grp in g.groupby("psr"):
            key = PSR[psr][0]
            vals = _hourly(grp, "mw", past)
            if any(v is not None for v in vals):
                ser[key] = [(x or 0) + (y or 0) if (x is not None or y is not None) else None
                            for x, y in zip(ser.get(key, [None] * 24), vals)] if key in ser else vals
                nm[key] = names[key]
        lg = ld[ld["kind"] == "actual"] if not ld.empty else ld
        lv = _hourly(lg, "mw", past)
        if any(v is not None for v in lv):
            ser["load"], nm["load"] = lv, "Load"
        flows, fnames = {}, {}
        if not fl.empty:
            for z, k in NB_KEY.items():
                v = _net(fl, "GB", z, past)
                if any(x is not None for x in v):
                    flows[k], fnames[k] = v, z.replace("IE(SEM)", "IE")
            if flows:
                flows["sum"] = [round(sum(v[i] for v in flows.values() if v[i] is not None), 1)
                                if any(v[i] is not None for v in flows.values()) else None for i in range(24)]
                fnames["sum"] = "Net import"
        out["gb"] = {"series": ser, "names": nm, "flows": flows, "flow_names": fnames, "zones": [], "name": "Great Britain", "src": "elexon"}
    # Ireland: generation from ENTSO-E (pipeline.entsoe.system, "ie"), load from EirGrid, flow to GB mirrored from Elexon
    ie = ie_base if ie_base and ie_base.get("series") else {"series": {}, "names": {}, "flows": {}, "flow_names": {}, "zones": ["IE(SEM)"],
                                                         "name": "Ireland", "src": "entsoe"}
    ie = {**ie, "series": dict(ie["series"]), "names": dict(ie.get("names", {}))}
    d = G.fetch_eirgrid_demand(a, b, "Europe/Dublin")
    lv = _hourly(d, "mw", past) if not d.empty else [None] * 24
    if any(v is not None for v in lv):
        ie["series"]["load"], ie["names"]["load"] = lv, "Load"
    if not fl.empty:
        v = _net(fl, "IE(SEM)", "GB", past)
        if any(x is not None for x in v):
            ie["flows"] = {"gb": v, "sum": list(v)}
            ie["flow_names"] = {"gb": "GB", "sum": "Net import"}
    if ie["series"]:
        out["ie"] = ie
    return out
