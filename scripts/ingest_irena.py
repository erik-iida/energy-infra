"""Turn the IRENA Renewable Energy Statistics workbook (IRENA_Stats_Tool_*.xlsb, sheet "Data") into a small tidy CSV.

    python scripts/ingest_irena.py path/to/IRENA_Stats_Tool_v2.xlsb [--from-year 2015]

Writes data/ref/irena_capacity.csv  (iso3, country, year, cls, cap_mw, gen_gwh) and data/ref/irena_meta.json.
`cls` groups IRENA's technologies into the classes the ENTSO-E generation types map to (newsletter/fundamentals.py):
solar, wind_onshore, wind_offshore, hydro (run-of-river + reservoir), pumped, nuclear, coal, gas, oil, fossil_nes,
bio, geothermal, other. Several countries report all fossil capacity as "fossil_nes" (no split).
Installed capacity is year-end; generation lags one year more. Heat rows and off-grid-only series are dropped from
capacity only where they carry no electricity capacity. Needs pyxlsb (pip install pyxlsb); the 18 MB workbook itself
is not committed, only this extract.
Licence: IRENA material may be freely used with attribution (c) IRENA and the year of the edition.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "ref"
COLS = ["region", "subregion", "country", "iso3", "m49", "re", "group", "tech", "subtech", "producer", "year",
        "gen_gwh", "cap_mw", "heat_tj", "flows", "sdg7a1", "sdg7b1"]

CLS = {
    "Solar photovoltaic": "solar", "Solar thermal energy": "solar", "Solar energy": "solar",
    "Onshore wind energy": "wind_onshore", "Offshore wind energy": "wind_offshore",
    "Renewable hydropower": "hydro", "Mixed Hydro Plants": "hydro", "Pumped storage": "pumped",
    "Nuclear": "nuclear", "Coal and peat": "coal", "Natural gas": "gas", "Oil": "oil",
    "Fossil fuels n.e.s.": "fossil_nes",
    "Solid biofuels": "bio", "Biogas": "bio", "Liquid biofuels": "bio", "Renewable municipal waste": "bio",
    "Geothermal energy": "geothermal",
}


def read_data(path: str) -> pd.DataFrame:
    from pyxlsb import open_workbook
    rows = []
    with open_workbook(path) as wb, wb.get_sheet("Data") as sh:
        for i, r in enumerate(sh.rows()):
            if i < 8:  # filters and header
                continue
            v = [c.v for c in r][:17]
            if v[0] is None and v[2] is None:
                continue
            rows.append(v)
    return pd.DataFrame(rows, columns=COLS)


def tidy(df: pd.DataFrame, from_year: int) -> pd.DataFrame:
    d = df[df["year"].notna() & (df["year"] >= from_year)].copy()
    d["year"] = d["year"].astype(int)
    d["cls"] = d["tech"].map(CLS).fillna("other")
    d = d[d["cap_mw"].notna() | d["gen_gwh"].notna()]
    d = d[d["producer"].isin(["On-grid electricity", "Off-grid electricity", "All types"])]
    g = d.groupby(["iso3", "country", "year", "cls"], as_index=False).agg(
        cap_mw=("cap_mw", lambda s: s.sum(min_count=1)), gen_gwh=("gen_gwh", lambda s: s.sum(min_count=1)))
    return g.round({"cap_mw": 3, "gen_gwh": 3}).sort_values(["iso3", "year", "cls"])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsb")
    ap.add_argument("--from-year", type=int, default=2015)
    a = ap.parse_args(argv)
    t = tidy(read_data(a.xlsb), a.from_year)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "irena_capacity.csv", index=False)
    meta = {"source": "IRENA Renewable Energy Statistics (statistics tool workbook, sheet Data)",
            "licence": "free use with attribution: (c) IRENA", "file": Path(a.xlsb).name,
            "capacity_last_year": int(t.loc[t["cap_mw"].notna(), "year"].max()),
            "generation_last_year": int(t.loc[t["gen_gwh"].notna(), "year"].max()),
            "countries": int(t["iso3"].nunique()), "rows": int(len(t))}
    (OUT / "irena_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta), file=sys.stderr)


if __name__ == "__main__":
    main()
