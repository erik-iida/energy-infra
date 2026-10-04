"""browse/agg.json (scripts/build_browse.agg_export): window averages of the stored daily metrics for the map's zone colours."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_BACKEND", "local")
    from common.store import Store
    st = Store()
    days = pd.date_range("2026-08-20", "2026-10-03", freq="D")
    rows = []
    for d in days:
        for z, base in (("RO", 100.0), ("HU", 90.0)):
            k = (d - days[0]).days
            rows += [dict(zone=z, day=d, metric="baseload", value=base + k), dict(zone=z, day=d, metric="tb4", value=50 + (k % 5)),
                     dict(zone=z, day=d, metric="tb2", value=30.0), dict(zone=z, day=d, metric="load_mean", value=1000.0),
                     dict(zone=z, day=d, metric="gen_wind_onshore", value=200.0), dict(zone=z, day=d, metric="gen_wind_offshore", value=50.0),
                     dict(zone=z, day=d, metric="gen_solar", value=150.0), dict(zone=z, day=d, metric="gen_total", value=1100.0)]
    df = pd.DataFrame(rows)
    df["version"] = 5
    df["fetched"] = pd.Timestamp.now(tz="UTC")
    st.write("metrics_daily", df, log=lambda *a: None)
    return st


def test_agg_windows(store):
    import build_browse as B
    agg = B.agg_export(store, datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc))
    assert agg and agg["end_day"] == "2026-10-03" and set(agg["zones"]) == {"RO", "HU"}
    ro = agg["zones"]["RO"]
    assert set(ro) == {"w1", "m1", "y1"}
    assert ro["w1"]["n_price"] == 7 and ro["m1"]["n_price"] == 30 and ro["y1"]["n_price"] == 45   # only 45 days exist
    assert ro["w1"]["price"] == pytest.approx(100 + (44 + 38) / 2, abs=0.01)                     # mean of the last 7 daily baseloads
    assert ro["w1"]["wind"] == pytest.approx(25.0) and ro["w1"]["solar"] == pytest.approx(15.0)
    assert ro["w1"]["vre"] == pytest.approx(40.0) and ro["w1"]["self"] == pytest.approx(110.0)
    assert ro["m1"]["tb2"] == 30.0 and ro["m1"]["n_wind"] == 30


def test_agg_without_metrics(store, monkeypatch, tmp_path):
    import build_browse as B
    monkeypatch.setenv("STORE_DIR", str(tmp_path / "empty"))
    from common.store import Store
    assert B.agg_export(Store(), datetime(2026, 10, 4, tzinfo=timezone.utc)) is None
