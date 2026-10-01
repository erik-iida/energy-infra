"""Settings for the hourly pipeline. Environment variables override the defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_JSON = ROOT / "web" / "data" / "site.json"
FEED_JSON = ROOT / "web" / "data" / "feed.json"
STATE_DIR = ROOT / "state"  # forecast cache, 24 h history, call budget (committed by the workflow)

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
DAILY_CALL_CAP = int(os.environ.get("WM_DAILY_CALL_CAP", "2000"))
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
