"""GB unit output, registry selection, REPD parsing and BM-unit matching from Elexon / REPD-shaped data (no network)."""
from datetime import datetime, timezone

import pandas as pd

from collector import gbunits as U

REG = [
    {"elexonBmUnit": "T_ABRBO-1", "nationalGridBmUnit": "ABRBO-1", "bmUnitName": "ABRBO-1", "leadPartyName": "Aberdeen Offshore Wind Farm",
     "fuelType": "WIND", "bmUnitType": "T", "generationCapacity": "99.000"},
    {"elexonBmUnit": "E_ABRTW-1", "nationalGridBmUnit": "ABRTW-1", "bmUnitName": "Auchrobert Wind Farm", "leadPartyName": "Npower Commercial Gas Limited",
     "fuelType": "WIND", "bmUnitType": "E", "generationCapacity": "36.000"},
    {"elexonBmUnit": "T_CRUA-1", "nationalGridBmUnit": "CRUA-1", "bmUnitName": "T_CRUA-1", "leadPartyName": "Drax Pumped Storage Limited",
     "fuelType": "PS", "bmUnitType": "T", "generationCapacity": "123.000"},
    {"elexonBmUnit": "E_BRGG-1", "nationalGridBmUnit": "BRGG-1", "bmUnitName": "Glanford Brigg", "leadPartyName": "CBS ENERGY STORAGE ASSETS LTD",
     "fuelType": None, "bmUnitType": "E", "generationCapacity": "50.000"},
    {"elexonBmUnit": "I_IEG-FRAN1", "nationalGridBmUnit": "I_IEG-FRAN1", "bmUnitName": "IFA", "leadPartyName": "x", "fuelType": "INTFR",
     "bmUnitType": "I", "generationCapacity": "2000"},
    {"elexonBmUnit": "V__PHABI010", "nationalGridBmUnit": "AG-HAB01P", "bmUnitName": "Boat of Garten", "leadPartyName": "Habitat", "fuelType": None,
     "bmUnitType": "V", "generationCapacity": "0.000"},
    {"elexonBmUnit": "2__AALAB000", "nationalGridBmUnit": None, "bmUnitName": "2__AALAB000", "leadPartyName": "Supplier", "fuelType": None,
     "bmUnitType": "S", "generationCapacity": "0"},
]
REPD_CSV = """Ref ID,Site Name,Operator (or Applicant),Technology Type,Storage Type,Installed Capacity (MWelec),Development Status (short),Country,Region,No. of Turbines,Turbine Capacity (MW),CfD Allocation Round,Offshore Wind Round,X-coordinate,Y-coordinate
1,Aberdeen Offshore Wind Farm,Vattenfall,Wind Offshore,,99,Operational,Scotland,Offshore,11,"9",,,,
2,Auchrobert Wind Farm,Someone,Wind Onshore,,36,Operational,Scotland,Scotland,"12","3",,,284000,640000
3,Glanford Brigg Battery,CBS,Battery,Li-ion,50,Operational,England,Yorkshire,,,,,500000,410000
4,Refused Farm,x,Wind Onshore,,10,Application Refused,England,x,,,,,1,1
"""


def test_select_and_registry(monkeypatch):
    class R:
        def json(self):
            return REG
    monkeypatch.setattr(U, "_get", lambda *a, **k: R())
    reg = U.fetch_registry()
    assert reg.loc[reg.bm_unit == "T_CRUA-1", "capacity_mw"].iloc[0] == 123
    sel = U.select_units(reg)
    # wind, pumped storage and the 50 MW battery; not the interconnector, the 0 MW virtual unit or the supplier unit
    assert set(sel["bm_unit"]) == {"T_ABRBO-1", "E_ABRTW-1", "T_CRUA-1", "E_BRGG-1"}


def test_repd_and_matching():
    repd = U.parse_repd(REPD_CSV)
    assert list(repd["ref"]) == ["1", "2", "3"]  # refused site dropped
    s = repd.set_index("ref")
    assert 55 < s.loc["2", "lat"] < 58 and -6 < s.loc["2", "lon"] < -2  # BNG -> WGS84
    assert pd.isna(s.loc["1", "lat"])  # no coordinates in the extract
    reg = pd.DataFrame([{"bm_unit": r["elexonBmUnit"], "ngc_id": r["nationalGridBmUnit"], "name": r["bmUnitName"], "party": r["leadPartyName"],
                         "fuel": r["fuelType"], "unit_type": r["bmUnitType"], "capacity_mw": float(r["generationCapacity"])} for r in REG])
    m = U.match_units(U.select_units(reg), repd, overrides={"T_CRUA-1": ""}).set_index("bm_unit")
    assert m.loc["T_ABRBO-1", "repd_ref"] == "1"                  # via the lead party name
    assert m.loc["E_ABRTW-1", "repd_ref"] == "2" and m.loc["E_ABRTW-1", "lat"] > 55  # via the unit name, supplier party ignored
    assert m.loc["E_BRGG-1", "repd_ref"] == "3"                    # battery matched on the battery site only
    assert m.loc["T_CRUA-1", "repd_ref"] is None                   # no pumped storage site in the sample
    # numbers must agree: Hornsea 1 is not Hornsea 3; an override fixes a miss and "" blocks a wrong match
    r2 = pd.DataFrame({"ref": ["10", "11"], "name": ["Hornsea 3", "Hornsea 1 - Heron"], "tech": ["Wind Offshore"] * 2, "mw": [2955.0, 1218.0],
                       "lat": [53.0, 54.0], "lon": [1.0, 2.0]})
    u2 = pd.DataFrame([{"bm_unit": "T_HOWAO-1", "name": "HORNSEA_1A", "party": "x", "fuel": "WIND", "unit_type": "T", "capacity_mw": 400.0},
                       {"bm_unit": "T_X-1", "name": "Nothing Alike", "party": "y", "fuel": "WIND", "unit_type": "T", "capacity_mw": 50.0}])
    m2 = U.match_units(u2, r2, overrides={"T_X-1": "10"}).set_index("bm_unit")
    assert m2.loc["T_HOWAO-1", "repd_ref"] is None  # not Hornsea 3 (a long REPD name for Hornsea 1 is left to the overrides)
    assert m2.loc["T_X-1", "repd_ref"] == "10" and m2.loc["T_X-1", "match_score"] == 1.0


def test_b1610_frame(monkeypatch):
    rows = [{"bmUnit": "T_ABRBO-1", "halfHourEndTime": "2026-09-25T05:00:00", "quantity": 14.7, "settlementRunType": "II"},
            {"bmUnit": "T_ABRBO-1", "halfHourEndTime": "2026-09-25T05:30:00", "quantity": -0.5, "settlementRunType": "II"},
            {"bmUnit": "T_ABRBO-1", "halfHourEndTime": "2026-09-25T06:00:00", "quantity": None, "settlementRunType": "II"}]

    class R:
        def json(self):
            return rows
    seen = []
    monkeypatch.setattr(U, "_get", lambda url, params, **k: (seen.append(params), R())[1])
    a, b = datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc)
    f = U.unit_frame(["T_ABRBO-1"], a, b, datetime.now(timezone.utc))
    assert seen[0]["bmUnit"] == ["T_ABRBO-1"]
    assert list(f["mw"]) == [29.4, -1.0]                           # MWh per half hour x 2
    assert list(f["ts"]) == [pd.Timestamp("2026-09-25T04:30Z"), pd.Timestamp("2026-09-25T05:00Z")]  # end time - 30 min, UTC
    assert set(f.columns) >= {"bm_unit", "ts", "mw", "run", "res_min", "fetched"}
