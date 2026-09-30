"""PyWake set-up: a generic power/thrust curve per farm and the four wake models."""
from __future__ import annotations

import numpy as np
from py_wake.literature.gaussian_models import Bastankhah_PorteAgel_2014, Niayifar_PorteAgel_2016
from py_wake.literature.noj import Jensen_1983
from py_wake.literature.turbopark import Nygaard_2022
from py_wake.site import UniformSite
from py_wake.wind_turbines import WindTurbine
from py_wake.wind_turbines.power_ct_functions import PowerCtTabular

from . import config

WS = np.arange(0, 30.01, 0.25)


def power_mw(ws, rated_mw: float, u_rated: float):
    """Generic curve: P = 0.5 rho A Cp U^3 (i.e. rated * (U/U_rated)^3) from cut-in, flat from rated to
    cut-out. Same curve as the web page."""
    ws = np.asarray(ws, dtype=float)
    p = rated_mw * np.clip(ws / u_rated, 0, 1) ** 3
    return np.where((ws < config.CUT_IN) | (ws > config.CUT_OUT), 0.0, p)


def ct_curve(ws, u_rated: float):
    ws = np.asarray(ws, dtype=float)
    ct = np.where(ws <= u_rated, 0.8, 0.8 * (u_rated / np.maximum(ws, 1e-6)) ** 3)
    ct = np.maximum(ct, 0.05)
    return np.where((ws < config.CUT_IN) | (ws > config.CUT_OUT), 0.05, np.minimum(ct, 0.8))


def turbine(f: dict) -> WindTurbine:
    return WindTurbine(
        name=f.get("t", "generic"), diameter=f["D"], hub_height=f["h"],
        powerCtFunction=PowerCtTabular(WS, power_mw(WS, f["mw"], f["ur"]) * 1e3, "kW", ct_curve(WS, f["ur"])),
    )


SITE = UniformSite(p_wd=[1], ti=config.TI)


def models_for(f: dict) -> dict:
    wt = turbine(f)
    return {
        "jensen": Jensen_1983(SITE, wt, k=0.04),
        "bastankhah": Bastankhah_PorteAgel_2014(SITE, wt, k=0.0324),
        "niayifar": Niayifar_PorteAgel_2016(SITE, wt),
        "turbopark": Nygaard_2022(SITE, wt),
    }


def farm_power(f: dict, ws_hub: np.ndarray, wd: np.ndarray) -> dict[str, np.ndarray]:
    """Total farm power [MW] per time step for every wake model plus the no-wake reference."""
    n = len(f["xy"]) // 2
    x, y = np.array(f["xy"][0::2], float), np.array(f["xy"][1::2], float)
    out = {"nowake": power_mw(ws_hub, f["mw"], f["ur"]) * n}
    ws_in = np.maximum(ws_hub, 0.1)
    for key, wfm in models_for(f).items():
        sim = wfm(x, y, ws=ws_in, wd=wd % 360, time=True)
        out[key] = sim.Power.values.sum(axis=0) / 1e6  # W -> MW, summed over turbines
    return out


def estimate_no_layout(f: dict, ws_hub: np.ndarray) -> dict[str, np.ndarray]:
    free = power_mw(ws_hub, f["cap"], config.GENERIC_RATED_SPEED)
    out = {"nowake": free}
    for key in config.WAKE_MODELS:
        out[key] = free * config.NO_LAYOUT_EFFICIENCY
    return out
