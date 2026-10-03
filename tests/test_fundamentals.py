"""Capacity factors from synthetic generation against a synthetic capacity table (no store, no network)."""
import pandas as pd

from newsletter import fundamentals as FU


def _ga(zone, psr, mw, start, hours):
    ts = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"zone": zone, "ts": ts, "res_min": 60, "psr": psr, "dir": "gen", "mw": mw})


def test_cf_and_coverage_and_ceiling():
    start = pd.Timestamp("2026-09-01", tz="UTC")
    end = start + pd.Timedelta(days=10)
    cap = pd.DataFrame([("XX", "wind_onshore", 1000.0, 2024), ("XX", "solar", 1000.0, 2024),
                        ("YY", "solar", 1000.0, 2024)], columns=["zone", "cls", "cap_mw", "year"])
    ga = pd.concat([
        _ga("XX", "B19", 300.0, start, 240),            # CF 0.30 over the full window
        _ga("XX", "B16", 100.0, start, 240),            # CF 0.10
        _ga("YY", "B16", 100.0, start, 100),            # only 100 of 240 hours -> left out
    ], ignore_index=True)
    cf = FU.capacity_factors(ga, start, end, cap).set_index(["zone", "cls"])
    assert abs(cf.loc[("XX", "wind_onshore"), "cf"] - 0.30) < 1e-9
    assert abs(cf.loc[("XX", "solar"), "cf"] - 0.10) < 1e-9
    assert ("YY", "solar") not in cf.index
    assert abs(cf.loc[("XX", "wind_onshore"), "gen_gwh"] - 72.0) < 1e-9


def test_capacity_sums_fossil_and_countries():
    cap = FU.capacity()
    assert not cap.empty
    de = cap[cap["zone"] == "DE-LU"].set_index("cls")["cap_mw"]
    assert de["solar"] > 50000 and "fossil" in de.index
