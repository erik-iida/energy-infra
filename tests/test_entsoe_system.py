"""pipeline.entsoe.system against a fake ENTSO-E API (no network): multi-zone countries, incomplete hours, borders."""
import time
from datetime import datetime, timezone

import pytest

from pipeline import config, entsoe as E

NS = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"
H0 = int(datetime(2026, 10, 4, 0, tzinfo=timezone.utc).timestamp())
HOURS = [H0 + 3600 * i for i in range(48)]   # 24 past + 24 future, "now" = H0 + 23 h


def doc(points: dict[int, float], psr: str | None = None, gen=True) -> str:
    """One TimeSeries, hourly, values per unix hour."""
    hs = sorted(points)
    a, b = hs[0], hs[-1] + 3600
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")  # noqa: E731
    pts = "".join(f"<Point><position>{(h - a) // 3600 + 1}</position><quantity>{points[h]}</quantity></Point>" for h in hs)
    extra = ("<inBiddingZone_Domain.mRID>x</inBiddingZone_Domain.mRID>" if gen else "") + \
            (f"<MktPSRType><psrType>{psr}</psrType></MktPSRType>" if psr else "")
    return (f'<GL_MarketDocument xmlns="{NS}"><TimeSeries>{extra}<Period><timeInterval><start>{iso(a)}</start>'
            f"<end>{iso(b)}</end></timeInterval><resolution>PT60M</resolution>{pts}</Period></TimeSeries></GL_MarketDocument>")


@pytest.fixture
def fake(monkeypatch, tmp_path):
    import xml.etree.ElementTree as ET
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(E, "COUNTRIES", {k: E.COUNTRIES[k] for k in ("dk", "pl")})
    Z = E.ZONE_EIC
    past = HOURS[:24]
    calls = []

    def get(self, **p):
        if self.over_budget():
            return None
        calls.append(p)
        self.calls += 1
        dt = p["documentType"]
        if dt == "A75":
            z = p["in_Domain"]
            if z == Z["DK2"]:   # DK2 has not reported the last 2 hours yet
                return ET.fromstring(doc({h: 100.0 for h in past[:-2]}, "B19"))
            return ET.fromstring(doc({h: 1000.0 for h in past}, "B18" if z == Z["DK1"] else "B05"))
        if dt == "A65":
            return ET.fromstring(doc({h: 500.0 for h in past}, gen=False))
        if dt == "A11":   # 10 MW on every border, imports and exports alike, except DK1 -> DE-LU exports 300 MW
            own_in = p["in_Domain"]
            if p["out_Domain"] == Z["DK1"] and own_in == Z["DE-LU"]:
                return ET.fromstring(doc({h: 300.0 for h in past}, gen=False))
            return ET.fromstring(doc({h: 10.0 for h in past}, gen=False))
        return None

    monkeypatch.setattr(E.Client, "get", get)
    monkeypatch.setattr(E, "token", lambda: "x")
    monkeypatch.setattr(E.Client, "__init__", lambda self: (setattr(self, "calls", 0), setattr(self, "errors", []),
                                                             setattr(self, "t0", time.time())) and None)
    return calls


def test_multizone_sum_drops_incomplete_hours(fake):
    out = E.system(E.Client(), HOURS)
    dk = out["dk"]
    assert dk["zones"] == ["DK1", "DK2"] and dk["name"] == "Denmark"
    s = dk["series"]
    # DK1 offshore 1000 + DK2 onshore 100; the last two hours are dropped because DK2 has not reported
    assert s["wind_offshore"][:22] == [1000.0] * 22 and s["wind_onshore"][:22] == [100.0] * 22
    assert s["wind_offshore"][22:] == [None, None] and s["load"][21] == 1000.0  # load = DK1 + DK2
    assert not dk.get("lag_h")  # 2 h short of now: within the 3 h tolerance


def test_flows_add_up_over_borders(fake):
    dk = E.system(E.Client(), HOURS)["dk"]
    fl = dk["flows"]
    # DE: borders DK1-DE (import 10, export 300) and DK2-DE (import 10, export 10) -> 20 - 310 = -290
    assert fl["de"][0] == -290.0
    assert fl["se"][0] == 0.0 and fl["sum"][0] == -290.0
    assert set(fl) == {"de", "nl", "no", "se", "gb", "sum"}


def test_cache_skips_refetch_within_the_hour(fake):
    E.system(E.Client(), HOURS)
    n = len(fake)
    E.system(E.Client(), HOURS)
    assert len(fake) == n  # both countries served from state/entsoe_cache.json
    assert time.time() > 0


def test_market_build_uses_entsoe_only(monkeypatch, tmp_path):
    from pipeline import gbie_live, market
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(E, "token", lambda: "x")
    monkeypatch.setattr(E.Client, "__init__", lambda self: (setattr(self, "calls", 0), setattr(self, "errors", []),
                                                             setattr(self, "t0", time.time())) and None)
    monkeypatch.setattr(E, "prices", lambda cl, zones, hours: {z: [50.0] * len(hours) for z in zones if z in ("DE-LU", "PL", "MK")})
    off = [1000.0] * 24
    monkeypatch.setattr(E, "system", lambda cl, hours: {
        "de": {"series": {"wind_offshore": off, "load": off}, "zones": ["DE-LU"]},
        "nl": {"series": {"wind_offshore": off}, "zones": ["NL"], "lag_h": 6}})   # late: not used for the model check
    monkeypatch.setattr(gbie_live, "fetch", lambda hours: (_ for _ in ()).throw(RuntimeError("offline")))
    farms = [{"id": 1, "c": "Germany", "lon": 7.0, "n": "x"}, {"id": 2, "c": "Denmark", "lon": 12.0, "n": "y"}]
    hrs = [datetime.fromtimestamp(h, timezone.utc).strftime("%Y-%m-%dT%H:00Z") for h in HOURS]
    mk = market.build(farms, hrs)
    assert set(mk["prices"]) == {"DE-LU", "PL", "MK"} and mk["price_source"]["PL"] == "entsoe"
    assert mk["farm_zone"] == {"1": "DE-LU", "2": "DK2"}
    assert "DE-LU" in mk["core_zones"] and mk["restricted_zones"] == []
    assert mk["actual_offshore"] == {"de": off}
    assert mk["source"].startswith("ENTSO-E") and "Energy-Charts" not in str(mk)


def test_time_budget_keeps_last_data(fake, monkeypatch):
    E.system(E.Client(), HOURS)
    cache = E._load_cache()
    for cc in cache["system"]:
        cache["system"][cc]["t"] = 0   # stale: would be fetched again
    E._save_cache(cache)
    monkeypatch.setattr(E.Client, "MAX_WALL_S", -1)  # budget already used
    cl = E.Client()
    out = E.system(cl, HOURS)
    assert set(out) == {"dk", "pl"} and out["dk"]["series"]["wind_offshore"][0] == 1000.0
    assert cl.errors and cl.errors[0].startswith("skipped")
    assert "lag_h" not in out["dk"]  # same hour: not late
    out2 = E.system(cl, [h + 7200 for h in HOURS])  # two hours later, still no budget
    assert out2["dk"]["lag_h"] == 2
