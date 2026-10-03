"""GB history and forecasts from NESO / Elexon-shaped files: time stamps (DST), merge, forecast long format (no network)."""
from datetime import datetime, timezone

import pandas as pd

from collector import gbhist as H

MIX = pd.DataFrame({
    "DATETIME": ["2026-03-29T00:00:00", "2026-03-29T00:30:00", "2026-03-29T01:00:00"],
    "GAS": [3000, 3100, 3200], "WIND": [4000, 4100, 4200], "WIND_EMB": [700, 710, 720], "SOLAR": [0, 0, 5],
    "CARBON_INTENSITY": [95, 96, 97], "GENERATION": [32000, 32100, 32200], "RENEWABLE": [1, 2, 3], "GAS_perc": [10, 10, 10],
})
DEM = pd.DataFrame({
    "SETTLEMENT_DATE": ["2026-03-29"] * 4 + ["2026-03-30"], "SETTLEMENT_PERIOD": [1, 2, 3, 4, 1],
    "ND": [21000, 21100, 21200, 21300, 22000], "FORECAST_ACTUAL_INDICATOR": ["A", "A", "A", "A", "F"],
    "IFA_FLOW": [-1500, -1400, -1300, -1200, 0],
})


def test_london_time_stamps_follow_dst():
    ts = H.london_to_utc(pd.Series(["2026-03-29", "2026-03-29", "2026-03-29"]), pd.Series([1, 2, 3]))
    # clocks go forward at 01:00 UTC: period 1-2 are 00:00 / 00:30 GMT, period 3 is 02:00 BST = 01:00 UTC
    assert [str(x) for x in ts] == ["2026-03-29 00:00:00+00:00", "2026-03-29 00:30:00+00:00", "2026-03-29 01:00:00+00:00"]
    s = H.london_to_utc(pd.Series(["2026-07-01"]), pd.Series([1]))
    assert str(s.iloc[0]) == "2026-06-30 23:00:00+00:00"  # BST midnight


def test_parse_mix_and_demand():
    m = H.parse_mix(MIX.copy())
    assert "gas_perc" not in m and "renewable" not in m and "carbon_intensity" in m and m["ts"].dt.tz is not None
    d = H.parse_demand(DEM.copy())
    assert len(d) == 4 and "forecast_actual_indicator" not in d  # forecast row dropped
    assert d["ts"].iloc[0] == pd.Timestamp("2026-03-29T00:00Z")


def test_hist_frame_merges(monkeypatch):
    res = lambda url_name: [{"name": url_name, "format": "CSV", "url": "u://" + url_name}]
    monkeypatch.setattr(H, "neso_resources", lambda p: res("x") if p == "historic-generation-mix" else res("Historic Demand Data 2026"))
    monkeypatch.setattr(H, "neso_csv", lambda url, **k: MIX.copy() if url == "u://x" else DEM.copy())
    f = H.hist_frame(None, datetime.now(timezone.utc))
    assert {"zone", "res_min", "fetched", "gas", "nd", "ifa_flow", "carbon_intensity"} <= set(f.columns)
    assert len(f) == 4 and f.loc[f.ts == pd.Timestamp("2026-03-29T01:00Z"), "nd"].iloc[0] == 21200
    assert f.loc[f.ts == pd.Timestamp("2026-03-29T01:30Z"), "gas"].isna().all()  # outer merge keeps the demand-only half hour


def test_forecast_frames(monkeypatch):
    fetched = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    da = pd.DataFrame({"Datetime_GMT": ["2026-10-03T23:00:00", "2026-10-03T23:30:00"], "Capacity": [25000, 25000], "Incentive_forecast": [6400, 6500]})
    monkeypatch.setattr(H, "neso_resources", lambda p: [{"name": "Day Ahead Wind Forecast", "format": "CSV", "url": "u"}])
    monkeypatch.setattr(H, "neso_csv", lambda url, **k: da)
    f = H.neso_wind_da(fetched, archive=False)
    assert set(f["series"]) == {"wind_da", "wind_da_incentive"} and len(f) == 4 and (f["res_min"] == 30).all()
    rows = {
        "demand": [{"startTime": "2026-10-03T13:00:00Z", "boundary": "N", "publishTime": "2026-10-03T12:48:00Z", "transmissionSystemDemand": 22734, "nationalDemand": 20100},
                   {"startTime": "2026-10-03T13:00:00Z", "boundary": "E", "publishTime": "2026-10-03T12:48:00Z", "transmissionSystemDemand": 1, "nationalDemand": 1}],
        "ws": [{"publishTime": "2026-10-02T16:45:03Z", "psrType": "Solar", "startTime": "2026-10-03T00:00:00Z", "quantity": 0.0},
               {"publishTime": "2026-10-02T16:45:03Z", "psrType": "Wind Offshore", "startTime": "2026-10-03T00:00:00Z", "quantity": 9000.0}],
    }
    monkeypatch.setattr(H, "_get", lambda url, params, **k: type("R", (), {"json": lambda s: rows["demand" if "demand" in url else "ws"]})())
    e = H.elexon_forecasts(fetched, fetched, fetched)
    assert set(e["series"]) == {"da_national_demand", "da_transmission_demand", "da_solar", "da_wind_offshore"}
    assert e[e.series == "da_national_demand"]["mw"].tolist() == [20100]  # national boundary only
