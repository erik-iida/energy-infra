# European offshore wake monitor

Live, wake-aware output of Europe's offshore wind farms. A map drills down from Europe to a
country to a farm, with the turbine layout and a wake-deficit heatmap. A Compare tab shows every
country and farm over the last 24 h plus a 24 h forecast.

```
forecast (Open-Meteo)  →  hub-height wind per farm  →  PyWake (4 wake models)  →  web/data/feed.json  →  web page
```

## Folder layout

| Path | What it is |
|---|---|
| `data/raw/eww/` | Open European offshore wind turbine database (EuroWindWakes, version 2026-01-27): one row per turbine, plus power and Ct curves per turbine type |
| `data/raw/European_offshore_wind_farm_outline.geojson` | Farm and zone outlines (own compilation, WGS84) |
| `scripts/build_site.py` | Turns the GeoJSONs into `web/data/site.json` (run again when the data changes) |
| `scripts/windy_test.py` | One-off check of your Windy key and which models it allows |
| `pipeline/` | The hourly job: `config.py` (settings), `sources.py` (forecasts), `budget.py` (call cap), `wake.py` (PyWake), `run.py` (main) |
| `web/` | The static site: `index.html` + `data/site.json` + `data/feed.json` |
| `state/` | Forecast cache, 24 h history, daily call counter (created by the pipeline) |
| `setup/hourly.yml` | The GitHub Actions workflow. Move it to `.github/workflows/hourly.yml` before pushing (see below) |

## Run it locally

Use any of your Python environments (3.10+):

```powershell
pip install -r requirements.txt
python -m pipeline.run                # Open-Meteo forecast (free, no key); takes ~30 s
python -m http.server 8000 -d web     # then open http://localhost:8000
```

The page has to be served over http (as above), not opened as a file, because it loads the JSON files.
`python scripts/build_site.py` is only needed if the files in `data/raw` change.

### Forecast sources (`WM_SOURCE`)

| Source | Cost | Notes |
|---|---|---|
| `openmeteo` (default) | Free for non-commercial use | Under 10 000 calls/day. ECMWF models use Open-Meteo's ECMWF endpoint with 100 m wind; others give 120 m (80 m fallback). Pick the model with `WM_OPENMETEO_MODEL`: `ecmwf_ifs` (default, HRES 9 km), `ecmwf_ifs_025`, `icon_eu`, `icon_seamless`. Also returns the past 24 h, so the history is full from the first run. Credit "Weather data by Open-Meteo.com" (CC BY 4.0) is shown on the page. |
| `windy` | Free key = shuffled test data, 500 calls/day. Professional = €990/year | No ECMWF on any tier. Kept for completeness; `scripts/windy_test.py` checks a key. |
| `ecmwf` | Free | Raw ECMWF open-data GRIB (100 m). `pip install -r requirements-ecmwf.txt`. Written but not yet run against the live server. |
| `synthetic` | Free, offline | Made-up weather for testing without network. |

```powershell
$env:WM_OPENMETEO_MODEL = "icon_eu"   # example: switch model
python -m pipeline.run --source openmeteo
```

## Market data (Energy-Charts)

The pipeline also pulls from the [Energy-Charts API](https://api.energy-charts.info) (Fraunhofer ISE, no key):

- **Day-ahead prices** per bidding zone for the last 24 h and the next 24 h (tomorrow's auction is published
  around midday). Farms map to zones by country; Denmark splits at the Great Belt (Anholt → DK1, Sprogø assumed DK2).
- **Actual offshore generation** per country for the last 24 h, to check the model against reality.
- **Monthly history** (`web/data/market_history.json`) of baseload price, offshore capture price, capture rate and
  output at negative prices for DE-LU, NL, BE, DK (DK1/DK2 blended by installed MW) and FR, built from actual
  national offshore output. It backfills 3 area-months per hourly run, so two years take a day or two.

The page's **Market** tab shows capture price and capture rate per zone (modelled, last and next 24 h), revenue lost
to wakes, the model check and the monthly history. The Compare table gets capture price and wake cost per farm.

Licences: every Energy-Charts response states its licence. Only CC BY data is published; zones marked "private
and internal use" are listed as restricted and left out. The API rate-limits bursts, so calls are spaced 3 s apart, retried once
after 30 s, and cached (roughly 15 calls per hourly run). UK farms have no market numbers: this source has no GB day-ahead price.
Switch it off with `WM_MARKET=0`. Offline test: `python -m tests.mock_market`.

## API budget

- Farms in the same 0.1° cell share one forecast: 128 farms → about 115 locations.
- Open-Meteo takes 50 locations per request, so a refresh is 3 HTTP requests. The budget counter
  counts every location as a call to be safe (115 per refresh).
- Forecasts are only refetched when the cache is older than `WM_REFRESH_HOURS` (default 6 h, about as
  often as the models update). The hourly runs in between make **no calls**. About 460 counted calls a day.
- `state/budget_<source>.json` counts calls per UTC day. At `WM_DAILY_CALL_CAP` (default 2000) the job stops
  calling and keeps using the cached forecast.
- A failed request is logged and skipped. The workflow never runs two copies at once.

## Put it online (GitHub Pages, free)

0. Move the workflow into place (it couldn't be written there directly):
   ```powershell
   mkdir .github\workflows
   move setup\hourly.yml .github\workflows\hourly.yml
   ```
1. Create a new **public** repository (Pages from a private repo needs a paid GitHub plan) on GitHub and push this folder to it:
   ```powershell
   git init
   git add .
   git commit -m "Wake monitor"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. In the repo: **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Secrets and variables → Actions**:
   - Nothing is required for Open-Meteo.
   - Optional variables: `WM_SOURCE` (default `openmeteo`), `WM_OPENMETEO_MODEL`, `WM_DAILY_CALL_CAP`.
   - Only if you use Windy: secret `WINDY_KEY` (never commit the key anywhere).
4. **Actions → hourly-feed → Run workflow** to test it once. After that it runs every hour at :07 and
   the site is at `https://<you>.github.io/<repo>/`.

Notes: the site is public. Open-Meteo's free tier is for non-commercial use and needs the credit line,
which the page shows in the sidebar footer.
Scheduled Actions can run a few minutes late, and GitHub pauses schedules in repos with no activity
for 60 days.

## Model notes

- **Wake models (PyWake 2.6):** Jensen/NOJ (k = 0.04), Bastankhah & Porté-Agel 2014 (k = 0.0324555, PyWake default),
  Niayifar & Porté-Agel 2016, TurbOPark (Nygaard 2022). Ambient TI 6 %.
- **Power and thrust curves per turbine type** come with the turbine database (35 types). They are PyWake
  generic curves (cut-in 4 m/s, cut-out 25 m/s, TI 5 %), not manufacturer curves. Mixed farms keep each
  turbine's own type. Farms without turbine data use a cubic curve on their stated capacity.
- **Hub height:** log law with z0 = 0.0002 m from the forecast's reference height
  (100 m for Open-Meteo ECMWF, 120/80 m for other Open-Meteo models, 10 m for Windy surface wind, 100 m for ECMWF open data).
- **Single direction:** wake losses are computed for the exact forecast direction. When the wind lines
  up with a row (Horns Rev I at 270°) this gives larger losses than measured 10-minute averages. Averaging
  over a few degrees of direction uncertainty is the next improvement.
- **No farm-to-farm wakes** yet; each farm is modelled alone.
- **Farms without turbine positions** (5 of 127: Iles d'Yeu et de Noirmoutier, WindFloat Atlantic, BIMEP,
  Bockstigen, Motriku) use a free-stream curve on their stated capacity with a flat 10 % wake loss (italics).
- **Matching turbines to outlines:** the turbine database has no link to the outline file, so turbines are
  matched by location (inside a polygon, else the nearest within 2 km, else their farm's majority polygon, else
  a hull around the turbines). One farm = one wind farm of the turbine database.

## Feed format (`web/data/feed.json`)

```json
{
  "version": 1, "source": "openmeteo", "nwp_model": "ecmwf_ifs", "generated": "2026-09-30T21:19:44+00:00",
  "models": {"jensen": "...", "bastankhah": "...", "niayifar": "...", "turbopark": "...", "nowake": "No wake"},
  "hours":    ["...24 hourly UTC stamps, the last one is now"],
  "fc_hours": ["...next 24 hours"],
  "farms": {
    "<wind_farm_id>": {
      "U": [24 hub-height m/s], "dir": [24 deg], "P": {"<model>": [24 MW]},
      "fU": [24], "fdir": [24], "fP": {"<model>": [24]}
    }
  }
}
```

Missing hours are `null`. The page falls back to synthetic wind and in-browser models if there is no feed.

## Disclaimer

This is a personal, non-commercial research and learning project. All production, capacity factor and
wake-loss figures are **model estimates** from public weather forecasts, generic turbine curves and
simplified wake models. They are not measured data, not official figures from any wind farm owner,
operator or TSO, and are known to be wrong in places. Nothing here is investment, trading or engineering
advice. The project is not affiliated with or endorsed by any company, wind farm, or data provider named
in it.

## Data sources and credits

| What | Source | Licence |
|---|---|---|
| Weather forecasts | [Open-Meteo](https://open-meteo.com/) (ECMWF IFS and other models) | CC BY 4.0, free for non-commercial use |
| Turbine positions, types and power/Ct curves | "Open European offshore wind turbine database" (version 2026-01-27), Fischereit, Vollmer & Hansen, [doi:10.5281/zenodo.17311571](https://doi.org/10.5281/zenodo.17311571). © Contributors to the EuroWindWakes European Offshore Dataset; includes data from © OpenStreetMap contributors and EMODnet | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| Farm and zone outlines | Compiled by Erik Iida; geometry partly based on [EMODnet Human Activities](https://emodnet.ec.europa.eu/en/human-activities) | Compilation: all rights reserved. EMODnet data: generally CC BY 4.0 |
| Power prices and actual generation | [Energy-Charts](https://www.energy-charts.info), Fraunhofer ISE; prices from Bundesnetzagentur \| SMARD.de | CC BY 4.0 (per response; restricted zones not published) |
| Coastlines | [Natural Earth](https://www.naturalearthdata.com/) | Public domain |
| Wake models | [PyWake](https://gitlab.windenergy.dtu.dk/TOPFARM/PyWake), DTU Wind Energy | MIT |

## Licence

- **Code:** copyright © 2026 Erik Iida, all rights reserved. Public to view, not licensed for reuse. See `LICENSE`.
- **Farm and zone outlines** (`data/raw/European_offshore_wind_farm_outline.geojson`): your own compilation,
  all rights reserved, with credit to EMODnet for the geometry it is based on.
- **Data derived from the offshore turbine database** (`data/raw/European_offshore_wind_turbines.geojson`
  and the turbine data in `web/data/site.json`): ODbL 1.0, as its licence requires. Anyone may reuse it
  under the ODbL.
- Other third-party data and software keep their own licences (table above).
