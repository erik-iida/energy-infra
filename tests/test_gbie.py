"""GB frames from Elexon-shaped rows: store schema, the consumption estimate and the flow sign convention (no network)."""
from datetime import datetime, timezone

import pandas as pd

from collector import gbie as G

A = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
B = datetime(2026, 10, 3, 11, 0, tzinfo=timezone.utc)


def _ts(*m):
    return [pd.Timestamp(2026, 10, 3, 10, x, tz="UTC") for x in m]


def test_gb_frames(monkeypatch):
    t = _ts(0, 30)
    fh = pd.DataFrame([{"ts": x, "fuelType": f, "generation": v} for x in t for f, v in
                       [("CCGT", 2000), ("OCGT", 10), ("NUCLEAR", 4000), ("WIND", 3000), ("PS", 100),
                        ("INTFR", 2500), ("INTELEC", 500), ("INTNSL", -1400), ("INTEW", -300)]])
    ws = pd.DataFrame([{"ts": x, "psrType": p, "quantity": v} for x in t for p, v in
                       [("Solar", 8000), ("Wind Onshore", 2500), ("Wind Offshore", 1500)]])
    nd = pd.DataFrame({"ts": t, "initialDemandOutturn": [21000, 21500]})
    monkeypatch.setattr(G, "fetch_fuelhh", lambda a, b: fh)
    monkeypatch.setattr(G, "fetch_b1630", lambda a, b: ws)
    monkeypatch.setattr(G, "fetch_indo", lambda a, b: nd)
    sp = pd.DataFrame({"ts": t, "sell": [100.0, 120.0], "buy": [100.0, 120.0], "niv": [50.0, -20.0]})
    monkeypatch.setattr(G, "fetch_system_prices", lambda a, b: sp)
    monkeypatch.setattr(G, "fetch_mid", lambda a, b: pd.DataFrame({"ts": t, "price": [90.0, 110.0], "volume": [1000.0, 800.0]}))
    f = G.gb_frames(A, B, datetime.now(timezone.utc))
    g = f["gen_actual"]
    assert set(g["psr"]) == {"B04", "B14", "B10", "B16", "B19", "B18"}  # transmission WIND is not double counted
    assert g[(g.psr == "B04") & (g.ts == t[0])]["mw"].iloc[0] == 2010  # CCGT + OCGT
    fl = f["flows"]
    fr = lambda a, b: fl[(fl.from_zone == a) & (fl.to_zone == b) & (fl.ts == t[0])]["mw"].iloc[0]
    assert fr("FR", "GB") == 3000 and fr("GB", "FR") == 0  # INTFR + INTELEC, import into GB
    assert fr("GB", "NO2") == 1400 and fr("NO2", "GB") == 0  # export
    assert fr("GB", "IE(SEM)") == 300
    dp = f["da_price"]
    assert set(dp["currency"]) == {"GBP"} and set(dp["zone"]) == {"GB"} and (dp["seq"] == 1).all() and dp["price"].tolist() == [90.0, 110.0]
    ld = f["load"]
    act = ld[(ld.kind == "actual") & (ld.ts == t[0])]["mw"].iloc[0]
    assert act == 21000 + 8000 + (4000 - 3000)  # national demand + solar + embedded wind (B1630 wind - metered wind)
    assert (ld[ld.kind == "national_demand"]["mw"] == [21000, 21500]).all()
    assert list(f["imb_price"]["sell"]) == [100.0, 120.0] and set(f["imb_price"]["currency"]) == {"GBP"}
    for ds, df in f.items():
        assert {"ts", "res_min", "fetched"} <= set(df.columns)
        assert ({"from_zone", "to_zone"} if ds == "flows" else {"zone"}) <= set(df.columns)
        assert str(df["ts"].dt.tz) == "UTC"


def test_mid_volume_weighted_and_da_price_rows(monkeypatch):
    rows = [{"startTime": "2026-10-03T10:00:00Z", "dataProvider": "APXMIDP", "price": 100.0, "volume": 3000.0},
            {"startTime": "2026-10-03T10:00:00Z", "dataProvider": "N2EXMIDP", "price": 130.0, "volume": 1000.0},
            {"startTime": "2026-10-03T10:30:00Z", "dataProvider": "APXMIDP", "price": 90.0, "volume": 0.0},   # no trades: dropped
            {"startTime": "2026-10-03T10:30:00Z", "dataProvider": "N2EXMIDP", "price": 0.0, "volume": 0.0}]
    monkeypatch.setattr(G, "_get", lambda *a, **k: type("R", (), {"json": lambda s: rows})())
    m = G.fetch_mid(A, B)
    assert len(m) == 1 and abs(m["price"].iloc[0] - 107.5) < 1e-9  # (3000 x 100 + 1000 x 130) / 4000
