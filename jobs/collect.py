"""Collect: public sources -> the data store (Parquet, monthly files) or data/static/ (committed page inputs).

    python -m jobs.collect entsoe [daily|recent|backfill|auto|probe]   ENTSO-E prices, generation, load, flows -> store
    python -m jobs.collect gb-ie / gb-hist / gb-units [mode]           Elexon, EirGrid, NESO, REPD -> store
    python -m jobs.collect capture | gas | gie | grid | bathymetry | osm-world | global-turbines | extra-turbines
                                                                      -> data/static/ (bot workflows commit the result)
    python -m jobs.collect site                                         rebuild data/static/site.json from the raw turbine data
"""
import sys

from . import _run

TABLE = {
    "entsoe": ("ENTSO-E raw history into the store (collector.collect; mode: daily, recent, backfill, auto, probe)",
               lambda a: _run.module("collector.collect", a)),
    "gb-ie": ("Great Britain + Ireland (Elexon / EirGrid) into the store (collector.gbie)", lambda a: _run.module("collector.gbie", a)),
    "gb-hist": ("NESO history into the store (collector.gbhist)", lambda a: _run.module("collector.gbhist", a)),
    "gb-units": ("Elexon per-unit output + REPD sites into the store (collector.gbunits)", lambda a: _run.module("collector.gbunits", a)),
    "capture": ("capture prices per technology -> data/static/capture.json (+ data/fx.json)", lambda a: _run.script("fetch_capture", a)),
    "gas": ("ENTSOG gas flows -> data/static/gas.json", lambda a: _run.script("fetch_gas", a)),
    "gie": ("GIE storage + LNG -> data/static/gie.json (needs GIE_KEY)", lambda a: _run.script("fetch_gie", a)),
    "grid": ("PyPSA-Eur HV grid -> data/static/grid.json", lambda a: _run.script("fetch_grid", a)),
    "bathymetry": ("EMODnet depth grid -> data/static/bathy.*", lambda a: _run.script("fetch_bathymetry", a)),
    "osm-world": ("OpenStreetMap turbines outside Europe -> data/raw/osm (then `site`)", lambda a: _run.script("fetch_osm_world", a)),
    "global-turbines": ("Global offshore turbine dataset -> data/raw", lambda a: _run.script("fetch_global_turbines", a)),
    "extra-turbines": ("extra turbines from OpenStreetMap -> data/raw (then `site`)", lambda a: _run.script("fetch_osm_turbines", a)),
    "site": ("data/static/site.json from the raw turbine data (scripts/build_site.py)", lambda a: _run.script("build_site", a)),
}

if __name__ == "__main__":
    raise SystemExit(_run.dispatch("jobs.collect", TABLE, sys.argv[1:]))
