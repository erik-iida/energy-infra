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
- Web page is plain HTML/JS with no build step: `web/index.html` (shell + bootstrap), `web/css/base.css`, ES modules under
  `web/js/` (see "Spec 3 step 2" below and docs/ARCHITECTURE.md). It loads `data/site.json` + `data/feed.json` from the
  assembled `dist/` (spec 3 step 3: `web/` is source only; `data/static/` holds committed inputs, `build/` a run's output).
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
- Page source: `web/index.html` + `web/css/base.css` + `web/js/**` (since 4 Oct 2026; one file before). Check with
  `python -m pytest tests -q` (incl. node --check of every module) and the smoke test, or playwright against `python -m http.server` in web/.
  feed.json is not committed at all since 4 Oct 2026 (`build/data/feed.json`, built every hour and deployed via the
  `built-data` artifact): for local tests inject a `market` block into a copy under `build/data/`.
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
- A44 `classificationSequence` (probe: tools/probes/probe_seq.py -> data/raw/entsoe/probe_seq_log.txt). Position 1 (or
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
- A75 lag (tools/probes/probe_lag.py, uses the collector's parser): RO publishes ~41 h late (newest 1 Oct 07:30 UTC at
  00:53 UTC on 3 Oct), AL and MK ~28 h, every other zone < 6 h. 29-30 Sep are complete for RO, so the lag is
  1.5-2.5 days, well inside the 4-day daily window (each day gets four retries). Note A03 curves: raw point counts
  per type say nothing about completeness, always check after forward-fill. The daily run now logs
  `late_gen_actual_h` (zones whose newest A75 is > 6 h old) in collector_log.json: watch RO there.
- Actions logs are not readable from the cloud session: use probe scripts that commit a log (probe-seq, probe-lag,
  entsoe-probe workflows).

### First backfill check (Oct 3 2026, ~04:30 CET)
- Store `store` release: Apr-Oct 2026 in all five datasets after two backfill runs (one manual); 28 months still to do
  (BACKFILL_FROM 2024-01). Each month = 407 calls, 0 errors. Typical sizes: da_price ~0.31 MB, flows ~1.5 MB,
  gen_actual ~4.4 MB, gen_forecast ~1.2 MB, load ~1.0 MB per month (zstd Parquet), so ~8.5 MB/month, ~280 MB for 33 months.
- da_price in the store holds seq 1 only (checked Apr, Jun); `seq_dropped` in the log: AT, DE-LU, DK1, DK2, ES (DK1 had
  no seq-2 in the first probe, it does in Jul-Sep; added to fetch_capture.SEQ2_ZONES).
- capture.yml refetch finished (1055 cells, all `sq: 1`); AT, DE-LU, DK1, DK2, ES are back in capture.json (24 months).
- newsletter.build on the real store (day 2026-10-02) works; first drafts sent to Erik. The collect workflow can be
  started by hand with mode=backfill to speed up the history (the concurrency group serialises it with the cron runs).
- RO late-lag check (point 2) is still to do after the 12:35 UTC daily run.

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

## Flags and Data tabs (Oct 3 2026)
- Tabs: Map, Compare, Market, System, **Flags**, **Data**.
- **Flags** (fifth tab): the newsletter signals as an overview. `newsletter/signals.py` has `scan()` (every zone x rule with
  value, percentile vs the zone's own last 90 days, median/P10/P90, status ok/short/gated, side when fired);
  `evaluate()` is its fired subset. `build_browse.flags_export` writes `web/data/browse/flags.json` for the latest complete
  CET day (spark spreads excluded: private data). Page: fired-signals table + a zone x metric matrix shaded by percentile
  (orange high, blue low, bold outline = fired, grey = < 30 days of history), zones filter (CEE/SEE + DE-LU or all).
  The rules, gates and window are the same as in the newsletter, so a new Rule appears in both.
- **Data** (sixth tab) has two modes only: *Time series* and *Installed capacity & capacity factor*.
  Time series: one flexible table, any zones x any variables. Zone chips (multi-select, list collapsed to the selected
  ones), variable chips grouped (Prices & daily spreads, Actual generation, Day-ahead forecast, Load, Cross-border flows;
  click a group name to expand, all/none per group). Columns are ordered variable-then-zone so the same variable in several
  zones sits side by side. Range 1-30 days, CET/UTC, newest/oldest first, Mean/Min/Max rows, future rows marked, CSV.
  Daily metrics are columns too (baseload, **TB2, TB4**, top-4 mean, negative hours, min/max price, solar/onshore/offshore
  capture price and rate) computed per CET day by `newsletter/metrics.py` and repeated on every hour of the day.
  Default on: day-ahead price, TB2, TB4, solar, onshore/offshore wind, actual load.
- Data path: static site, release assets not CORS-readable, so `scripts/build_browse.py` (hourly.yml, cached 3 h,
  continue-on-error) exports `build/data/browse/{index.json, ts/<zone>.json, capacity.json, flags.json}` (served as `data/browse/`) (hourly means in
  UTC, last 30 days + days ahead, seq-1 prices only; one file per zone holds every variable; index.json has the variable
  catalogue and which variable exists in which zone). Not committed (.gitignore). Local test: `STORE_DIR=<folder> python
  scripts/build_browse.py`, serve web/.
- Capacity mode: every IRENA country (224), zones column, GW or 30-day CF, filter to countries with a bidding zone, CSV
  (see "Installed capacity and capacity factors").
- Next: chart toggle for the selected columns, native 15-min resolution and longer ranges (month files), per-farm wind
  data, capacity history (IRENA years 2015+ are already in data/ref/irena_capacity.csv), flags for tomorrow's auction,
  signal history (flags per day) once the store has a year.

## Metric catalogue, residual load, interconnection, stored daily metrics (Oct 3 2026)
- **Classification first.** `newsletter/registry.py` is the single definition of every daily metric: id, label, family,
  unit, definition, input datasets, minimum hours per day, what "high" means, display scale. Families: price_level,
  storage_spread, price_shape, capture, residual_load, interconnection (+ fuel_spread, private, never exported or stored).
  The metric functions (metrics.py), signal rules (signals.py), the Data-tab export (build_browse.py) and the stored table
  all use it; test_registry.py checks they stay consistent. `registry.describe()` prints the catalogue as a table.
  Change a definition = bump `registry.VERSION` (stored rows carry it) and recompute (`metrics` workflow, mode=all).
- New metrics (version 2): `res_mean`, `res_peak`, `res_min`, `res_ramp3`, `vre_share` (residual load = actual load - solar
  - onshore - offshore wind, hourly; per day only the technologies the zone reports >= 20 h, only hours that have load and all of
  them) and `net_import`, `net_import_max`, `net_import_min`, `import_share` (physical flows over the zone's borders that
  are in the store, import positive; a day counts only when the set of borders equals the set present on most days of the
  window; borders to zones outside the store - GB, MD, TR, ... - are not included, so it is the net position over the
  collected borders, not the full one).
- New signal rules: `res_peak` (high, >= 500 MW), `res_min` (low = surplus, >= 300 MW), `res_ramp3` (high, >= 500 MW),
  `import_share` (high or low, >= 5 % of load). They show up in the newsletter signals, the Flags tab and the Data tab
  (new group "Residual load & interconnection (daily)").
- **Stored daily metrics**: store dataset `metrics_daily` (monthly Parquet assets, key zone+day+metric; columns zone, day
  (CET date), metric, value, version, fetched). `scripts/build_metrics.py` + `.github/workflows/metrics.yml`: runs after every
  collect run (and 13:10 UTC fallback), recomputes the last 10 days and fills every month the backfill has finished
  (`metrics_state.json` remembers which); `--all` / dispatch mode=all recomputes everything. Raw ENTSO-E stays the source of
  truth; this table is derived and can always be rebuilt.
- Local copy: `python scripts/pull_store.py` downloads `metrics_daily` (or `--datasets ...` / `--all`) from the public release into
  `~/gridecon-store` (refuses OneDrive folders) and writes `metrics_daily.csv`. `git pull` never brings the store (release assets).
- **Why this shape for ML later.** Long format (zone, day, metric, value) with a registry means a new metric is one line, not a
  schema change; features are pivoted on demand (`df.pivot(index=[zone, day], columns=metric)`). Rules for a model dataset:
  split by time, not at random (days are autocorrelated); percentiles / signals use only the trailing window so they are
  leak-free, but any feature computed on the full history is not; keep `version` as a feature of the dataset; missing = day
  failed its completeness rule, never zero-filled. Targets worth defining before modelling (not built): next-day TB4, next-day
  negative hours, next-day capture rate (from day-ahead forecasts of wind, solar, load - gen_forecast is already stored).
  Still missing as inputs: gas / carbon (private), temperature, installed capacity per year (IRENA to 2024), outages (A77/A80).
- Next: store IRENA capacity as a store dataset too; per-border flow metrics (HU-RO etc.) as their own family; price-setter /
  marginal technology inference; flags per day history table once metrics_daily has a year.

## Fuel prices and spark spreads (Oct 3 2026)
- Gas: yfinance `TTF=F` (Yahoo, ICE Endex front month, EUR/MWh, daily since Oct 2017; probe: tools/probes/probe_yf.py ->
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
- Market tab (Oct 3 2026): optional "Spark" column and sort in the "All bidding zones" heatmap (feed.market.spark, built by
  pipeline/spark.py: top-4-hour price minus the reference gas cost, past 24 h and tomorrow). OFF by default: repo variable
  SPARK (Settings > Secrets and variables > Actions > Variables) = `private` (spreads only in the login-protected copy, see
  below) or `public` (everyone). Reason: the page also
  shows the hourly prices, so baseload minus spark gives the reference cost back and with it the TTF price - publishing
  the spreads publishes the gas price de facto (Erik chose "derived only" before this was clear; confirm before
  switching on). The gas cost is cached in state/fuel_cache.json (Actions cache, 6 h), never in the feed.
- PRIVATE SITE (Oct 3 2026): public repo + public GitHub Pages showcase (no non-sharing data) AND a full copy behind a
  login. scripts/split_private.py (hourly.yml) copies web/ to site_private/ before stripping market.spark from the public
  feed; with SPARK=private and the secrets CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID and repo variable
  CF_PAGES_PROJECT, the step deploys site_private/ to Cloudflare Pages (continue-on-error). The login is Cloudflare
  Access (Zero Trust, free plan, email one-time-PIN for Erik): created in the Cloudflare dashboard, not in code.
  Setup steps for Erik are in the chat; once done, other non-sharing data (e.g. a future paid gas feed) can go into the
  private copy the same way. Never put it in web/ or the store release.
- newsletter.yml installs requirements-newsletter.txt (collect + yfinance). Yahoo is not reachable from the cloud
  session: the fuel fetch only runs on Actions; a failed fetch leaves the brief without spark spreads and says so.

## Installed capacity and capacity factors (Oct 3 2026)
- Source: IRENA Renewable Energy Statistics workbook (IRENA_Stats_Tool_v2.xlsb, sheet "Data"). Licence: free use with
  attribution "(c) IRENA" + edition year, so it may be published; credit it wherever capacity or CF is shown.
- `scripts/ingest_irena.py <xlsb>` -> `data/ref/irena_capacity.csv` (iso3, country, year, cls, cap_mw, gen_gwh, 2015+) and
  `irena_meta.json`. Classes: solar, wind_onshore, wind_offshore, hydro, pumped, nuclear, coal, gas, oil, fossil_nes, bio,
  geothermal, other. The workbook (18 MB) is not committed. Re-run when IRENA publishes (capacity April/July). This
  edition: capacity to 2024, generation to 2023.
- `newsletter/fundamentals.py`: zone -> country map (whole-country zones only; DE-LU = DEU+LUX; no DK/NO/SE/IT zones),
  ENTSO-E PSR -> class map, `capacity()` (latest year, fossil summed), `capacity_factors()` (>= 90 % hourly coverage of
  the window), `fundamentals_table()` (solar/wind GW, 30-day CF, solar+wind capacity / mean load, same-window baseload,
  TB4, negative hours). Wired into `newsletter.build`: `facts.json["fundamentals"]`, a "Fundamentals" sentence (incl. the
  rank correlation of VRE/load with TB4 and negative hours when >= 8 zones) and a second table in the brief.
- Known weakness: the capacity is a year-end 2024 figure against 2026 generation, so fast-growing zones read too high.
  CFs above a physical ceiling (solar 25 %, wind 40 % over 30 days) are withheld and the zone flagged (`stale_cap`;
  first run: BG solar, MK wind, LV solar+wind). Unusually low values (BA, MK solar) probably mean missing generation
  or old capacity. ENTSO-E generation can also miss small distributed solar.
- Data tab capacity mode (web/data/browse/capacity.json, written by scripts/build_browse.py:
  `capacity_export`): since Oct 3 (later) every IRENA country (224), not just bidding zones; `fundamentals.ZONE_ISO3` maps all 45
  store zones to countries (NO1-5, SE1-4, IT-*, DK1/2 are summed; a country gets a CF only if all its zones are in the
  store; DE-LU capacity incl. Luxembourg), CSV download, filter to countries with a zone. Rows are countries x classes, switch between installed GW (+ IRENA year) and 30-day CF %. CFs above a per-class
  ceiling (solar 25 %, onshore wind 40 %, offshore 60 %, anything else 100 %) are hidden. Credit "(c) IRENA" is on the page;
  confirm the edition year of the workbook and add it to the credit line (licence asks for the copyright year).
- Oddities seen in the first run (not investigated): RO nuclear is 0 MW all of September (Aug max 629 MW; ENTSO-E B14),
  BE nuclear 0 %, SK nuclear >100 % before the ceiling (Mochovce 3 not in the 2024 capacity).
- Next: ENTSO-E A68 (installed capacity per production type, annual) as a collector dataset with current-year values
  to replace the IRENA vintage; A71 forecast generation capacity is another option. Then capacity-by-tech in the Data
  tab, seasonal CF baselines once > 1 year of generation is in the store, and a CF-vs-price signal.

## Newsletter tab and feedback loop (Oct 3 2026)
- **Tab "Newsletter"** (web/index.html `nwsTab`): shows the daily draft for the last 3 CET days, with Read & rate (👍 keep / 👎 cut /
  💬 comment per paragraph or table), Edit text (markdown), an overall note, and "Send feedback". Ratings, comments and edits live in the
  browser (localStorage) until sent. Send = prefilled GitHub issue in this repo, label `newsletter-feedback` (only the changed sections of
  an edit are included; a long one is copied to the clipboard instead). Copy / download buttons as fallbacks.
- **Data**: `scripts/build_newsletter_site.py` (deploy step, cached 3 h with the Data tab export, continue-on-error) writes
  web/data/newsletter/{index.json, <day>.md} (not committed). It runs `newsletter.build --no-fuel`, so no spark data ever reaches the public site.
  `newsletter/editorial/<day>.md` (hand/chat-written text) replaces the generated text for that day; the generated one stays as `<day>.auto.md`.
  First editorial draft: 2026-10-02.
- **Reading feedback in a new chat**: `gh api "repos/erik-iida/energy-infra/issues?labels=newsletter-feedback&state=open"` (REST works from the
  cloud workspace), apply it to `newsletter/STYLE.md` and to the generator (`newsletter/build.py draft_brief`), comment on the issue with what
  changed and close it. STYLE.md is the memory of the format; keep it current.
- Not done: the draft is generated once per deploy from the store (no per-user login, no live comments, feedback is not shown back on the
  page); an email/LinkedIn export; residual load / net import sentences in the generated brief (listed in STYLE.md).

## System tab: late TSO data, hover line, residual load (Oct 3 2026)
- **Late-reporting fix** (`sysData`): hours after a technology's last report are "not yet reported", not zero. `last` = latest hour at which every
  material technology (>= 3 % of the window's energy) has reported; shares (% of generation / consumption), the stack, the cards and the tables use
  it. MW mode draws each technology up to its own last report. A technology whose last reported value is ~0 (night solar, omitted zeros) is not
  treated as lagging. The mix chart shades the hours still awaiting generation ("generation not yet reported"); the load line continues.
- **Hover**: every System chart (`svg.sx`) now draws a dashed vertical line at the hovered hour, matching the tooltip's timestamp.
- **Residual load** (load - wind - solar, as newsletter/registry.py; only where load and the technologies have reported): per-country card line,
  a "Residual load" chart card for the selected country (peak, minimum, steepest 3 h rise, wind + solar share of load), and an option in the
  "Compare across countries" selector (MW, or % of consumption; the "% of generation" button falls back to consumption for it).
- Not done: carrying lagging technologies forward (we show gaps instead of estimates); the Market tab charts were not changed.

## Layout of the non-map tabs (Oct 3 2026)
- The right-hand pane (`aside`) is hidden on every tab except the map; the content uses the full width. A country selector with flag (`#C2`, `#csf`, `csSync()`)
  sits top right of the tab row on those tabs and drives the same `S.c` / `go()` as the map's selector (a globe for World, regions and groups).
  Flags / Newsletter / Data ignore the country (they have their own zone filters).
- Country pickers (`flagSel`): the map pane's `#C` and the header `#C2` are drawn as a searchable list with flags (native select kept hidden as the source of truth; `.value=` writes resync the button). Regions/groups get a globe. Flags for CN, JP, KR, TW, VN, US, KP added to `FLAGS`/`CFLAG`; a new country needs an entry in both.
- "Sources and disclaimer" (`#footd`) moved from the pane to the bottom of the page; it is still hidden on the map tab.
- The System tab's generation table and hover list are ranked by current share; the stack order in the chart stays fixed (baseload to peaking).

## Great Britain and Ireland (Oct 3 2026)
- `collector/gbie.py` + `.github/workflows/collect-gbie.yml` (daily 12:50 UTC, backfill every 2 h from BACKFILL_FROM, state `gbie_state_v2.json`, same
  concurrency group as the ENTSO-E collector). No keys. Probe log: data/raw/gbie/probe_log.txt (tools/probes/probe_gbie.py).
- **GB** (zone `GB`, Elexon BMRS Insights `data.elexon.co.uk/bmrs/api/v1`, 30 min): `gen_actual` from FUELHH (CCGT+OCGT -> B04, coal B05, oil B06,
  PS B10, NPSHYD B11, nuclear B14, biomass B01, other B20) and B1630 `/generation/actual/per-type/wind-and-solar` (solar B16, wind on/offshore B19/B18,
  incl. the embedded estimate; FUELHH WIND is not used, it would double count); `flows` from FUELHH interconnector fuels (INTFR+INTELEC+INTIFA2 -> FR,
  INTNED NL, INTNEM BE, INTNSL NO2, INTVKL DK1, INTEW+INTIRL+INTGRNL -> IE(SEM)), directed rows, links to one neighbour summed; `load`: kind `actual`
  = INDO national demand + embedded solar + embedded wind (B1630 wind - FUELHH WIND), kind `national_demand` = raw INDO. These are estimates.
- **Ireland** (zone `IE(SEM)`): prices and generation already came from ENTSO-E; `load` actual from the EirGrid Smart Grid Dashboard `demandactual`
  region ALL (all-island = the SEM zone, 15 min). The dashboard often answers 503: `_get` retries 6 times with backoff. Its time stamps are Irish local
  time (the collector checks this each run by correlating its wind with ENTSO-E B19 and refuses to write load if neither reading correlates > 0.9).
- **Licences**: BMRS open data licence, attribution "Contains BMRS data (c) Elexon Limited copyright and database right <year>" (credited in the Data tab);
  EirGrid open data licence, "Supported by EirGrid Group Data" (credited). **Not collected**: BMRS Market Index (MID, N2EX/APX prices): third-party exchange
  data outside the BMRS licence. GB therefore has no day-ahead price in the store; system (imbalance) prices exist in BMRS (`balancing/settlement/system-prices`)
  and are Elexon's own, an option later.
- Effects: GB appears in the Data tab and the residual-load / interconnection metrics once the metrics job runs; FR, NL, BE, NO2, DK1 and IE(SEM) gain a GB
  border in the flow metrics (days without it are excluded by the border-set rule until the backfill has filled them).
- **Live System tab** (24 h): `pipeline/gbie_live.py` (called at the end of `pipeline/market.build`, never blocks the feed) builds the `gb` and `ie`
  entries from the same Elexon / EirGrid calls (hourly means); IE generation comes from ENTSO-E (`entsoe.COUNTRIES["ie"]`), IE load from EirGrid
  (read as Europe/Dublin), IE's flow to GB mirrors Elexon's. The page lists them as United Kingdom / Ireland (`SYSN`), credits in the System tab note.
  Ireland shows the SEM day-ahead price from Energy-Charts; GB shows "n/a".
- **GB prices**: `imb_price` store dataset (zone GB, ts, res_min 30, sell/buy GBP/MWh, niv MWh) = BMRS system (imbalance) prices, Elexon's own data.
  The N2EX/APX Market Index (`datasets/MID`) is the only GB wholesale price in BMRS and is third-party data the BMRS licence does not cover: not
  collected; add it only after Erik decides. The state file is `gbie_state_v2.json` (v1 predates `imb_price`).
- Not done: Data tab shows `imb_price` (build_browse has no group for it yet); capacity vintage for GB/IE in the capacity-factor tables.

## GB open data: the free equivalent of a paid GB API (Oct 3 2026)
Erik asked for the data of a paid GB API (energydashboard.co.uk: its terms forbid redistributing raw data, so it can't feed the public store) from free
sources. Probes 2-6 (tools/probes/probe_gb2..6.py, logs in data/raw/gbie/probe*_log.txt) mapped what is open.
- `collector/gbunits.py` + `collect-gbunits.yml` (daily 13:10 UTC, backfill every 2 h from BACKFILL_FROM, state `gbunits_state.json`, concurrency group
  `store-gbopen`): **unit_output** store dataset = Elexon B1610 metered output per BM unit (`/datasets/B1610/stream?from&to&bmUnit=...` repeated; 25 units
  x 10 days per request; mw = MWh x 2, signed; `run` = settlement run). About 750 units: any BM unit with a fuel type except interconnectors, plus T/E/M
  units >= 5 MW without one (batteries). Only BM units: small embedded wind/solar are not in B1610 (their total is in B1630 `gen_actual`).
  **Lag**: the latest day with data is ~4 days back (run II), later runs (SF, R1, ...) revise: the daily job re-reads 15 days, newest fetch wins,
  backfill marks a month done only when it is > 45 days old. Elexon time: `halfHourEndTime` is UTC, ts = end - 30 min.
- Same job refreshes release assets **gb_units.json** (BM-unit registry: id, NGC id, name, lead party, fuel, type, capacity, plus REPD match: repd_ref,
  repd_site, lat, lon, match_score) and **gb_repd.json** (DESNZ REPD sites with status Operational / Under Construction / Awaiting Construction /
  Decommissioned: tech, MW, turbines, CfD round, offshore round, lat/lon from British National Grid via pyproj). REPD licence: Open Government Licence v3.0.
  Matching (`gbunits.match_units`): SequenceMatcher ratio >= 0.82 of the compact names (generic words dropped, number words as digits; differing numbers
  cost 20 %), technology-compatible, matched units of a site must total 0.5-2x its REPD MW; `data/gb_unit_overrides.json` (hand-checked, "" = no site) wins.
  Checked offline on the first run's files: 98 % of wind capacity placed (30.1 of 30.8 GW), the rest are supplier-aggregated units. Thermal and nuclear
  units are not in REPD (no coordinates; use powerplantmatching later), small hydro names rarely match. **REPD offshore coordinates are approximate**
  (several farms share one point): for offshore wind prefer the farm positions already in the site data. Check `match_score` before relying on a location.
- `collector/gbhist.py` + `collect-gbhist.yml` (daily 14:20 UTC, backfill every 6 h until done, state `gbhist_state.json`): **gb_hist** = NESO historic
  generation mix + carbon intensity (half-hourly since 2009) merged with NESO historic demand (ND, TSD, embedded wind/solar generation and capacity,
  pumping, interconnector flows), one wide row per half hour; **gb_forecast** (long: series, issued, ts, mw) = NESO day-ahead wind forecast (+ archive since
  2018), NESO embedded wind and solar forecast, Elexon day-ahead national demand and wind/solar forecasts. NESO licence: "Supported by National Energy SO Open
  Data" (commercial use and redistribution allowed). Not done: the embedded forecast archive (5 M rows a year), Elexon NDF/TSDF history, Carbon Intensity
  API regional data (CC BY 4.0; regions are DNO areas).
- **Empty Data / Flags tabs (Oct 3, 15:49 CEST)**: `scripts/build_browse.py` crashed (`KeyError 'l|national_demand'`, the new GB load kind had no metadata) in the 12:06 UTC
  deploy; the step is `continue-on-error`, so the deploy went on and the 3-hour cache kept the empty export for every later deploy. Fixed: metadata for the
  kind, unknown series kinds are skipped with a message instead of crashing, and a hourly.yml step drops incomplete output so it is never cached.
  Lesson: when the store gains a new series kind, run `STORE_DIR=<last 3 months of the store> python scripts/build_browse.py` before pushing.
- **GitHub API rate limit** (found Oct 3): every monthly store write costs several GitHub API calls, and the Actions token allows ~1000 calls per hour for the
  whole repository (all workflows share it). The first full gb_hist backfill (214 monthly files) exhausted it after ~190 files; further writes (and other jobs)
  then fail with `HTTP 403: API rate limit exceeded for installation`. Hence `GBHIST_MAX_MONTHS` (40 per run, only months missing in the store) and run logs:
  collect-gbunits / collect-gbhist commit `data/raw/gbie/last_run_<job>.txt` after a failure or manual run (Actions logs are not readable from the cloud).
  Never dispatch several big backfills in the same hour.
- **National Gas** (gas NTS flows, linepack, entry points): reachable (`data.nationalgas.com/api/latest-gas-flows-download` without parameters returns the
  latest 2-minute flows; `find-gas-data-download?ids=PUBOBJ...` needs the right parameters, still 500). Reuse licence NOT clear (site terms forbid
  republishing; the portal says only that data is open under the GSO licence), so nothing is collected or published until the wording is checked.
- Not done: Data tab group / site layer for unit output and the REPD sites (build_browse), a GB plant map layer, capacity factors per wind farm
  (unit_output / REPD capacity), comparison of B1610 with PyWake output for UK farms.

## Flags drill-down, step 1 (Oct 3 2026)
Spec: project doc `claude/spec-1-flags-drilldown.md` (rev. 2). Click a row in "Signals fired" (or Enter/Space on it) to
open a panel under it; Esc, the ✕ or a second click closes it. Deep link `#flags/<zone>/<metric>/<YYYY-MM-DD>` (zone
URI-encoded, e.g. `IE(SEM)`), kept 14 days; older links show "no longer available" and fall back to the latest day.
A link to a signal that did not fire, or to a zone outside the zone filter, opens the panel above the table (`.fxsolo`).
- **Data**: no new export script. The panel reads `browse/ts/<zone>.json` (Data tab, 30 days) and slices the CET day in
  the browser (Intl, Europe/Brussels; DST days have 23/25 bars, the repeated hour is labelled `02′`).
  `build_browse.flags_export` now returns the last `FLAG_DAYS` = 14 complete CET days (one store read of 90 + 3 + 14
  days, one `all_metrics`, one `scan` per day) -> `browse/flags/<day>.json` + `browse/flags/index.json`; `flags.json`
  stays the latest day. Each file also has `days` (for the Day selector) and `context` / `context_rules`
  (`signals.CONTEXT`: display-only rules with hi = lo = None, so they never fire). ~120 KB per day raw, ~17 KB gzipped.
- **Panel**: header (plain signal name, value, percentile sentence, typical range, "?" = `FXPLAIN` one-liner), data-age
  box (generation / load hours published, latest reading, "N h old"; missing generation -> day-ahead wind and solar
  forecast as lighter bars; missing actual load -> dotted day-ahead load forecast), main chart (stacked generation by
  site technology colours, load, residual load for res_* signals, price on the right axis, event shading, hover
  crosshair via `dtip`), a caption in plain numbers, "What else was unusual" (`FXUNU` order, sorted by distance from
  P50, ≥ P90 / ≤ P10 highlighted), sources (ENTSO-E; BMRS line for GB).
- **Shading** (`fxEvents`): TB2/TB4 top/bottom k hourly prices (ties: earliest hour); negative hours; max/min residual
  hour; the 4 bars of the steepest 3-hour rise; baseload and capture rates draw reference lines instead (day mean,
  90-day median; capture price from `m|capture_*` in the zone file). Checked: the shaded hours reproduce TB2/TB4 in the
  flag files for all 1,198 zone-days of a real export (max diff 0.055 €/MWh, rounding) and on a synthetic 25-hour DST day.
  GB's chart is in £/MWh (ts file), the flag in €/MWh; the caption says so.
- **New metrics** (registry VERSION 3, family `generation`, Data tab group "Generation & load (daily)"): `gen_solar`,
  `gen_wind_onshore`, `gen_wind_offshore` (daily mean MW: over 90 days capacity is ~constant, so the percentile equals the
  capacity-factor percentile), `gas_share` (B04 / all generation, energy), `load_mean`. `metrics.slim_gen` keeps solar,
  wind, gas and one synthetic `TOTAL` row per zone-hour (hourly mean per type, clipped at 0, summed) while reading
  gen_actual (`newsletter.build.load_window` / `load_range`), so the 90-day window stays small. No signal rules for them.
  Run the metrics workflow with mode=all once so `metrics_daily` gets them.
- Local test: `STORE_DIR=<last 5 months of da_price, gen_actual, load, flows> python scripts/build_browse.py`, serve web/,
  open `#flags/RO/tb4/<day>`. Store assets download with `gh api -H "Accept: application/octet-stream"
  repos/erik-iida/energy-infra/releases/assets/<id>` (gh release download needs GraphQL, blocked in the cloud session).

## GBP/EUR rate fix (Oct 3 2026)
- GB showed no price on the Market tab and map, and the Data tab showed GBP: `data/fx.json` never got a GBP rate because
  the ECB history csv download answered without a parsable GBP column (capture_log: `fx: ECB fetch failed ValueError('no GBP rows')`).
  `entsoe.fetch_ecb_gbp` now tries the ECB Data Portal API (`data-api.ecb.europa.eu`, SDMX csvdata: TIME_PERIOD, OBS_VALUE),
  then the reference-rate zip, then the csv, and logs status / content type / first bytes of each failure; the parser
  accepts both formats, padded headers and a BOM. The hourly feed fetches the rate itself when fx.json has none
  (`market.py`, not committed; capture.yml commits it).
- Data tab: `build_browse` converts GB prices to EUR at the ECB rate of the day (rows without a rate stay GBP and are logged),
  so the GB column and the Flags panel are in €/MWh like the GB metrics.

## Newsletter feedback #1 applied (Oct 3 2026)
- Issue #1 (newsletter-feedback, 2 Oct editorial): see newsletter/STYLE.md "Format (v2)" and the feedback log.
- `draft_brief` v2: one signal in the headline (daily capture-rate signals are never quoted; TB signals only when nothing
  else fired), **Price decoupling** from `build.decoupling` (pairs with a physical-flow border in the store, at least one
  CEE/SEE zone; rel = |a - b| / max(|a|, |b|) of the day's baseload; hours with > 1 €/MWh difference), Next 24 h,
  Fundamentals as wind / solar output % of load, full names via `build.ZONE_NAME` / `zn()`.
- New daily metrics `wind_share_load`, `solar_share_load` (registry VERSION 4, family generation; also in the Flags
  "unusual" table). Daily table columns: wind % and solar % of load instead of capture rates.
- **Capacity factors no longer use IRENA** (outdated year-end capacity): `fundamentals.peak_capacity` = highest hourly
  output per class in the last 90 days (needs >= 30 days of hours), `peak_cf` = 30-day mean / that peak. Newsletter
  30-day table: shares, CF vs peak, 30-day capture rates (output-weighted price / mean price), baseload, TB4, neg. hours.
  Data tab capacity view: "30-day capacity factor %" (default, vs peak), "Peak output, 90 days GW", "Installed GW (IRENA)"
  (reference only); `build_browse` reads 90 days of gen_actual for it. The old IRENA CF functions and ceilings remain in
  fundamentals.py but nothing on the site uses them.
- 2 Oct editorial rewritten in the new format (newsletter/editorial/2026-10-02.md).

## Flags drill-down, step 2 (Oct 3 2026)
- Under the main chart: **Cross-border flows** (diverging stacked bars per border, + = import into the zone, black line =
  net position over the borders in the store), **Day-ahead prices next door** (zone bold, neighbours thin; GB labelled
  Market Index; a neighbour priced identically all day is noted as hidden behind the zone line), **Next door** cards
  (mean price and difference, day-mean net flow "sent / took N MW", the day's generation mix bar). Each neighbour keeps one
  identity colour (`FXNC`, Tableau-10-like) across flows, prices and cards; technology colours stay for generation only.
- Neighbours = the zone file's flow columns (`x|in|N`, `x|out|N`) with data on that day (`fxNbZones`), ordered by mean
  |net flow|. Their ts files load in parallel after the zone file; a missing file or a non-EUR price (UA-IPS, UAH) shows
  "price n/a" with the reason. Borders to zones outside the store (MD, TR) do not appear.
- Clicking a card swaps the panel to that neighbour for the same day (FX.open.row keeps the clicked row, "← back to RO";
  the hash follows the shown zone). Shared crosshair: every chart registers in `FX.charts` with the same x geometry
  (`fxGeom`), hovering one draws the line in all and shows that chart's tooltip.
- "What else was unusual": a value only counts as unusual when it is also beyond P90 / P10 (ties: 0 negative hours on a
  zone whose history is all zeros used to read P98 "unusually high").

## CARTO basemap key, newsletter number format (Oct 3 2026)
- CARTO raster tiles now need a key (keyless tiles carry an "API key required" watermark). Tiles come from
  `basemaps.cartocdn.com/rastertiles/<style>/{z}/{x}/{y}[@2x].png?key=...` (styles checked from Erik's browser:
  voyager, voyager_nolabels, light_all, light_nolabels, dark_all, dark_nolabels; positron / dark_matter do not exist there).
  The key is client-side (visible in the served page) but kept out of git: `scripts/build_config.py` writes it into
  `web/config.js` (`window.CFG.cartoKey`, not committed) from the **CARTO_KEY** Actions secret in hourly.yml and deploy.yml;
  no secret = old keyless host (watermark). (Until 4 Oct 2026 a `sed` on `__CARTO_KEY__` in index.html did this.) Voyager added as a basemap.
- Newsletter: whole numbers everywhere (`build._i`, half up), correlations keep two decimals; "Baseload" column is
  "Avg. power price", "% of load" is "% of consumption" (text too).

## DC flow arrows, legend in the pane, sources folded (Oct 3 2026)
- **DC flow direction** (grid layer, "DC" entry): each DC link's ends are placed in a bidding zone (zones.json; point in
  polygon, else nearest zone vertex within ~0.6°; `dcZone`). Links between two countries get the latest hourly border
  flow from the System data (`SYS[a].flows[b]`, import positive; keys are country names like "united_kingdom" or zone
  codes like "no2", mapped by `FLN` / `flKey`; the other side is used if one is missing or zero). Chevrons along the link
  point in flow direction (size grows with MW), one label per border when zoomed in ("NO2→GB 1.4 GW"). The value is the
  whole border (all AC + DC links on it), so on mixed borders (FR-ES, DK1-DE) it is the net border flow. Domestic links
  (Great Belt, Western Link, SAPEI, offshore DolWin/BorWin) and borders without flow data get no arrows.
- **Legend** moved from the map overlay into the right-hand pane ("Layers & legend", after the wake controls), always
  open (`#legt` hidden; same element and toggles).
- **Sources and notes**: source / disclaimer notes carry class `srcnote`; `foldSrc` moves them into one collapsed
  `details.srcd` "Sources and notes" at the end of the tab (Compare, Market, System, Flags, Data; a MutationObserver
  re-folds after each re-render, open state kept per tab). Flags and Data keep a one-line instruction at the top.
  Map: the pane's source note is a collapsed block too. The site-wide "Sources and disclaimer" footer stays.

## Flags in chart hovers (Oct 3 2026)
- `cmpRender` / `cmpHover` (Market price chart, System "Compare … across countries"): the hover list is now a rich
  tooltip (`dtipH`, HTML) with each series' flag, value right-aligned, the line under the cursor in bold; the chart draws a
  dot on that line at the hovered hour with a flag + label badge (flips left near the right edge).

## Land-border flow arrows; wake controls only for a selected farm (Oct 3 2026)
- Grid layer entry "Cross-border flow (land)" (key `gxb`): one arrow per neighbouring country pair on a shared land
  border. `xbBuild` finds the border from zones.json (vertices of two countries' zones closer than ~5 km, 0.1° buckets;
  57 pairs), puts the arrow on the shared vertex nearest their middle, and orients it from the exporter's area centroid
  to the importer's. Flow = `dcFlow(a, b)` (latest hour of the System data, border total); arrow size grows with MW,
  MW labels from zoom sl() >= 9. Drawn after the grid lines and DC arrows.
- The wake / forecast controls (#mapctl: forecast-wind checkbox, what-if sliders, wake model, expansion) show only
  when a farm is selected (S.farm), otherwise the pane starts with the totals and the legend.

## Interconnection layer, technology colour map, System tab order (Oct 4 2026)
- **Interconnection** is its own map layer (category `ic`, entries `xac` land border flow, `xdc` DC interconnector);
  it replaces the grid layer's DC entry and the country-level land arrows (the grid layer now draws AC lines only).
  Flows are per **bidding-zone pair** from `browse/xflow.json` (build_browse: net hourly physical flow a->b for every
  zone pair in the store, latest hour + last 24 h; ENTSO-E A11 / Elexon). Because land borders and subsea DC links mostly
  join different zone pairs (DK1-DE land vs DK2-DE Kontek, SE1-FI land vs SE3-FI Fenno-Skan, NO2-DE NordLink …), the
  land arrow is the border flow without the offshore interconnector. Where a DC cable and the land border join the same
  two zones (INELFE FR-ES, ALEGrO BE-DE, Savoie-Piemont FR-IT North: onshore DC) the land arrow carries the total and the
  cable shows direction only. A pair missing in xflow.json (or older than 18 h) falls back to the System data when the two
  countries meet at a single zone pair. Only pairs between different countries are drawn (no NO1-NO2 etc.).
- **Zone colours** (legend, formerly "Day-ahead prices"): "Colour zones by" selects day-ahead price (Now / 24 h avg /
  Tomorrow / TB2 / TB4) or any technology's output as % of load (`MO = "s:<tech>"`, `shareVal`: System data,
  country level, latest hour every material technology has reported; colours from the technology palette `--m-<tech>`,
  transparent to full colour, scale 0 to the 97th percentile).
- System tab: opening it with no region selected sets the selector to Europe. Picking a country puts its generation mix
  and load block first, above the country grid and the comparison chart.

## Hourly feed timeouts (Oct 4 2026)
- From ~02:00 UTC most hourly-feed runs were cancelled at the 30-minute job limit, so nothing deployed after 05:56 UTC.
  The pipeline step took ~25 min: Energy-Charts answered 38 of 76 calls with errors/timeouts and each failure could hold
  the job for 210 s (90 s timeout, 30 s wait, retry). `market.Client` now has a circuit breaker: 30 s timeout, 10 s
  wait, stop calling after 4 consecutive failures or 7 min of market calls (the page keeps what it got). Job limit 45 min.
  Read the step log on the job page (Run pipeline: "market: N calls, M errors", "openmeteo: … N s").

## Spec 3 step 0: Actions measurements (Oct 4 2026, read-only)
Whole history of the repo (created 30 Sep 22:11 UTC): 298 runs to 4 Oct 10:35 UTC. Source: `gh api …/actions/runs` + jobs.

| workflow | runs | ok | cancelled | failed | median / p90 run time (min) | total min |
|---|--:|--:|--:|--:|--:|--:|
| hourly-feed | 187 | 142 | 37 | 8 | 7.3 / 19.9 | 1,758 |
| osm-world | 15 | 14 | 1 | 0 | 24.6 / 45.7 | 339 |
| collect | 9 | 7 | 2 | 0 | 29.8 / 36.6 | 193 |
| collect-gbie | 9 | 7 | 2 | 0 | 2.0 / 44.0 | 137 |
| metrics | 10 | 6 | 4 | 0 | 4.5 / 48.1 | 91 |
| collect-gbunits | 7 | 6 | 0 | 1 | 4.8 / 40.5 | 90 |
| capture | 14 | 14 | 0 | 0 | 0.5 / 29.2 | 68 |
| collect-gbhist, gas, extra-turbines, bathymetry, grid, global-turbines, 13 probes | 49 | | | | | ~125 |

hourly-feed in detail (jobs API):
- Triggers: 129 push, 29 schedule, 28 workflow_run (after data jobs), 1 manual.
- Queue (run created -> job started): median 0.1 min, p90 6 min, max 27 min; 9 of 103 pushes that ran waited > 5 min.
  26 pushes never ran: replaced in the queue by a newer push (concurrency group keeps only the latest pending run).
- Job time median 6.4 min, p90 17 min. Steps: **Run pipeline 5.5 / 15.0 / 29.8 min** (median / p90 / max: forecasts,
  PyWake on 593 farms, ENTSO-E and Energy-Charts calls), newsletter drafts 2.7, Data-tab export 1.2, pip 0.4, deploy 0.1.
- 6 runs timed out at 30 min on 4 Oct (Energy-Charts errors, fixed with the circuit breaker); 8 failures on 30 Sep–2 Oct.
- Reading: a front-end push waits for the **whole pipeline** (median ~6, often 15+ min); queueing adds a few minutes
  only sometimes. So the main delay is "every push runs the pipeline", not the queue: spec 3's fast deploy (step 5)
  removes it. Actions minutes: ~2,800 in 3.5 days (~24,000 per month), free while the repo is public; a private repo
  (spec 2) gets 2,000 free minutes per month on the free plan, so spec 2 needs this number.

## Spec 3 kickoff (Oct 4 2026)
- Erik approved all seven defaults of spec 3 (project doc `claude/spec-3-frontend-backend-split.md`); the order of work
  changed after step 0: safety net (step 1), then the fast deploy (step 5), then the `index.html` split. Decision log:
  docs/DECISIONS.md. Every step: proposal to Erik, his go-ahead, build and test, show, push, verify, report.

## Spec 3 step 1: safety net (Oct 4 2026)
Nothing visible changed on the site. Added:
- `docs/ARCHITECTURE.md` (plain-language map + diagram) and `docs/DATA_CONTRACT.md` (every file the page loads: writer,
  cadence, reader, fields, public). `market_history.json` is loaded but unused (removal candidate, waiting for Erik).
- Schema stamps: `"schema": 1` in feed.json, market_history.json, browse/* and newsletter/index.json;
  `scripts/build_meta.py` writes `data/meta.json` (schema + newest data point per file) in hourly-feed before deploy
  (never fails the job). Bump a schema number in build_meta.SCHEMAS **and** the contract table together.
- Test data: `tests/fixtures/make_fixtures.py` -> `tests/fixtures/data` (20 farms, synthetic feed at NOW = 2026-10-04
  11:00Z, trimmed static files, browse/flags/newsletter). Gotcha: farms point at turbine types by index (`ti`), so
  trimming `types` needs the index remap (done in the script).
- Tests: `test_wake_parity.py` (page's JS `run()` in node vs PyWake numbers in `tests/fixtures/wake_reference.json`,
  rebuilt by `make_wake_reference.py`; agreement ~0.001 %, tolerance 0.5 %), `test_contract.py` (page fetches <-> contract
  table <-> build_meta <-> fixture stamps), `test_page_syntax.py` (node --check), `tests/e2e/test_smoke.py` (playwright,
  fixtures served as data/, external hosts blocked, clock fixed; all 7 tabs at 1536x864 @1.25 and 390 px phone, flags
  deep link; baselines in tests/e2e/baseline, `UPDATE_BASELINE=1` rewrites them).
- `.github/workflows/checks.yml`: ruff (errors only: E9,F63,F7,F82), pytest, smoke test, screenshots as artifact. Separate
  from hourly-feed: a red check never blocks a deploy.
- Wake parity test extracts code between `const URG=` .. `const CT=` and the `/* in-browser wake models */` block up to
  `function spacingOf` from the page JavaScript (`tests/pagejs.py`, today `web/js/core/wake.js`): keep those markers or update the test.

## Spec 3 step 5: fast deploy (Oct 4 2026)
- `hourly.yml` = build job (pipeline, Data-tab export, newsletter, meta.json, private Cloudflare copy) that uploads the
  public data as artifact `built-data` (feed.json without spark, market_history.json, meta.json, browse/, newsletter/;
  3 days), then calls `deploy.yml` with its run id.
- `deploy.yml`: checkout of **main** (never an older SHA), newest `built-data` (or the given run's), completeness check
  (site.json, feed.json, no spark in feed), CARTO key, Pages. Triggers: push to `web/**`, bot workflows completed, manual,
  workflow_call. Concurrency `pages-deploy`, no cancelling.
- hourly push trigger ignores `web/**`, `docs/**`, `tests/**`, `**/*.md`; per-step timeouts (pipeline 30, export 10,
  newsletter 10).
- Gotchas: `gh run download` refuses to overwrite, so it unpacks into $RUNNER_TEMP first. Artifacts can't be downloaded
  from the cloud workspace (blob host blocked): check deploys on the live site. If no hourly build succeeded for 3 days,
  deploy.yml fails with "no built-data artifact" (run hourly-feed by hand).

## Spec 3 step 5c: market_history.json removed (Oct 4 2026)
The monthly offshore capture history from Energy-Charts (DE, NL, BE, DK, FR; `market.history()`) was loaded by the page
but unused since `capture.json` (ENTSO-E, all zones and technologies) replaced that view in 34cbbc6. Removed the file, the
page's fetch, `history()`/`history_public()`/`zone_weights()` and the HISTORY_* constants: up to ~9 fewer Energy-Charts
calls per hourly run. `state/market_history.json` in the Actions cache is simply no longer read. `python -m
tests.mock_market` (offline Energy-Charts mock) now stubs GB/IE live data; steady state 24 Energy-Charts calls per run.

## Spec 3 step 5b: one market source (ENTSO-E), PyWake cache, GIE incremental (Oct 4 2026)
Measured on the live feed first (new `feed.timing_s`, `market.diag.seconds`): wake 67 s, Energy-Charts 52 s for 8 calls
that all failed (circuit breaker), ENTSO-E 4 s for 20 countries. The System tab had lost DE/FR/NL/BE/DK/NO/SE/PL/AT/CH.
- **Energy-Charts removed from the hourly feed** (Erik, 4 Oct). `pipeline/market.py` now only assembles ENTSO-E + GB/IE.
  Prices: `entsoe.prices` for all ALL_PRICE_ZONES + MK, BA. System: the 10 western / Nordic countries were added to
  `entsoe.COUNTRIES`; an area can be a list of zones (DK1+DK2, NO1-5, SE1-4, summed; hours where a zone has not reported
  are dropped, no false dips) and a neighbour can be a list of (own zone, neighbour zone) borders whose flows are added.
  Countries are fetched in parallel (6 threads; ENTSO-E allows 400 req/min). Actual offshore for the model check = the
  `wind_offshore` series of each country (skipped when the country lags). Page and README credits now name ENTSO-E only.
  `tests/test_entsoe_system.py` checks this offline; `tests/mock_market.py` (Energy-Charts mock) removed.
- **PyWake result cache** (`state/wake_cache.json`): a farm-hour is reused when its hub-height wind is unchanged and the
  farm signature (layout, turbine types, hash of wake.py) matches. Local: 96 s -> 0.2 s, identical output.
- **GIE**: last 14 days merged into gie.json by gas day; full 400-day pull on Mondays (or `--full`, or no gie.json).
- Possible next: hourly-feed flows/generation could be read from the collector's store instead of a second set of
  ENTSO-E calls (spec 2: one collect step feeding both).

## Spec 3 step 5d: installs, store downloads, collector window (Oct 4 2026)
- **Data tab + Newsletter export in the background**: they read only the store, so hourly.yml starts them (nohup,
  /tmp/export.log) before `Run pipeline` and waits for them afterwards; on the 3-hourly rebuild runs this overlaps
  ~3 min (Data-tab export ~87 s + newsletter ~89 s with the shared store cache; newsletter was ~162 s). Manual rebuild:
  "Run workflow" on hourly-feed with `rebuild_tabs`.
- **PyWake ahead**: PyWake's cost per call is per turbine (≈0.31 s per farm for 1 hour, 0.45 s for 25), so the cache
  alone only helped the :37 run. When a farm is computed, all forecast hours up to REFRESH_HOURS + 24 h ahead are computed
  in the same call; later runs reuse them until the forecast changes (simulated hours +1, +2, +7: 0.2-0.3 s, identical).
- **ENTSO-E rate limits**: the feed (6 threads) and the collector (4 threads) running together exceeded 400 req/min; the
  feed's ENTSO-E part took 680 s of 429 retries (14:10 UTC run). Shared `entsoe.RateLimiter`: feed 240/min
  (ENTSOE_PER_MIN), collector 150/min (COLLECT_PER_MIN; it is latency-bound at ~140/min anyway). Plus a 240 s budget per feed run (ENTSOE_MAX_WALL_S): skipped
  countries keep their last data with `lag_h` set (for up to 6 h), so the page labels it "data N h old".
- **uv instead of pip** in every regular workflow (`astral-sh/setup-uv`, `uv pip install --system`, no cache): local test
  5.6 s vs 37 s for requirements.txt. A cache of the installed packages would be ~700-800 MB, slower to restore than uv
  downloads fresh, so none.
- **Store download cache** (`collector/store.py`): asset bytes cached per asset id in memory (all Store() objects in a
  process) and on disk under STORE_CACHE (hourly.yml: /tmp/store-cache, shared by build_browse and the newsletter
  drafts); the asset listing is shared too. An upload gives a new id, so no stale reads; a download that fails because the
  asset was replaced meanwhile lists again once and retries. Before: the newsletter re-downloaded the same monthly files
  for every function and every day (3 days), and listed ~600 assets each time. `tests/test_store_cache.py`.
- **Collector**: backfill handled the running month too and never marked it done, so every 2-hourly run re-downloaded the
  whole month (46 zones, 89 borders; 133-150 s, growing through the month). Now backfill covers ended months only, and
  the 2-hourly schedule runs `auto`: backfill while ended months are missing, else `recent` (last 2 days + tomorrow).
  Daily 12:35 UTC keeps the 4-day window for revisions.

## Spec 3 step 2: index.html split into modules (Oct 4 2026)
Six pushes, no visual change (15 baseline screenshots pixel-identical after each). Decisions: docs/DECISIONS.md; layout and
rules: docs/ARCHITECTURE.md "How the page is built"; how-tos: docs/RECIPES.md.
- `web/index.html` = tab bar, panes, `<link css/base.css>`, `<script config.js>` and a bootstrap that fetches site.json /
  feed.json (`window.SITE` / `window.FEED`) and then loads `js/app.js` as `<script type="module">`. 42 lines.
- `web/js/core/` (data, util, load, wake, feed, sysdata, gasdata, colours, chart, flags, table, cmp, router, sources) and
  `web/js/features/{map (+layers/), compare, market, system, flags, data, newsletter}/`. 37 modules, every one with a
  header line saying what it holds. Imports / exports were generated from scope analysis (every free name = import), so
  they are exact; the module evaluation order equals the old script order (`app.js` imports every module in that order)
  and was checked for load-time forward references.
- The former `function main(DATA,FEED){...}` closure is gone: module scope replaces it. Consequence: nothing is a global
  any more (`F`, `S`, `tab()` are not reachable from the console; use the module imports, or `window.GAS` which was
  already exposed).
- Router registry (`core/router.js`): tabs call `registerTab(id,{el,render})`, the map calls `registerMap({paint,pane,goto})`;
  `tab()`, `draw()`, `go()` live there and name no feature. Zero cross-feature imports (`tests/test_modules.py`).
- Only logic edits: `anim`/`paintReq` owned by `map/view.js`; `wakeFarm(f)` in `core/wake.js` sets WTI/WHH (was assigned
  from `heat()` too); `MK` declared in `core/feed.js`; `gasLoad` calls `draw()` instead of `repaint()`+`system()`; the
  Market tab's click handler moved from the System section to `market/market.js`.
- `web/config.js` (git-ignored) replaces the `sed` on `__CARTO_KEY__`: `scripts/build_config.py` writes `window.CFG`
  (cartoKey, builtAt, schema) in hourly.yml and deploy.yml; `tiles.js` reads it and keys the basemap thumbnails.
- Tests: `tests/pagejs.py` (where the page JS lives), `test_page_syntax` (node --check per module; Node 22 in checks.yml),
  `test_modules.py` (import rules, reachability from app.js). Local pixel comparison against the baseline was done with a
  throw-away script; a permanent screenshot-diff assertion in the smoke test is a small follow-up.
- Not done in this step (spec 3): the map-layer contract (`draw/hitTest/legend/needs`), per-feature CSS, long minified
  lines inside the modules (median 130 chars, a few > 1,000: a format-only commit is possible now that the files are small).

## Spec 3 step 3: source and build separated (Oct 4 2026)
- `pipeline/config.py` is the one place that knows the folders: `WEB` (page source), `DATA_STATIC` = `data/static/` (committed
  inputs: site, zones, grid, capture, gas, gie, bathy; `config.static_file(name)`), `BUILD_DATA` = `build/data/` (one run's
  output: feed.json, meta.json, browse/, newsletter/; `config.build_file(...)`), `BUILD/config.js`, `DIST` = `dist/`. All
  twelve writers take their path from it; nothing writes into `web/` any more (`web/data/` is git-ignored as a guard).
- `scripts/build_dist.py` assembles `dist/` = `web/` + `data/static/` (as `data/`) + `build/` (as `data/` and `config.js`);
  `--serve 8000` for a local look. `split_private.py` copies `dist/` to `site_private/` and strips spark from the public
  feed in `dist/` and `build/`. deploy.yml downloads `built-data` into `build/data/`, runs build_config + build_dist, checks
  `dist/` and publishes `dist/`. hourly.yml caches `build/data/{browse,newsletter}` and uploads `build/data/*` as the artifact.
- git: `web/data/{site,grid,zones,capture,gas,gie,bathy.*}` moved to `data/static/` (history kept, `git log --follow`); the
  stale committed `feed.json` removed. The six bot workflows commit to `data/static/` now; deploy.yml also triggers on
  `data/static/**` pushes, hourly.yml ignores them.
- The data store (`store` release) is untouched by this step.
- `scripts/build_meta.py --data` takes several folders (default `build/data data/static`, first hit wins) and writes
  `build/data/meta.json`. `tests/fixtures/make_fixtures.py` reads `data/static/` and `build/data/`.
- Lesson (first deploy after the step had empty Data / Flags / Newsletter tabs): a `from pipeline import config` placed before
  `sys.path.insert(0, ROOT)` works under pytest (repo root on the path) and fails when the script runs from the command line,
  as hourly.yml runs it. Check scripts the way the workflow runs them: `cd /tmp && python <repo>/scripts/<x>.py`.
- Local page work: `python scripts/build_dist.py --serve 8000`; without a pipeline run `dist/data/feed.json` is missing (page
  falls back to synthetic wind), so download the newest `built-data` artifact into `build/data/` for the real thing.

## Spec 3 step 4A: common/ (Oct 4 2026)
- `common/` holds what every back-end package used to borrow from `pipeline/`: `paths.py` (folder layout, moved out of
  `pipeline/config.py`, which re-exports it; `STATE_DIR`, `BUILD_DIR`, `DIST_DIR` env-overridable for Render), `entsoe.py`
  (URL, token, RateLimiter, Client, series parsing, ZONE_EIC, GB_EIC, PSR, price_seq, currency), `fx.py` (data/fx.json, NBU
  UAH, ECB GBP, eur_rate, to_eur), `store.py` (moved from `collector/store.py`; shim left there for one release).
  `pipeline/entsoe.py` keeps the feed-specific parts (COUNTRIES, prices, system, cache) and re-exports the common names.
- `collector/` and `newsletter/` no longer import `pipeline/`; `common/` imports no package; nothing imports `scripts/`
  (`tests/test_packages.py`). `pipeline/` still imports `collector/` (farms, GB live) and `newsletter/` (fuel for spark):
  that is derive using collect, and is resolved by the jobs entrypoints (4B), not by another move.
- Scripts import `from common import paths as config`; `fetch_capture.py` uses `common.entsoe` + `common.fx` (as `FX`, a
  local dict is called `fx`).

## Spec 3 step 4B: jobs entrypoints (Oct 4 2026)
- `jobs/` = `collect`, `derive`, `render`, each a tiny dispatcher (`jobs/_run.py`) that runs the existing module or script
  under `runpy` with the same argv, so behaviour is unchanged; a step either stops the job (exit 1) or is "soft" (logged,
  continue: the Data-tab and newsletter exports in `render tabs`, meta.json in `render site`). `python -m jobs` lists all.
- Every workflow calls these now: hourly = `derive feed` + `render tabs` (background) + `render site`; deploy = `render dist`;
  collect / GB jobs = `collect entsoe|gb-ie|gb-hist|gb-units <mode>`; metrics = `derive metrics [--all]`; newsletter =
  `derive newsletter`; bots = `collect capture|gas|gie|grid|bathymetry|osm-world|extra-turbines|global-turbines|site`.
  The old `python scripts/x.py` and `python -m collector.x` still work (nothing was moved); they are not used by workflows.
- These are the commands Render's cron jobs will run (4D); converting a script into a function called by its job can happen
  one at a time later without touching the workflows again.

## Spec 3 step 4C: store backend for a bucket (Oct 4 2026)
- `common/store.py` has three backends behind the same `Store()` API: `github` (release assets, as before), `s3` (any
  S3-compatible bucket: Cloudflare R2, Backblaze B2, AWS S3) and `local` (STORE_DIR). Chosen by `STORE_BACKEND`, else
  inferred: STORE_DIR -> local, STORE_BUCKET -> s3, otherwise github. S3 settings: `STORE_BUCKET`, `STORE_PREFIX`
  (default `store`), `STORE_S3_ENDPOINT` (R2: `https://<account id>.r2.cloudflarestorage.com`; B2 similar; AWS none),
  credentials `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or `STORE_S3_KEY` / `STORE_S3_SECRET`), `STORE_S3_REGION`
  (default `auto`, what R2 expects). Objects keep the asset names (`<dataset>_<YYYY-MM>.parquet`, the json state files), so
  a bucket is a byte-for-byte copy of the release; the download cache is keyed by ETag (a new upload = a new download).
  An S3 put is atomic, so the `tmp-` upload-rename dance is GitHub-only.
- `tools/store_migrate.py --from github --to s3 [--dry-run | --verify-only | --only ds1,ds2]`: copies what is missing or
  different (size + MD5), never deletes, then reads every Parquet file on both sides and compares row counts (table per
  dataset, exit 1 on any difference). Re-runnable. Run it with GH_TOKEN + the bucket settings once the bucket exists; then
  set `STORE_BACKEND=s3` on Render (and, for the transition, on Actions) so every job reads and writes the bucket.
- Tests: `tests/test_store_s3.py` against a fake S3 (moto): merge, json, cache versioning, migration + verification.
  `boto3` is in requirements-collect.txt; `pull_store.py` still reads the public release (fine while that exists).

## Spec 3 step 4D-E: Render packaging, probes (Oct 4 2026)
- `Dockerfile` (python 3.12-slim + uv + `requirements.lock`, compiled from `requirements.in` = requirements.txt +
  requirements-newsletter.txt; recompile with `uv pip compile requirements.in -o requirements.lock --python-version 3.12
  --upgrade`), `.dockerignore`, `render.yaml` (cron jobs: hourly, collect entsoe auto / daily, metrics, gb-ie, gb-units,
  gb-hist; env var group `gridecon`, secrets `sync: false`), `docs/DEPLOY.md` (what runs where, the one-time setup, the
  variable table, the cutover and rollback). The image could not be built in the cloud session (no Docker daemon);
  `docker-build.yml` builds it on Actions and runs the tests inside it (on Dockerfile / lock changes and by hand).
- `jobs.hourly` = the whole hourly run in one command for Render: state pull, derive feed, tabs (every 3 h, mark in
  state/), render site, `jobs.publish pages`, state push. `jobs/_state.py` mirrors `state/` to `<STORE_PREFIX>-state/` in
  the bucket (STATE_SYNC=1) because Render cron jobs start from an empty machine (the earlier idea of a persistent disk
  does not apply to cron jobs; the bucket does the same job). The 3-hourly tab files ride along in `state/tabs/`.
- `jobs.publish cloudflare` (added later the same day, Erik's hosting decision): `wrangler pages deploy dist` to the public
  Pages project `CF_PAGES_PUBLIC` and `site_private/` to `CF_PAGES_PROJECT` when SPARK=private; node + wrangler are in the
  image; `PUBLISH=cloudflare|pages|both|none` picks the target in `jobs.hourly`. `jobs.publish pages`: zips `build/data` into asset `built-data.zip` of release `built-data` and dispatches `deploy.yml`
  with `source=release`; deploy.yml downloads that instead of the Actions artifact. Needs a fine-grained GH_TOKEN on Render.
- Probes: `scripts/probe_*.py` -> `tools/probes/`; the eleven `probe-*.yml` / `entsoe-probe.yml` replaced by one `probe.yml`
  (workflow_dispatch, input `script`). Logs still land in `data/raw/*/probe*_log.txt`.
- What stays on GitHub after the cutover: deploy.yml, checks.yml, docker-build.yml, probe.yml and the bots that commit
  `data/static/` (capture, gas, grid, osm-world, bathymetry, turbines). Reason: they commit to git and are cheap.

## Spec 3 step 6: dataset registry (Oct 4 2026)
- `data/registry.toml`: `[files."<path>"]` for every file the page loads (patterns `<zone>`, `<day>`), `[datasets.<name>]` for
  every store dataset, `[private.<name>]` for sources that are never stored or served (TTF gas price, manual EUA, ENTSO-E
  grid map, EOX tiles). Each entry: `source`, `publishable`. `common/registry.py` reads it (stdlib `tomllib`).
- `scripts/build_dist.py` gate: after copying, every file under `dist/data` must match a publishable entry, else `dist/` is
  removed, the offenders are listed and the job exits 1 (deploy.yml then stops before publishing: the site keeps the last
  good build). Tests: page files, contract rows and store datasets all registered; the gate refuses an unlisted file.
- Flag changes are decisions (docs/DECISIONS.md). Spark spreads stay the one in-file exception handled by split_private.py.

## Legend toggles and line-end labels (Oct 4 2026, evening; Erik's feature list items 2 and 4)
- `core/chart.js spread()`: labels along one axis keep a minimum gap and stay inside the plot (gap shrinks to fit, font to
  9.5 px below 13 px gap). `core/cmp.js` uses it for the line-end country / zone labels: no more labels above the chart or
  over the legend with 30 countries (System "Compare across countries", Market prices).
- Click a line-end label in a `cmp` chart to hide that series (struck through, dimmed), "show all" at the top right;
  `C.hidden` per chart, in memory. Hover ranking skips hidden series.
- System tab: the technology legend (`.mixleg`) toggles technologies and the load line in the generation mix chart
  (`SYSHIDE`, localStorage `sys-hide`); the y scale follows the visible stack.
- Flags drill-down: every legend chip toggles (`FX.hide`: `tech:<k>`, `load`, `res`, `price`, `nb:<zone>`), the panel
  re-renders through `fxFill`; the flows chart's net position is then the net over the shown borders (labelled). Event
  hours and the caption stay computed on the full series.
- Baseline screenshots for the Market tab updated (label layout).

## System tab: price and residual load on the mix chart, 72 h / 1 wk / 1 mo ranges (Oct 4 2026, items 3 and 1)
- Generation mix chart ("Generation mix, load and price"): residual load as a dashed line, day-ahead price on a right-hand
  axis (the country's zones: first bold, others thin; scale label top right), both toggleable in the legend. Tooltip adds
  the price.
- Range buttons on the selected country's heading: 24 h (the feed, as before, incl. the forecast part of the price card)
  or 72 h / 1 wk / 1 mo from the store export (`core/range.js rangeData()`: `browse/ts/<zone>.json`, hourly means, last 30
  days; a country = the sum of its zones, hours where a zone has no value stay null; flows per neighbour zone excluding the
  country's own borders; prices per zone). The range is loaded on demand and cached for the one country | range pair
  (`RANGE`); the 24 h view is shown with a note while it loads, or when the export has no file for the zone. The detail
  block reads everything through `D.R` (n, labels, prices, now-marker) so the cards do not know which source they draw.
  The country cards and the "Compare across countries" chart stay on the 24 h feed (30+ zone files otherwise).
- `tests/test_page_syntax.py`: `node --check file.js` silently passed a .js file with `import` + a syntax error (Node 22
  module guessing); the test now feeds each file to `node --input-type=module --check` on stdin, which parses for real.

## Map zone colours: periods and new buckets (Oct 4 2026, items 5 and 6)
- "Colour zones by" = metric (day-ahead price, TB2, TB4; wind = onshore + offshore, solar, solar + wind, self-sufficiency =
  generation of all types / load; each technology), the segment below = period (Now, 24 h, Tomorrow for prices, 1 wk, 1 mo,
  1 y). Periods that do not exist for a metric are greyed with a tooltip (tomorrow: prices only; long periods: prices,
  wind, solar, solar + wind, self-sufficiency).
- Now / 24 h / tomorrow come from the feed (prices) and the System data (shares: latest hour, or energy over the 24 h, whole
  country). 1 wk / 1 mo / 1 y come from **`browse/agg.json`** (`build_browse.agg_export`): per zone and window the mean of
  the daily baseload / TB2 / TB4 and the energy ratios wind, solar, vre, self over the window, from `metrics_daily` only
  (tiny file), plus `n_*` day counts (shown in the tooltip). 1 y therefore covers what the metrics table holds (backfill
  from 2024-01 is in the store; the daily metrics follow the metrics job).
- New daily metric `gen_total` (registry VERSION 5, mean hourly generation of all types) for self-sufficiency: run the
  metrics workflow with mode=all once so every past day gets it (until then `self` is empty in agg.json). Done 4 Oct 2026
  22:00: metrics mode=all + `rebuild_tabs`; live agg.json has `self` for all 46 zones, 1 y windows hold ~362 days.
- `zones.js`: MO = metric, MWIN = period; legacy keys now/avg/next/tb2/tb4 still accepted by moSet; `S.moLast` holds the metric.

## Spec 4 steps 1-2: diagnose the drivers in code, then narrate (Oct 5 2026)
Spec: project doc `claude/spec-4-diagnosis-before-narration.md`. The Flags-panel drill-down reasoning is now a function.
- **`newsletter/diagnose.py`** (pure functions on DataFrames, no store / file / web knowledge, so it moves into the collect /
  derive / diagnose / render layout unchanged): `day_frames(hp, ga, hl, hf, day)` -> one frame per zone for the CET day
  (23/24/25 hours; price, load, solar, wind on/offshore, gas, total, net_import, `x|<partner>` per border, residual load);
  `event_hours` mirrors `fxEvents` (TB2/TB4 priciest and cheapest hours, negative hours, residual max/min hour, steepest
  3-hour rise; same tie-breaking as the JS, i.e. ties among the top hours resolve to the later hour); `block_stats` for the
  event hours and the day (price, wind / solar % of consumption, gas share, load, residual load, net import);
  `unusual_rows` = the panel's rule and FXUNU order (`UNUSUAL_ORDER`, keep in step with drilldown.js); `neighbours` from the
  flow columns (price, difference, hours split by > 1 €/MWh, "sent / took N MW", price n/a with the reason, GB = Market
  Index); `drivers` = the rule table; `diagnose(sig, day, frames, scan_rows, fired)` -> dict; `render_text(dict)` -> block.
  `newsletter/zones.py` holds ZONE_NAME (moved out of build.py, shared); `build.ZONE_NAME` / `zn` still importable.
- **Driver rule table** (`diagnose.drivers`, thresholds in `TH`): FIRST VERSION, Cowork's proposal from the spec, not yet
  reviewed by Erik on real days (spec 4 step 0 was skipped at his request to build first). Families: wide spread (priciest
  hours hold the residual-load peak; cheapest hours in the solar / wind peak; wind-poor day; gas share up in the peak;
  imports in the peak / exports in the trough), negative hours (wind + solar share, exports or still importing, low load,
  neighbours below zero, residual minimum), residual peak / minimum (the hour, load, wind share, price then, flows then),
  ramp (load / solar / wind change over the window, price change), import share (top border with its price gap and split
  hours, wind, gas), baseload (gas, wind, solar, load percentiles; neighbours within 10 €/MWh = regional level; net flow),
  capture rate (capture price vs day mean, share of output in the 4 cheapest hours); plus "neighbours also fired" for all.
  Every phrase states co-occurrence; no congestion claims (NTC not in the store); nothing fuel-derived (`spark_*` excluded).
- **Audit rule**: every number in a rendered text is a value of the dict (`diagnose.numbers_in`; `tests/test_diagnose.py`
  parses the text back; dates, clock times and the "(1)" numbering are skipped). Also tested: a 25-hour DST day (25 Oct
  2026, labels 02 / 02′), a missing price hour, late generation, UA-IPS (UAH) and a zone outside the store, GB label,
  TB4 / TB2 event hours reproduce the metric, a tight-evening and a solar-glut day. Real days checked by hand (2-4 Oct):
  the spread in the text equals the flagged TB4 to the euro; RO's late generation is stated, not filled.
- **In the newsletter** (`build.diagnoses`): story candidates = fired signals in the focus zones, no `cr_*` (STYLE.md: no
  daily capture rates) or `spark_*`, one signal per zone (its strongest), top `DIAG_N` = 6 by score. `facts.json` gets
  `diagnoses` (dict + `text` each). `draft_brief`: the headline sentence gets the headline signal's top driver (the open
  STYLE.md item); new block **Why they fired** = the other candidates, one line each (signal, percentile, top driver; else
  the two most unusual context rows; else the data gap). Cost: ~1.5 s per day on top of the ~60 s build.
- **Erik's first review (5 Oct 2026, on the 3 / 4 Oct briefs)**: (a) the two days read identically (same Greece headline, same
  templates); (b) whenever a driver says "imports from Y", say what was happening in Y (wind, solar, or a neighbour exporting
  nuclear). Applied: `build.add_streaks` counts consecutive fired days per (zone, metric, side) over the last 7 days ->
  `streak` on every signal and diagnosis; `draft_brief` prefers the strongest signal that did NOT fire yesterday as the
  headline (`PREFER_NEW`), repeats are marked "3rd day running" / "(P100, 3rd day)". `build.load_day_gen` reads the day's
  unslimmed gen_actual (one day, all production types) -> `day_frames(ga_full=...)` adds `m|<class>` columns (MIX classes =
  the site's technology groups); every neighbour row gets `mix` (event hours), `stats`, `unusual` (its own generation and
  demand rows), and every flow driver names the main counterparty and `_there()`: "mostly from Bulgaria (392 MW); in
  Bulgaria that was nuclear 38 %, solar 22 %, coal and lignite 20 % of generation; its demand (3110 MW) was lower than on
  99 % of its last days". Shares under 10 % are not quoted as the neighbour's story. Result: 3 and 4 Oct now open with
  Serbia / Slovakia import stories, Greece's negative hours read "4th day running".
- Not done (spec 4 steps 3-5): the Flags "Copy context as text" button (export the text into `browse/flags/<day>.json`,
  after or before the page split as Erik decides), the playwright parity test (event hours / unusual rows / neighbours of
  the panel vs the dict), `signals_used` in editorial front matter, the UI check bot.

## Merit order on the Flags drill-down (Oct 5 2026, Erik's idea)
One hour of one zone as a merit curve: block width = actual output of each production type in that hour (ts file
`g|<psr>|gen`), height = the technology's short-run marginal cost, demand = load + exports (dashed), clearing price
(orange). Imports are blocks at the neighbour's price (one per border with net import that hour, border colours `FXNC`);
a neighbour without an EUR price (UA-IPS, zones outside the store) is hatched at the clearing price. Reservoir and pumped
hydro bid opportunity cost: hatched at the clearing price. Blocks sort by cost (ties: `FXMORD`), the caption names the
marginal block (where the demand line falls) and the gap between price and its SRMC ("premium"), or says why none can
be read (demand in an opportunity block; demand beyond the stack = generation or flows missing). Hour selector
(`#fxmh`, `FX.mh`) defaults to the first shaded event hour, else the priciest hour.
- **Costs are fuel-derived, so they are private.** `newsletter/fuel.py` `TECH` + `srmc_table(day, ttf, eua, coal, oil)`:
  per technology eta / emission factor / fuel series; nuclear 10 EUR/MWh fixed, lignite 4 EUR/MWh_th mine-mouth, hard
  coal from `coal_manual.csv` (API2 EUR/t, 6.98 MWh_th/t) and oil from `oil_manual.csv` (Brent EUR/bbl, 1.7 MWh_th/bbl),
  both hand-entered and git-ignored like `eua_manual.csv`; without them those classes carry the carbon part only and are
  drawn hatched ("fuel price missing"). VRE, run-of-river, biomass/waste and "other" are 0 (must-run). Gas = CCGT (55 %);
  the OCGT level is in the table (`gas_peak`) but not a block (ENTSO-E B04 does not split gas plants).
  FIRST VERSION of the parameters: Erik reviews them on real days.
- `pipeline/spark.py` `srmc_days()` writes `feed.market.srmc` = {days: {day: table} for the last 31 days + tomorrow,
  carbon, tech, note}, cached 6 h in `state/srmc_cache.json`; only when the SPARK repo variable is set (same gate as the
  spark spreads). `scripts/split_private.py` strips `market.srmc` with `market.spark` from the public feed;
  `data/registry.toml` lists both under `stripped` and the manual price files under `[private]`.
- The page draws the section only when `MK.srmc.days[<day>]` exists; otherwise one line says the cost levels are on the
  private copy. GB (£/MWh series) gets a note instead. Tooltip per block (`data-mt`, the shared `dtip`).
- Tests: `tests/test_newsletter.py` (srmc_table: carbon-only coal, opportunity hydro, no fuel price leaks), fixture feed
  has a synthetic `market.srmc` (35 EUR/MWh gas, 70 EUR/t EUA; `tests/fixtures/make_fixtures.py srmc_fixture`),
  `tests/e2e/test_smoke.py` asserts the stack, the marginal-block caption and the hour selector at 125 %.
- To see it live: repo variable SPARK = `private` plus the Cloudflare secrets (DEVNOTES "PRIVATE SITE") deploys the
  private copy with costs; SPARK = `public` would put the costs (and so the TTF price de facto) on the public page.
- Not done: imports as wide as the NTC with the used share shaded (needs the NTC dataset); a regional curve for the zones
  whose prices converged that hour; the merit numbers (marginal technology, premium) in the newsletter diagnoses
  (`newsletter/diagnose.py` could reuse `srmc_table` in the fuel-enabled newsletter workflow only).

## Map pane: legacy wind header removed (Oct 5 2026, Erik)
- The right-hand pane of the Map tab no longer has its own region / country selector (`#C`) or the offshore-wind header
  (the big MW figure, "of N MW operating", the farm / future-zone counts) and the region / country / farm list at region
  level: at that level the pane is title, crumb and Layers & legend. The map navigates by clicking zones and farms and by
  the crumb; the tab-bar selector `#C2` (built directly in events.js now) serves the other tabs as before.
- For a selected farm the farm block stays: output and wake loss (`#farmhd`), the turbine details, the PyWake model table
  (`#cmp`), the wake / what-if controls (`#mapctl`) and the farm list of that country (`#list`), toggled in `sidebar()`.
- Fixed on the way: a comment in sidebar.js had swallowed the `#list` display line (dead code since the module split).

## System tab "data 6 h old": our budget, not the TSOs (Oct 5 2026)
- At 14:55 CEST every ENTSO-E country showed "data 6 h old (TSO reports late)". feed.market.diag said why: `entsoe`
  243 s, 17 calls, `skipped: time budget of 240 s used`. The hourly feed's ENTSO-E client spent its 240 s on 17 slow
  calls (~14 s each: ENTSO-E answering slowly or 429-ing the shared runner IP; a 429 retried three times slept 60 s and
  returned None without an error line), `system()` was skipped, and the cached data was re-used with the shift added to
  `lag_h`, which the page labels as the TSO's lateness. Energy-Charts looks fresher because it ingests continuously
  with no such per-run budget.
- Fixed: `stale_h` (this feed could not refetch) is now separate from `lag_h` (the data ends early at the source) and the
  card says "this feed could not refetch ENTSO-E" instead; the offshore model check and `cap24` treat both as not usable.
  `Client` counts `rate_limited` and `slow` calls (feed.market.diag.entsoe), reports a triple 429 as an error, backs off
  5/10/15 s instead of 10/20/30, and the budget is 480 s (ENTSOE_MAX_WALL_S; the job limit is 45 min). `system()` fetches
  the countries with the oldest cache first, so a budget cut hits the freshest ones.
- If the diag keeps showing `rate_limited` > 0: the GitHub runner IPs are shared, so the fix is the Render cutover (own
  IP, continuous collector) rather than more retries.

## Name: Radial Economics (Oct 5 2026, Erik)
- The page is called **Radial Economics** (title, heading, newsletter title "Radial Economics daily", CSV / markdown
  download names). Repo, workflows, Cloudflare projects and the code keep their old names (`energy-infra`,
  `grideconomics` Pages project) until the hosting move; the domain is still to be bought.
- Tab "Compare, ±24 h" is now **Offshore wind** (the PyWake model comparison and farm series; file names unchanged).
- The breadcrumb ("World › Europe › Germany") under the heading is hidden (`#crumb hidden`, Erik 5 Oct 2026); `crumb()`
  still fills it so it can come back with one attribute. Back to World = the ⌂ button on the map.

## Known gaps / next ideas
- Interconnection: hover tooltip with the link name and the 24 h series (already in xflow.json); NTC / capacity to show
  utilisation (and to give the merit order's import blocks their real width); the map's hover hour instead of "latest hour".
- Merit order: review the SRMC parameters (`fuel.TECH`) with Erik; manual coal / oil price files; NTC-wide import
  blocks; regional curve for coupled zones; marginal technology and premium in the newsletter diagnoses.
- Flags drill-down Phase 2: "copy context as text" (spec 4 step 3: the text now exists in `newsletter/diagnose.py`; export it
  per fired signal into `browse/flags/<day>.json` and add the button in `js/features/flags/`), the playwright parity test
  (spec 4 step 4), congestion marker once NTC is in the store, starred story candidates (browser-only).
- Spec 4 driver rule table: review with Erik on real days (which checks, thresholds `diagnose.TH`, wording, how many
  candidates per day); then write the decisions into docs/DECISIONS.md and STYLE.md.
- Spec 3 remaining (step 6): freshness labels on the
  page from meta.json, a screenshot-diff assertion in the smoke test, failure notifications. Spec 2: the cutover itself
  (docs/DEPLOY.md), then `jobs.publish cloudflare` when the public site moves next to the private one.
- Newsletter: decoupling uses daily baseload; add the hourly view (max gap hour) and, once NTC data is in the store,
  whether the border was at its limit. Revisit names for multi-zone countries in tables.
- Neighbour load: one ts file is 90-340 KB raw (~50 KB gzipped); DE-LU opens 11 neighbours. Add `browse/day/<day>.json`
  if that feels slow.
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

## Handover status (Oct 4 2026, 07:00 UTC)
- Store (checked via the release): gb_hist 214 months complete (2009-01..2026-10), unit_output 33 months (from 2024-01, backfill
  state 31 done, last 2026-07, still running every 2 h), da_price Market Index state gbie_mid_state.json 33 months done
  (last 2026-09). No failed Actions runs since Oct 3 16:00 UTC; metrics ran at 06:29 UTC after the GB price landed, so
  GB baseload/TB2/TB4/capture should now be in metrics_daily (not yet looked at on the live site).
- Open check: the daily ENTSO-E collect slot (12:35 UTC) has not fired as "daily" yet (GitHub dropped it on Oct 3;
  collector_log.json only has backfill entries). RO / MK late generation is therefore not yet judged: after the
  first daily run read `late_gen_actual_h`, `seq_dropped`, `n_errors` in collector_log.json; widen the daily window in
  collector/collect.py only if RO lags more than ~3 days.
- Live GB price path (pipeline/gbie_live.py -> market.py) was only tested with mock data; confirm on the live site that
  GB is coloured on the Map and has the line in Market/System. If not, read the hourly-feed log or add a probe.
- Not collected on purpose: National Gas gas flows (licence unclear), Yahoo/yfinance gas (SPARK gating), EnergyDashboard API (terms).
- Next: Flags drill-down Phase 2 (see Known gaps); GB plant layer from unit_output + REPD sites; per-farm capacity
  factors vs PyWake; stability-aware hub-height wind.

## Working from a browser-only session
The code runs on GitHub, not locally. Clone the repo, edit, push to `main`; the workflow runs the pipeline
and redeploys the site in ~3 minutes. Check the run in the Actions tab.

## GB day-ahead price (Elexon Market Index) — added 2026-10-03
- Source: BMRS MID (`collector/gbie.fetch_mid`), APXMIDP volume-weighted (N2EX mostly zero volume). Stored as `da_price`, zone GB, 30 min, currency GBP, src `elexon_mid`. Erik approved it as the GB price.
- Caveats (also on the page): an index of wholesale trades, not an auction result; third-party data outside the BMRS licence (credited); no tomorrow values; MID API limited to 7-day windows.
- GBP→EUR: ECB daily rates in data/fx.json (`pipeline/entsoe.refresh_fx`, run by capture.yml); metrics (`newsletter/metrics.py`) and the live page (`pipeline/market.py`) convert at that rate. GB shows no price until capture.yml has run once.
- History: `python -m collector.gbie mid` (resumable, state gbie_mid_state.json, from BACKFILL_FROM). Then rerun the metrics job for GB baseload/TB2/TB4/capture in metrics_daily.
- Tests: tests/test_gbie.py (da_price, volume weighting), tests/test_gbp_fx.py. build_browse handles per-currency price groups (checked with a synthetic GBP store).
- Map tab (2026-10-03): GB outline added to web/data/zones.json (scripts/build_zones.py, Natural Earth England+Scotland+Wales; Northern Ireland stays in IE(SEM)). The price layer (now / 24 h avg / TB2 / TB4) colours GB from MK.prices.GB (EUR); the legend names the Market Index. Re-run build_zones.py needs `pip install shapely`.
- Basemaps (2026-10-03): added CARTO Light (Positron, borders + city labels), Light without labels, and Dark (CARTO basemaps, © OpenStreetMap contributors © CARTO; free for non-commercial use, attribution shown). @2x tiles on HiDPI. Basemap picker is a 3-column grid. Tiles can't be fetched from the cloud workspace: tested with mocked tiles, check the look on the live site.
