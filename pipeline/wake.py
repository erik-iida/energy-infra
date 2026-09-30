"""PyWake set-up: turbine types with their power/Ct curves, and the four wake models.

Farms with turbine positions use the per-type generic curves shipped with the EuroWindWakes database
(generated with PyWake's generic turbine generator: cut-in 4 m/s, cut-out 25 m/s, TI 5 %). Farms with only
an outline use a simple cubic curve on their stated capacity.
"""
from __future__ import annotations

import numpy as np
from py_wake.literature.gaussian_models import Bastankhah_PorteAgel_2014, Niayifar_PorteAgel_2016
from py_wake.literature.noj import Jensen_1983
from py_wake.literature.turbopark import Nygaard_2022
from py_wake.site import UniformSite
from py_wake.wind_turbines import WindTurbine, WindTurbines
from py_wake.wind_turbines.power_ct_functions import PowerCtTabular

from . import config

SITE = UniformSite(p_wd=[1], ti=config.TI)


# ---------------------------------------------------------------- curves
def padded(t: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Table from the database, padded with zero power / zero thrust below cut-in and above cut-out."""
    ws, p, ct = (np.asarray(t[k], float) for k in ("ws", "p", "ct"))
    lo = np.arange(0, ws[0], 0.5)
    ws_f = np.concatenate([lo, [ws[0] - 1e-3], ws, [ws[-1] + 1e-3, 30.0]])
    p_f = np.concatenate([np.zeros(len(lo) + 1), p, [0.0, 0.0]])
    ct_f = np.concatenate([np.zeros(len(lo) + 1), ct, [0.0, 0.0]])
    return ws_f, p_f, ct_f


def type_power(t: dict, ws) -> np.ndarray:
    ws_f, p_f, _ = padded(t)
    return np.interp(np.asarray(ws, float), ws_f, p_f)


def generic_power(ws, rated_mw: float, u_rated: float) -> np.ndarray:
    """Cubic curve up to rated, used for farms without turbine data. Same as the web page."""
    ws = np.asarray(ws, dtype=float)
    p = rated_mw * np.clip(ws / u_rated, 0, 1) ** 3
    return np.where((ws < config.CUT_IN) | (ws > config.CUT_OUT), 0.0, p)


def turbines_for(f: dict, types: list[dict]) -> tuple[WindTurbines, np.ndarray, list[int]]:
    """WindTurbines object for the types in this farm, and the local type index of each turbine."""
    n = len(f["xy"]) // 2
    ti = f["ti"] if isinstance(f["ti"], list) else [f["ti"]] * n
    used = sorted(set(ti))
    local = {g: i for i, g in enumerate(used)}
    wts = []
    for g in used:
        t = types[g]
        ws_f, p_f, ct_f = padded(t)
        wts.append(WindTurbine(name=t["name"], diameter=t["D"], hub_height=f["h"],
                               powerCtFunction=PowerCtTabular(ws_f, p_f * 1e3, "kW", ct_f)))
    return WindTurbines.from_WindTurbine_lst(wts), np.array([local[g] for g in ti]), ti


def farm_power(f: dict, types: list[dict], ws_hub: np.ndarray, wd: np.ndarray) -> dict[str, np.ndarray]:
    """Total farm power [MW] per time step for every wake model plus the no-wake reference."""
    x, y = np.array(f["xy"][0::2], float), np.array(f["xy"][1::2], float)
    wt, tloc, ti = turbines_for(f, types)
    counts = {g: ti.count(g) for g in set(ti)}
    out = {"nowake": sum(c * type_power(types[g], ws_hub) for g, c in counts.items())}
    ws_in = np.maximum(ws_hub, 0.1)
    models = {
        "jensen": Jensen_1983(SITE, wt, k=0.04),
        "bastankhah": Bastankhah_PorteAgel_2014(SITE, wt, k=0.0324555),
        "niayifar": Niayifar_PorteAgel_2016(SITE, wt),
        "turbopark": Nygaard_2022(SITE, wt),
    }
    for key, wfm in models.items():
        sim = wfm(x, y, type=tloc, ws=ws_in, wd=wd % 360, time=True)
        out[key] = sim.Power.values.sum(axis=0) / 1e6  # W -> MW, summed over turbines
    return out


def estimate_no_layout(f: dict, ws_hub: np.ndarray) -> dict[str, np.ndarray]:
    free = generic_power(ws_hub, f["cap"], config.GENERIC_RATED_SPEED)
    out = {"nowake": free}
    for key in config.WAKE_MODELS:
        out[key] = free * config.NO_LAYOUT_EFFICIENCY
    return out
