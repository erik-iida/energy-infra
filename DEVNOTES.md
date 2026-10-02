# Development notes

Handover notes for whoever (human or Claude) picks this up next. Keep them current.

## How it runs
- GitHub Actions (`.github/workflows/hourly.yml`) runs `python -m pipeline.run` hourly at :07, on every
  push to `main`, and on "Run workflow". It then deploys `web/` to GitHub Pages.
- `state/` (forecast cache, 24 h history, call counter) lives in the Actions cache, not in git.
- Default forecast source: Open-Meteo, model `ecmwf_ifs` (HRES 9 km) via the /v1/ecmwf endpoint for 100 m wind
  (falls back to /v1/forecast `ecmwf_ifs025`, 10 m wind, if that fails), free
  non-commercial tier (<10 000 calls/day). About 3 requests / 115 locations per refresh, refresh every 6 h.
- PyWake 2.6: Jensen_1983 (k 0.04), Bastankhah_PorteAgel_2014 (k 0.0324555), Niayifar 2016, TurbOPark (Nygaard 2022), plus no-wake.
- The in-browser Jensen and Bastankhah (map heatmap + what-if) re-implement PyWake's exact formulas and defaults
  (ct2a_madsen + area-overlap + squared sum for NOJ; ceps 0.2, ctlim 0.899, ct2a_mom1d, linear sum on effective
  ws for Bastankhah). Verified within 0.12 % of farm power against PyWake on 30 farm/wind cases. Keep them in sync
  if pipeline/wake.py changes. Model names are identical in both places.
- Web page is plain HTML/JS in `web/index.html` (no build step). It loads `data/site.json` + `data/feed.json`.
  Map heatmap uses in-browser Jensen/Gaussian; Compare tab uses the PyWake numbers from the feed.

## Market module (pipeline/market.py)
- Energy-Charts v2 API. Prices are 15-min (PT15M) since the 15-min day-ahead market; averaged to UTC hours.
- Licence gating on every response ("CC BY" in `license`); restricted zones go to `restricted_zones`, not published.
- Capture price = Σ P·price / Σ P. Capture rate = capture / baseload. Wake cost = Σ (P_nowake − P_model)·price,
  farms with layouts only. The page computes these from feed.json for the selected wake model.
- Monthly history uses ACTUAL national offshore output (not the model) × zone price; DK blends DK1/DK2 by
  installed MW from site.json. Backfill 3 (area, month) cells per run; current and previous month refreshed daily.
- The API returns HTTP 429 on bursts and sometimes drops large monthly downloads: 3 s spacing, one retry after
  30 s (429/5xx/connection errors), then skip; the cell is retried on a later run. Market failure never blocks the feed.
- No GB price in Energy-Charts → UK farms lack market numbers (Elexon/N2EX would be the source).

## Web page
- Wake fields are drawn on a wind-aligned grid (D/10 across, D/3 along), transparent below 0.8 % deficit,
  viridis 0-30 % with a legend.
- Map is one pan/zoom canvas (drag, wheel, pinch, double-click, +/− buttons). Projection: equirectangular around
  the view centre. Level of detail by the turbine layout's on-screen radius: < 30 px ring glyph (outer ring =
  capacity, filled radius = capacity factor), ≥ 30 px turbines, ≥ 90 px wake heatmap (max 4 farms, cached per
  farm/model/wind so panning is cheap). Selecting a farm or country flies to it.
- System tab (SYSTEM_COUNTRIES in market.py): mix in 8 groups with validated colour order (nuclear magenta, coal
  violet, gas orange, hydro aqua, biomass & other red, wind offshore blue, wind onshore green, solar yellow),
  load line, prices, flows (import blue / export red).
- Comparison charts (Market: day-ahead price per zone, last 24 h / tomorrow; System: offshore share of generation
  or of load). With 10-15 series a colour per line can't be told apart, so lines are neutral grey, identified by
  a round flag + label at the line end (labels nudged apart), and the line under the cursor is highlighted;
  the tooltip ranks all series at that hour. Shared code: FLAGS / flagSVG / cmpRender in index.html.
- Bathymetry underlay: a coarse EMODnet depth grid (1.25', 20W-32E, 34-66N) fetched by
  scripts/fetch_bathymetry.py (bathymetry workflow, runs when the script changes) into web/data/bathy.png
  (8-bit: metres up to 200, then 100 m steps, 255 = land) + bathy.json. The browser colours it with a sequential
  blue ramp over 0..slider depth (default 60 m, deeper = darkest), so the scale suits fixed-bottom depths. When
  zoomed in, EMODnet WMS emodnet:contours is drawn on top. If the grid is missing the page falls back to the
  WMS emodnet:mean image. Plate carrée maps linearly to the map projection. CC BY 4.0.
- Wake heat uses viridis (user's choice), alpha still rising from 0.8 % deficit.
- Farms in site.json but not yet in feed.json (between a site update and the next hourly run) are hidden
  instead of breaking the page.

## Decisions so far
- Windy dropped: free key returns shuffled test data (500 calls/day), Professional is €990/yr and has no ECMWF.
- Turbines, types and power/Ct curves from the EuroWindWakes database (2026-01-27, 6 544 turbines, 122 farms,
  35 types). site.json has `types` (with curves) and per farm `ti` (one index, or one per turbine for the 4 mixed
  farms). PyWake uses WindTurbines with `type=`; the browser interpolates the same tables, padded with zero
  power/Ct outside cut-in/cut-out. Browser vs PyWake verified to 0.00 % on 30 cases incl. mixed farms.
- Farm view shows nearest-neighbour spacing (min / mean / max, in each turbine's own rotor diameters).
- Farms without turbine positions (5 of 127) use free-stream power × 0.9.
- Outline capacities in the source file are unreliable (e.g. every Hornsea 2 phase lists 1 386 MW);
  installed MW uses turbine count × rated power where turbines exist.
- Wind and output are never on a shared dual axis; separate charts.
- The user's PC folder is on OneDrive: don't create virtual environments there.

## World coverage (Oct 2026)
- Farms outside Europe come from the Global offshore wind turbine dataset (Zhang et al. 2021, CC0, figshare
  13280252): 12 338 Sentinel-1 turbine detections to 2021 with 4C project names/capacities. build_site.py uses
  the non-European ones (Europe stays on EuroWindWakes): 6 116 turbines after dropping 87 double detections,
  152 farms (China 122, Vietnam 22, Taiwan 4, South Korea 2, US 2).
- Farms = project name, split into sites by 3 km single linkage; 1-3 stray turbines join the nearest group.
- Taiwan's farms are labelled China in the source; reassigned by position (south of 25N from 119.6E, or east of
  120.5E). Name fields are cp1252 (the unused lat/lon text columns hold GBK degree signs).
- Turbine type unknown except KNOWN_TYPES (Block Island, CVOW, Formosa 1, Greater Changhua, Korean demos).
  Otherwise MW = project MW / turbines detected when 2-8.5 MW, else a regional default; rotor from 330 W/m2,
  hub = D/2 + 25 m, generic power/Ct curve. Farms carry `est` (the basis), `src: "gowt"`, `rg` (region); the
  page shows an "Estimated turbines" note. Project grouping in the source is loose (e.g. 170 turbines under one
  Rudong intertidal name), so installed MW outside Europe is indicative. Farms built after 2021 are missing.
- Page hierarchy World > Region > Country > Farm; S.c is null, a region or a country; inC(x, c) filters.
  Market/System tabs stay European (Energy-Charts).
- Land: Natural Earth 10m, detailed (0.01 deg Europe, 0.02 deg around other farms) inside `dbox`, 0.1 deg
  elsewhere, cut into 20-degree tiles (`tile`) so the page culls off-screen land. The page strokes coastlines
  from the polygons except along tile cuts and dbox borders, and paints over those cuts in land colour
  (canvas anti-aliasing seams). Paths skip vertices < 1.2 px apart (except on tile cuts).
- Depth grid only shows when the view spans < 80 deg longitude and is centred on it.
- Hourly run: ~280 farms, ~30 s more PyWake time; Open-Meteo ~230 locations per 6 h (< 2000/day cap).

## OpenStreetMap layer (Oct 2026)
- scripts/fetch_osm_world.py (osm-world workflow, every 2 h until complete, resumable via `done` in
  data/raw/osm/osm_wind.json): wind generators in ~20 small coastal boxes outside Europe (positions first, keep
  those outside Natural Earth land or < 500 m inside, then tags by id) + power=plant centres for names; and all
  of Estonia (onshore demo, bbox + Natural Earth country filter). Country from NE admin-0. Overpass is often
  overloaded (504/timeouts): each part is retried by later runs; the workflow rebuilds site.json each time.
- build_site.osm_farms: within 400 m of a satellite turbine = duplicate; within 2 km of a satellite farm = joins
  it (`osm_added`); others cluster into new farms (`src: "osm"`), named from the nearest named plant within
  5 km, else "Unnamed wind farm <lat> <lon>". Size from tags, then MODEL_SPECS by model name, else
  OSM_DEFAULT_MW per country (`est` says which). Chinese OSM turbines are usually untagged ("yes").
- Estonia onshore demo: farms with `on: 1`, region Europe, green on the map, PyWake with TI 10 %
  (config.TI_ONSHORE), still flat terrain / no forest or stability. Not in Market/System.

## High-voltage grid layer (Oct 2026)
- scripts/fetch_grid.py (grid workflow: on script change, monthly, manual) downloads lines.csv/links.csv of the
  latest PyPSA-Eur OSM prebuilt network (Zenodo, ODbL; v0.7 at first fetch: 9 162 lines, 39 DC links) and writes
  web/data/grid.json ([kV or 0 for DC, flags (1 under construction, 2 cable, circuits << 2), coords]),
  ~300 m simplification, 1.15 MB, loaded lazily by the page. The CSV 'tags' column has unquoted commas, so the
  WKT is cut out of the raw line. Raw CSVs are not committed.
- Page: toggle "High-voltage grid", ENTSO-E colour convention (750 blue, 500 crimson, 380-400 red, 300-330
  orange, 220 green, DC pink, dashed = under construction); 220 kV hidden at world zoom.
- The ENTSO-E grid map PDF is a GeoPDF (ETRS89 LCC, corner GPTS) and would extract cleanly, but ENTSO-E's
  terms forbid redistribution / derivative works without written permission, and the map is schematic
  ("not located at their real geographic location"). Not used.

## Legend toggles (Oct 2026)
- Legend entries are buttons (data-k): off/on farms, uc/cs/pl zones, g750..g220/gdc grid classes, depth.
  Hidden keys live in HID and localStorage "wm-hide" (per browser). The legend folds (button #legt, "wm-legend"). A selected farm stays visible. Zone entries
  re-enable the "Show future zones" checkbox; depth mirrors the bathymetry checkbox.

## Basemaps (Oct 2026)
- On-map basemap switcher (bottom right, #bmw): Simple (own land/sea), Map (OpenStreetMap standard tiles) or
  Satellite (EOX Sentinel-2 cloudless 2024, CC BY-NC-SA 4.0: non-commercial only; loaded without CORS, nothing reads
  the main canvas back); depth layer drawn translucent over a basemap; "Terrain shading" = Mapterhorn
  terrarium tiles (512 px, z<=12) turned into a hillshade per tile in the browser (needs CORS; sea/<=0 m
  transparent). Mercator tiles are reprojected into the equirectangular view by drawing each tile in horizontal
  strips (16 at z<=5, 6 at z<=8, else 2); ancestors fill in while tiles load; LRU caches. OSM tiles are
  inverted in dark mode. Attribution box bottom-right. Choices remembered in localStorage.
- OSM's tile servers are for light use only (usage policy). For a commercial / high-traffic product switch to a
  hosted provider (e.g. OpenFreeMap, MapTiler, Stadia) or self-hosted PMTiles.

## Price comparison (Oct 2026)
- market.ALL_PRICE_ZONES: every current physical bidding zone with an Energy-Charts day-ahead price (43; historic
  DE-AT-LU and virtual zones left out). Fetched with the per-zone cache (refetch only when hours are missing or
  tomorrow's auction is due); licence-restricted zones are dropped and re-checked once a day.
- Market tab: the line chart keeps `core_zones` (zones with farms + System tab); a heatmap card shows every open
  zone x hour, rows sorted by mean, one warm sequential ramp for >= 0 (capped at the 97th percentile) and a cool
  ramp for negative prices, hover = value and rank in that hour. Shares the Last 24 h / Tomorrow switch.

## Energy-system direction (Oct 2026)
- Renamed "Energy infra monitor". Offshore wind stays the most detailed layer; the structure (farms with `on`,
  technology colours, legend by technology) is meant to take onshore wind, nuclear and gas plants next. Large
  concentrated assets (offshore farms, nuclear, large gas/CCGT) are the easiest to show at the same detail.
- Technology colours (System tab, onshore farms on the map): nuclear red, hydro light blue, gas orange, offshore
  wind dark blue, onshore wind medium blue, solar yellow, coal dark brown, biomass & other green. Stack order
  nuc, hyd, gas, woff, won, sol, coal, oth is the one that passes the colour-vision checks in light and dark mode
  (coal next to gas or nuclear, and green next to orange or yellow, fail).
- Sidebar: on Compare / Market / System only the title, breadcrumb and region/country selector stay (class
  `keep`, body[data-tab]), plus "Sources and disclaimer" as a fold-out. Market highlights the selected country's
  bidding zones (line chart + heatmap); System opens the selected country's detail, and clicking a country card
  selects that country everywhere.

## Gas layer (Oct 2026)
- scripts/fetch_gas.py (gas workflow, daily 09:17 UTC + on change): ENTSOG public API, no token. connectionpoints
  (committed) + 8 days of daily Physical Flow per gas day (not committed) -> web/data/gas.json: points (IP,
  import, LNG, production) with GWh/d series and direction, and per-country entries by origin.
- ENTSOG positions are schematic (tpMapX/Y): cubic fit + IDW correction on ~54 known points (A dict),
  leave-one-out median ~20 km. Shown as "position approximate".
- Flow per point/day = max(entry, exit) over operator countries (operatorKey prefix); direction = exit country ->
  entry country. Country supply = entries into that country's operators, by origin (includes transit).
- Map: circles / diamonds (LNG) / squares (production), gas orange, sqrt-scaled; legend toggles gip/glng/gprod.
  System tab: "Gas supply into the system" card for the selected country.

## GIE storage and LNG (Oct 2026)
- scripts/fetch_gie.py runs in the gas workflow with secret GIE_KEY (x-key header). AGSI+ (storage: full %,
  gasInStorage TWh, injection/withdrawal GWh/d, workingGasVolume TWh) and ALSI (sendOut GWh/d, inventory GWh)
  for EU + each country, 400 days -> web/data/gie.json. Raw per-country files are not committed.
- System tab: "EU gas storage" overview (fill line this year vs year before, largest countries) at the top,
  and "Gas storage and LNG" card for the selected country.

## ENTSO-E (Oct 2026)
- pipeline/entsoe.py, called from market.build when ENTSOE_TOKEN is set (hourly workflow). Fills day-ahead prices
  for every zone Energy-Charts can't publish (A44), and adds System-tab countries from ENTSO-E (A75 generation per
  PSR type mapped to Energy-Charts ids, A65 load, A11 physical flows per neighbour -> net import; flows refreshed
  every 3 h). Cache in state/entsoe_cache.json. Errors land in feed market.diag.entsoe.
- Page: "CEE / SEE" group in the selector (GROUPS), CEE/SEE countries without farms get map boxes (CBOX);
  Market highlights the group's zones, System shows the group's countries.
- Next: A73 per-unit generation for large plants on the map (needs plant positions: powerplantmatching).

## Known gaps / next ideas
- TO DO: stability-aware hub-height wind. Today pipeline/run.py `hub_wind` scales the ECMWF IFS 100 m wind with a
  neutral log law (z0 = 0.0002 m, offshore) for every farm. Plan: also fetch 10 m wind (Open-Meteo ECMWF endpoint
  has both), fit the hourly shear from the 10/100 m ratio (power-law alpha or log-law with an effective z0) and
  use it above 100 m, so stable offshore conditions (strong shear, spring/summer) aren't underestimated; cap alpha
  to a sane range. Give onshore farms (f["on"]) their own roughness (~0.03-0.1 m) instead of the offshore z0.
  Check against hub-height measurements where available (e.g. FINO, met-mast data).
- Newer farms outside Europe (China's 2021-26 build-out, Taiwan, Japan, US) need a newer source.
- The EuroWindWakes database has no Finnish farms (Tahkoluoto) and only two Norwegian demos (no Hywind Tampen).
  scripts/fetch_osm_turbines.py fills gaps from OpenStreetMap into data/raw/extra_turbines.csv (run where
  Overpass is reachable, i.e. not in the cloud build environment). Unknown turbine types get a generic curve.
  On GitHub: the extra-turbines workflow runs it when the script changes and commits the CSV + site.json.
  Overpass servers are often overloaded; the script falls back to the main OSM API (bbox < 0.25 deg²).
- Tahkoluoto: 11 offshore turbines kept by OSM node id (the bbox also holds 6 harbour turbines and one at
  Reposaari). All are labelled SWT-4.0-130 4 MW; one is probably the 2010 ~2.3 MW pilot (not identifiable).
- Direction-uncertainty averaging (±5°) for aligned rows (Horns Rev I at 270° gives ~55–70 % loss vs ~40 % measured).
- Farm-to-farm (cluster) wakes: run neighbouring farms together in PyWake.
- Inter-array cables.
- Validation per farm: Elexon (UK, per BM unit) and ENTSO-E per unit; country-level check vs Energy-Charts is in the Market tab.
- Product thinking: capture-price discount and wake-cost analytics per farm/zone are the most commercial part so far.
- Price data and cross-border flows (later phase).
- Onshore Denmark with satellite roughness (v2); DK onshore turbine file exists but is not in this repo.

## Working from a browser-only session
The code runs on GitHub, not locally. Clone the repo, edit, push to `main`; the workflow runs the pipeline
and redeploys the site in ~3 minutes. Check the run in the Actions tab.
- Renamed "GridEconomics" (page title and heading; the repo and site URL stay energy-infra).
