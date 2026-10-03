"""Residual-load and interconnection metrics on synthetic data, and the registry's consistency with the code."""
import pandas as pd

from newsletter import metrics as M, registry as R, signals as S

START = pd.Timestamp("2026-09-09 22:00", tz="UTC")  # = 2026-09-10 00:00 CET
H = pd.date_range(START, periods=72, freq="h")      # three full CET days: 10, 11, 12 Sep


def _gen(zone, psr, mw):
    return pd.DataFrame({"zone": zone, "ts": H, "res_min": 60, "psr": psr, "dir": "gen", "mw": mw})


def test_residual_load():
    ld = pd.DataFrame({"zone": "AA", "ts": H, "res_min": 60, "kind": "actual", "mw": 1000.0})
    sol = [100.0 if 8 <= (h.hour + 2) % 24 <= 16 else 0.0 for h in H]  # CET daytime solar
    ga = pd.concat([_gen("AA", "B16", sol), _gen("AA", "B19", 200.0)], ignore_index=True)
    m = M.all_metrics(pd.DataFrame(columns=["zone", "ts", "seq", "currency", "price"]), ga, None, ld, None)
    d = m[(m["zone"] == "AA") & (m["day"] == pd.Timestamp("2026-09-11"))].set_index("metric")["value"]
    assert abs(d["res_peak"] - 800.0) < 1e-9 and abs(d["res_min"] - 700.0) < 1e-9   # night 1000-200, midday 1000-300
    assert abs(d["res_ramp3"] - 100.0) < 1e-9                                         # 700 -> 800 when solar falls away
    assert abs(d["vre_share"] - (200 * 24 + 100 * 9) / (1000 * 24)) < 1e-9


def test_net_import_needs_the_usual_borders():
    def f(a, b, hours, mw):
        return pd.DataFrame({"from_zone": a, "to_zone": b, "ts": hours, "res_min": 60, "mw": mw})
    day3 = H[:48]  # partner CC drops out on the third day
    fl = pd.concat([f("BB", "AA", H, 300.0), f("AA", "BB", H, 0.0), f("CC", "AA", day3, 100.0), f("AA", "CC", day3, 0.0)],
                   ignore_index=True)
    ld = pd.DataFrame({"zone": "AA", "ts": H, "res_min": 60, "kind": "actual", "mw": 2000.0})
    m = M.flow_metrics(M.hourly_flows(fl), M.hourly_load(ld))
    a = m[m["zone"] == "AA"]
    assert set(a["day"]) == {pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")}   # day 3 lacks border CC: skipped
    d = a[a["day"] == pd.Timestamp("2026-09-10")].set_index("metric")["value"]
    assert abs(d["net_import"] - 400.0) < 1e-9 and abs(d["import_share"] - 0.2) < 1e-9


def test_registry_matches_code():
    ids = set(R.BY_ID)
    assert len(ids) == len(R.METRICS)
    assert {r.metric for r in S.RULES if not r.metric.startswith("spark")} <= ids
    assert {m.family for m in R.METRICS} <= set(R.FAMILIES) and all(m.family in R.GROUP_OF for m in R.METRICS)
    assert "spark_top4" not in ids  # private metrics never enter the catalogue that is exported / stored
