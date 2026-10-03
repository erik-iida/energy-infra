"""Offline test of the newsletter generator against a synthetic local store.   python -m tests.test_newsletter"""
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

tmp = tempfile.mkdtemp()
os.environ["STORE_DIR"] = tmp

from collector.store import Store  # noqa: E402
from newsletter import build, metrics as M, signals as S  # noqa: E402

DAY = pd.Timestamp("2026-10-02")
rng = np.random.default_rng(1)
fetched = pd.Timestamp("2026-10-03 12:40", tz="UTC")


def price_rows(zone, start, end, base, amp, spike_day=None, res=15, cur="EUR"):
    ts = pd.date_range(start, end, freq=f"{res}min", tz="UTC", inclusive="left")
    h = ts.tz_convert(M.CET).hour + ts.tz_convert(M.CET).minute / 60
    p = base + amp * np.sin((h - 7) / 24 * 2 * np.pi) + rng.normal(0, 3, len(ts))
    if spike_day is not None:
        d = ts.tz_convert(M.CET).tz_localize(None).normalize()
        p = np.where(d == spike_day, p + 4 * amp * (np.abs(h - 19) < 2), p)
    return pd.DataFrame({"zone": zone, "ts": ts, "res_min": res, "seq": 1, "price": p, "currency": cur, "fetched": fetched})


def gen_rows(zone, start, end, psr, peak):
    ts = pd.date_range(start, end, freq="15min", tz="UTC", inclusive="left")
    h = ts.tz_convert(M.CET).hour
    mw = np.where((h >= 7) & (h < 17), peak, 0.0)
    return pd.DataFrame({"zone": zone, "ts": ts, "res_min": 15, "psr": psr, "dir": "gen", "mw": mw, "fetched": fetched})


A, B = "2026-06-20", "2026-10-04"  # prices run to the end of 3 Oct (tomorrow's auction is in)
da = pd.concat([
    price_rows("RO", A, B, 100, 40, spike_day=DAY),          # spike on the target day
    price_rows("HU", A, B, 105, 30),
    price_rows("DE-LU", A, B, 110, 35, res=60),              # hourly zone
    price_rows("UA-IPS", A, B, 4000, 1500, cur="UAH"),       # must be ignored (UAH)
])
bad = price_rows("RO", A, B, 9999, 0)                        # seq 2 garbage must be ignored
bad["seq"] = 2
da = pd.concat([da, bad])
# make the last hours of HU's target day missing -> incomplete day
da = da[~((da.zone == "HU") & (da.ts >= pd.Timestamp("2026-10-02 12:00", tz="UTC")) & (da.ts < pd.Timestamp("2026-10-02 22:00", tz="UTC")))]
ga = pd.concat([gen_rows(z, A, B, "B16", 500) for z in ("RO", "DE-LU")])
st = Store()
for month, part in da.groupby(da.ts.dt.strftime("%Y-%m")):
    pass
st.write("da_price", da, log=lambda *_: None)
st.write("gen_actual", ga, log=lambda *_: None)

# ---- metrics
hp = M.hourly_prices(da)
assert set(hp.zone) == {"RO", "HU", "DE-LU"}, "UAH zone must be excluded"
assert hp[hp.zone == "RO"].price.max() < 1000, "seq 2 rows must be ignored"
pm = M.price_metrics(hp)
v = pm[(pm.zone == "RO") & (pm.day == DAY)].set_index("metric").value
g = hp[hp.zone == "RO"].assign(day=M._local_day(hp[hp.zone == "RO"].h))
g = sorted(g[g.day == DAY].price)
assert abs(v["tb2"] - (sum(g[-2:]) / 2 - sum(g[:2]) / 2)) < 1e-9 and abs(v["tb4"] - (sum(g[-4:]) / 4 - sum(g[:4]) / 4)) < 1e-9
assert abs(v["baseload"] - sum(g) / len(g)) < 1e-9
assert pm[(pm.zone == "HU") & (pm.day == DAY) & (pm.metric == "tb4")].empty, "incomplete day must give no spread"
cm = M.all_metrics(da, ga)
cr = cm[(cm.zone == "RO") & (cm.day == DAY) & (cm.metric == "cr_solar")].value.iloc[0]
assert 0.5 < cr < 1.5, cr

# ---- signals
sig = S.evaluate(cm, DAY)
assert any(s["zone"] == "RO" and s["metric"] in ("tb2", "tb4") and s["side"] == "high" for s in sig), sig[:3]
assert not any(s["zone"] == "HU" and s["metric"] == "tb4" for s in sig)
assert sig == sorted(sig, key=lambda s: -s["score"])

# ---- end to end
out = Path(tmp) / "out"
build.main(["--day", "2026-10-02", "--out", str(out)])
f = json.loads((out / "facts.json").read_text())
assert f["day"] == "2026-10-02" and {r["zone"] for r in f["table"]} >= {"RO", "DE-LU"}
assert f["tomorrow"]["day"] == "2026-10-03" and any(r["zone"] == "RO" for r in f["tomorrow"]["zones"])
assert any("HU" in n for n in f["notes"]), f["notes"]
md = (out / "brief.md").read_text()
assert "Headline" in md and "RO" in md and "percentile" in md
assert "<svg" in (out / "brief.html").read_text()
shutil.rmtree(tmp)
print("newsletter tests passed")
