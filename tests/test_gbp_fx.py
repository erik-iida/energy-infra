"""GBP -> EUR for GB prices: ECB history parsing, daily rate lookup, TB2/TB4 inputs in EUR (no network)."""
import pandas as pd

from newsletter import metrics as M
from pipeline import entsoe


def test_parse_ecb_gbp():
    csv = "Date,USD,GBP,\\n2026-10-02,1.10,0.8600,\\n2026-10-01,1.10,0.8500,\\n2022-01-03,1.1,0.84,\\n2026-09-30,1.1,N/A,\\n".replace("\\n", "\n")
    h = entsoe.parse_ecb_gbp(csv)
    assert h == {"2026-10-02": 0.86, "2026-10-01": 0.85}  # before 2023 and N/A dropped


def test_parse_ecb_formats():
    api = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\nEXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2026-10-02,0.8701\n"
    assert entsoe.parse_ecb_gbp(api) == {"2026-10-02": 0.8701}
    padded = "\ufeffDate, USD, GBP, \n2026-10-02, 1.17, 0.8702, \n"  # padded header names, BOM
    assert entsoe.parse_ecb_gbp(padded) == {"2026-10-02": 0.8702}
    assert entsoe.parse_ecb_gbp("<html>moved</html>") == {}


def test_hourly_prices_convert_gbp(monkeypatch):
    monkeypatch.setattr(entsoe, "fx_table", lambda: {"GBP": {"history": {"2026-10-01": 0.80, "2026-10-02": 0.90}}})
    ts = [pd.Timestamp("2026-10-02T10:00Z"), pd.Timestamp("2026-10-02T10:30Z"), pd.Timestamp("2026-10-03T10:00Z")]  # 3 Oct: last rate (2 Oct)
    da = pd.concat([
        pd.DataFrame({"zone": "GB", "ts": ts, "res_min": 30, "seq": 1, "price": [90.0, 108.0, 99.0], "currency": "GBP"}),
        pd.DataFrame({"zone": "DE-LU", "ts": ts[:1], "res_min": 60, "seq": 1, "price": [100.0], "currency": "EUR"}),
        pd.DataFrame({"zone": "UA-IPS", "ts": ts[:1], "res_min": 60, "seq": 1, "price": [4000.0], "currency": "UAH"}),
        pd.DataFrame({"zone": "DE-LU", "ts": ts[:1], "res_min": 60, "seq": 2, "price": [5.0], "currency": "EUR"})], ignore_index=True)
    hp = M.hourly_prices(da).set_index(["zone", "h"])["price"]
    assert abs(hp[("GB", pd.Timestamp("2026-10-02T10:00Z"))] - 110.0) < 1e-9   # mean(90, 108) / 0.90
    assert abs(hp[("GB", pd.Timestamp("2026-10-03T10:00Z"))] - 110.0) < 1e-9   # 99 / 0.90
    assert hp[("DE-LU", pd.Timestamp("2026-10-02T10:00Z"))] == 100.0            # seq 2 and UAH rows still excluded
    assert set(hp.index.get_level_values(0)) == {"GB", "DE-LU"}


def test_no_rate_drops_gb(monkeypatch):
    monkeypatch.setattr(entsoe, "fx_table", lambda: {})
    da = pd.DataFrame({"zone": "GB", "ts": [pd.Timestamp("2026-10-02T10:00Z")], "res_min": 30, "seq": 1, "price": [90.0], "currency": "GBP"})
    assert M.hourly_prices(da).empty
