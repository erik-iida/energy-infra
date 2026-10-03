# Development notes

Handover notes for whoever (human or Claude) picks this up next. Keep them current.

**Before the first commit in a fresh clone** (Claude sessions default to `Claude <noreply@anthropic.com>`, which GitHub
does not count in Erik's contribution graph):
`git config user.name "Erik Iida" && git config user.email "152779827+erik-iida@users.noreply.github.com"`
Keep the `Co-Authored-By: Claude ...` trailer in the commit message. Workflow commits by `wake-monitor-bot` stay as they are.

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

## Late Oct 2-3 2026: GridEconomics
- Renamed "GridEconomics" (page title, heading, README); repo and URL stay energy-infra
  (https://erik-iida.github.io/energy-infra/ - the bare erik-iida.github.io has no site).
- web/index.html is the only page source (one file: CSS + HTML + JS). Edit it directly; check the script with
  `node --check` on the extracted <script> and test with playwright against `python -m http.server` in web/.
  The committed web/data/feed.json is stale (the hourly workflow deploys a fresh one without committing it):
  for local tests inject a `market` block into a copy, never commit it.
- Map projection is Web Mercator (V.s = px per degree of longitude, sl() = px per degree of latitude at the
  centre for zoom thresholds); north/south panning is clamped to the world edge (clampV). Hit-testing uses
  CSS-pixel paths with an identity transform (works at any display scaling).
- Map price overlay: bidding zones from web/data/zones.json (scripts/build_zones.py: entsoe-py MIT geometries +
  Natural Earth for IE(SEM), ME, MK, BA, UA-IPS, AL) coloured by day-ahead price now / 24 h avg / tomorrow /
  TB2 / TB4; opens on "Now"; low prices fade to transparent; click a zone -> System tab for that country.
  Price controls live in the legend; legend headings switch whole layers.
- Browser wake model defaults to TurbOPark (Nygaard 2022), a port of PyWake's Nygaard_2022 (TurboGaussian,
  A=0.04, ground mirror, Gaussian rotor overlap, squared sum); matches PyWake within ~0.2 % in wind speed.
  The models panel shows PyWake output and PyWake calc time per model (feed farms[id].ms, .nt).
- Capture prices: scripts/fetch_capture.py + capture workflow (every 3 h) -> web/data/capture.json: per bidding
  zone and month, ENTSO-E A75 generation per production type + A44 prices -> output-weighted capture price per
  technology, baseload, negative hours, daily TB2/TB4 (CET days). State in data/raw/capture/cells.json.
  Market tab: all-markets monthly heatmap (solar / wind on / wind off), per-country technology tables + chart.
- Ukraine (UA-IPS) prices are published in UAH: converted at the latest NBU rate stored with history in
  data/fx.json (refreshed daily by the capture workflow; cells kept in UAH, converted when published).
- TB2/TB4 (mean of the 2/4 highest minus 2/4 lowest hourly prices) shown next to the price heatmap.
- All tables in Market and System sort by header (unit-aware). Technology colours: nuclear red, coal & lignite
  black, gas grey, oil brown, onshore wind green, offshore wind dark blue, hydro purple, biomass & waste dark
  green, solar yellow.
- System tab: electricity before gas; "Compare <technology> across countries" (% of generation / consumption /
  MW); country flags.
- Hub-height wind: ECMWF IFS HRES 100 m (Open-Meteo ECMWF endpoint) scaled with a neutral log law,
  z0 = 0.0002 m (see the to-do below).
- Pending: Balancing Services token (BALANCING_TOKEN secret) for imbalance / aFRR / mFRR; power-plant layer
  (powerplantmatching positions + ENTSO-E A73 per-unit output, CEE/SEE first).

## Data store (Oct 3 2026)
- Goal: own history for the newsletter / product (the APIs only give "now"). Core product = data + newsletter; the
  map is the showcase. Free sources only until there is traction. ENTSO-E is the primary source; Energy-Charts is
  not stored (ENTSO-E covers every zone, and many Energy-Charts series are licensed private-use only).
- Storage: Parquet assets of ONE GitHub release, tag `store` (prerelease, not "latest"). Release assets are not in
  git history, so rewriting monthly files doesn't grow the repo. One file per dataset and UTC month:
  `<dataset>_<YYYY-MM>.parquet` (zstd). Plus `backfill_state.json` and `collector_log.json` (run summaries:
  calls, errors, rows per file). The repo is public, so the store is public: openly licensed data only.
  Going private later keeps everything working (assets become private with the repo).
- collector/store.py: write() merges by the dataset's key; the most recently fetched row wins (TSO revisions);
  rows are never dropped and a shrinking merge is refused. Upload = new asset `tmp-<name>`, delete old, rename;
  read() falls back to `tmp-<name>` if a run died in between. STORE_DIR=<folder> switches to a local folder (tests).
  store.load(dataset, months) concatenates months for analysis.
- Datasets (all with `fetched` UTC; timestamps UTC; native resolution in `res_min`, nothing averaged):
  da_price (A44: zone, ts, res_min, seq, price, currency - as published, UA-IPS in UAH),
  gen_actual (A75: zone, ts, res_min, psr B01..B25, dir gen/cons, mw), gen_forecast (A69 day-ahead wind/solar),
  load (A65: kind actual / da_forecast), flows (A11 physical, from_zone -> to_zone, both directions of 89 borders
  in collector/entsoe_raw.BORDERS), farm_hourly (farm_id, ts, ws hub m/s, wd, p_<wake model> MW, nwp),
  farm_forecast (issued, farm_id, ts, lead_h, same columns; once per new Open-Meteo fetch, ~6 h),
  farms_meta (farm id -> name, country, position, MW, turbines; monthly snapshot). Farm ids are permanent:
  never renumber or reuse them, or the farm history no longer lines up.
- Workflows: collect.yml (concurrency group store-entsoe) - daily 12:35 UTC = last 4 days + today/tomorrow
  (~410 calls); backfill every 2 h = whole months from BACKFILL_FROM (repo variable, default 2024-01), newest
  first, ~410 calls per month, 4 threads with a shared 330 req/min limiter; manual `probe` mode prints parsed rows
  for DE-LU, RO and HU<->RO without writing. hourly.yml runs collector/farms.py at the end of pipeline.run
  (COLLECT_FARMS=1, GH_TOKEN; needs contents: write); a store failure only prints a warning.
- Not stored yet: gas (ENTSOG flows, GIE storage/LNG: both have API history, so backfillable later), ERA5 /
  Open-Meteo archive wind per farm (backfillable), Balancing Services (token pending), A73 per-unit output.
- Licences: check ENTSO-E reuse terms for derived figures before the first newsletter goes out. Open-Meteo's free
  tier is non-commercial: farm wind/wake data needs a paid plan or another source once the product earns money.

### Findings from the first collect probe (Oct 3 2026)
- A44 `classificationSequence` (probe: scripts/probe_seq.py -> data/raw/entsoe/probe_seq_log.txt). Position 1 (or
  untagged) is the auction result: the site's DE-LU price equals seq 1 to the cent (max diff 0.005). AT, DE-LU, DK2
  and ES also carry a position-2 series: it differs from seq 1 by ~10 EUR/MWh on average (max 56), covers days whose
  auction has not run (at 00:44 UTC on 3 Oct it ran to the end of 5 Oct), has gaps (e.g. 5 missing quarter-hours on
  4 Oct) and exists for past days too (back to at least 18 Sep). What it is is NOT identified. FR, PL, BG (and the
  other zones probed) return two identical series without a tag: harmless, the store merge collapses them.
  Averaging all series gave a mean |diff| of 4.3 EUR/MWh against the site: that is what the old code did.
- Fix: collector/entsoe_raw.py keeps seq 1 only (PRICE_SEQ_KEEP) and counts dropped rows per zone in
  collector_log.json (`seq_dropped`; a change in ENTSO-E's tagging shows up there). The same bug was in
  pipeline/entsoe.prices() and scripts/fetch_capture.cell(), which averaged every TimeSeries: capture prices,
  baseload and TB2/TB4 for AT, DE-LU, DK2 and ES were wrong. Both now use entsoe.price_seq(); capture cells carry
  `sq: 1`, older cells are refetched (all zones, 24 months, resumable) and AT/DE-LU/DK2/ES are left out of
  capture.json until their cells are redone (SEQ2_ZONES in fetch_capture.py).
- A75 lag (scripts/probe_lag.py, uses the collector's parser): RO publishes ~41 h late (newest 1 Oct 07:30 UTC at
  00:53 UTC on 3 Oct), AL and MK ~28 h, every other zone < 6 h. 29-30 Sep are complete for RO, so the lag is
  1.5-2.5 days, well inside the 4-day daily window (each day gets four retries). Note A03 curves: raw point counts
  per type say nothing about completeness, always check after forward-fill. The daily run now logs
  `late_gen_actual_h` (zones whose newest A75 is > 6 h old) in collector_log.json: watch RO there.
- Actions logs are not readable from the cloud session: use probe scripts that commit a log (probe-seq, probe-lag,
  entsoe-probe workflows).

## Newsletter generator (Oct 3 2026)
- newsletter/: metrics.py (daily metrics per zone and CET day from da_price seq 1, EUR only, hourly means: baseload,
  TB2, TB4, negative hours, min/max, capture price and capture rate for solar / onshore / offshore wind; a day needs
  >= 23 priced hours, capture >= 20 hours of generation data), signals.py (universal rule table: metric, high/low
  percentile vs the zone's own last 90 days, min 30 days of history, absolute gate; add a rule = add a line to RULES),
  build.py (facts.json = the contract, brief.md = deterministic draft, brief.html = draft + TB4 bar chart with each
  zone's p90 tick). No API calls: the LLM/human step reads facts.json.
- Run: `python -m newsletter.build [--day YYYY-MM-DD]` (yesterday CET by default; STORE_DIR=<folder> for a local copy
  of the store). Workflow newsletter.yml is manual (workflow_dispatch), output as artifact, not committed (public repo).
  Offline test: `python -m tests.test_newsletter` (synthetic store: seq-2 and UAH rows ignored, incomplete day gated,
  spike flagged).
- Draft shape follows the product note: headline (widest TB4 in CEE/SEE) + what left its normal range + next 24 h from
  tomorrow's auction. Not yet: UA-IPS (UAH), price-setter / SRMC, clean spark spreads, flows and wind drill-down when a
  signal fires, the Streamlit/site "Signals" view, e-mail sending.
- Needs history for percentiles: until the backfill has run, the draft says so in the data notes.

## Data tab (Oct 3 2026)
- Fifth tab, "Data": browse the stored history like a spreadsheet. Dataset buttons (day-ahead price, actual generation,
  wind & solar forecast, load, cross-border flows), zone select, range (1-30 days), CET/UTC, newest/oldest first,
  variable chips to switch columns on/off (technology colours from the --m-* palette; pumping/consumption columns start
  off), Mean/Min/Max rows on top, negatives red, future (day-ahead) rows marked, CSV download of what is shown.
  Timestamps run down the rows. The Signals tab (anomaly filters) comes later and will be the sixth.
- Data path: the site is static and release assets are not CORS-readable, so scripts/build_browse.py (run by hourly.yml,
  cached for 3 h, continue-on-error) exports the last 30 days of the store to web/data/browse/ (index.json +
  <dataset>/<zone>.json, hourly means in UTC, seq 1 prices only). Not committed (.gitignore). If the export is missing
  or the store is empty the tab says so. Local test: STORE_DIR=<folder> python scripts/build_browse.py, then serve web/.
- Next: chart toggle (the page already has svg line charts), native 15-min resolution, longer ranges per month file,
  farm_hourly / farm_forecast per wind farm, capture/TB2/TB4 derived columns (newsletter/metrics.py has them).

## Fuel prices and spark spreads (Oct 3 2026)
- Gas: yfinance `TTF=F` (Yahoo, ICE Endex front month, EUR/MWh, daily since Oct 2017; probe: scripts/probe_yf.py ->
  data/raw/fuel/probe_yf_log.txt). Carbon: NO free EUA series on Yahoo (KEUA, EUA=F returned nothing; KRBN is a USD
  global-carbon ETF, only a rough proxy, not used). Optional manual carbon input: newsletter/eua_manual.csv
  (date,eua_eur_t; gitignored); without it spreads are FUEL-ONLY and the brief says so.
- PRIVATE-DATA RULE (Erik): Yahoo's terms don't allow republishing, and the repo is public. The gas price is fetched at
  run time in newsletter/fuel.py and never written to the repo, the `store` release, facts.json, brief.md/html or the
  Data tab export. Only derived spreads (spark_base, spark_top4 = baseload / mean of the 4 highest hours minus the
  reference CCGT cost: 55 % efficiency, 0.202 tCO2/MWh_th) leave it; the SRMC itself is not a metric. Tested in
  tests/test_newsletter.py. If a paid or licensed feed replaces it, revisit this rule.
- Same reference cost in every zone: CEE/SEE hubs trade above TTF and some plants have oil-indexed or regulated gas,
  so zone spreads there are indicative. Idea for later: compare implied gas cost at gas-marginal hours across zones
  against DE-LU/NL to measure local premia (needs carbon).
- Not done: dark spreads (no coal price source), implied-gas-cost metric, spark spreads on the site's Data/Signals tabs.
- newsletter.yml installs requirements-newsletter.txt (collect + yfinance). Yahoo is not reachable from the cloud
  session: the fuel fetch only runs on Actions; a failed fetch leaves the brief without spark spreads and says so.

## Known gaps / next ideas
- Store: identify the A44 seq-2 series (ask ENTSO-E support / read the Transparency API guide if it matters); decide
  whether to keep it separately. After the first backfill, check collector_log.json (`seq_dropped`, `late_gen_actual_h`).
- Newsletter: first hand-assembled briefs from `newsletter.build`, then the 15-user test; UA-IPS via data/fx.json.
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
