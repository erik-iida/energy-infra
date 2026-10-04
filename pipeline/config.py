"""Settings for the hourly pipeline. Environment variables override the defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Where files live (spec 3 step 3: source and build output are separate folders).
#   web/          the page as written by hand (index.html, css/, js/). Nothing generates files here.
#   data/static/  slow inputs the page reads, committed to git and refreshed by bot workflows
#                 (site.json, zones.json, grid.json, capture.json, gas.json, gie.json, bathy.*)
#   build/        what one run generates, never committed: data/feed.json, data/meta.json, data/browse/,
#                 data/newsletter/, config.js. The hourly job uploads it as the `built-data` artifact.
#   dist/         the assembled site = web/ + data/static/ (as data/) + build/ (as data/ and config.js);
#                 scripts/build_dist.py makes it, the deploy publishes it. Never committed.
WEB = ROOT / "web"
DATA_STATIC = ROOT / "data" / "static"
BUILD = ROOT / "build"
BUILD_DATA = BUILD / "data"
DIST = ROOT / "dist"
SITE_JSON = DATA_STATIC / "site.json"
FEED_JSON = BUILD_DATA / "feed.json"
STATE_DIR = ROOT / "state"  # forecast cache, 24 h history, call budget (Actions cache, not git)


def static_file(name: str) -> Path:
    """A committed page input (data/static/<name>)."""
    return DATA_STATIC / name


def build_file(*parts: str) -> Path:
    """A generated page file (build/data/<parts>), parent folder created."""
    p = BUILD_DATA.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

# Forecast source:
#   "openmeteo"  Open-Meteo API: free for non-commercial use (<10 000 calls/day, credit "Weather data by
#                Open-Meteo.com", CC BY 4.0). ECMWF (100 m wind) or ICON-EU and others (120/80 m).
#   "windy"      Windy Point Forecast API (the free testing key returns shuffled data; Professional is paid)
#   "ecmwf"      ECMWF open data GRIB download (100 m wind)
#   "synthetic"  made-up weather for offline testing
SOURCE = os.environ.get("WM_SOURCE", "openmeteo")
OPENMETEO_MODEL = os.environ.get("WM_OPENMETEO_MODEL", "ecmwf_ifs")  # ECMWF HRES 9 km, 100 m wind. Or icon_eu, icon_seamless
WINDY_KEY = os.environ.get("WINDY_KEY", "")
WINDY_MODEL = os.environ.get("WM_WINDY_MODEL", "iconEu")  # run windy_test.py to see which models your key allows

# Call budget. Your hard ceiling is 10 000 per day; the pipeline stops well before it.
DAILY_CALL_CAP = int(os.environ.get("WM_DAILY_CALL_CAP", "3000"))  # Open-Meteo free tier: 10 000/day
REFRESH_HOURS = float(os.environ.get("WM_REFRESH_HOURS", "6"))  # refetch a forecast only when older than this
CELL_DEG = 0.1  # farms inside the same 0.1 deg cell share one forecast call (128 farms -> ~115 cells)

# Physics
Z0 = 0.0002  # offshore roughness length [m] for the log-law shear to hub height
TI = 0.06    # ambient turbulence intensity offshore
TI_ONSHORE = 0.10  # onshore demo farms (flat terrain, no forest/stability effects)
NO_LAYOUT_EFFICIENCY = 0.90  # farms without turbine positions: free-stream power x this
GENERIC_RATED_SPEED = 11.5   # rated wind speed for farms without rotor data [m/s]
CUT_IN, CUT_OUT = 3.0, 25.0

# Wake models run by PyWake (key -> label). "nowake" is always added.
WAKE_MODELS = {
    "jensen": "Jensen (NOJ)",                        # k = 0.04, area-overlap rotor average, squared sum
    "bastankhah": "Bastankhah & Porté-Agel 2014",   # k = 0.0324555, linear sum on effective wind speed
    "niayifar": "Niayifar & Porté-Agel 2016",       # TI-dependent wake growth, Crespo-Hernandez turbulence
    "turbopark": "TurbOPark (Nygaard 2022)",
}

# Power-market data from Energy-Charts (prices, actual generation). Set WM_MARKET=0 to switch off.
MARKET = os.environ.get("WM_MARKET", "1") != "0"

HISTORY_HOURS = 24
FORECAST_HOURS = 24
