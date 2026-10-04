# How GridEconomics is put together

A plain-language map of the project: where the numbers come from, how they become files, and how the page turns
those files into tabs. Kept current with every structural change (spec 3). Last update: 4 Oct 2026 (page split into modules; source and build separated).

## The short version

GridEconomics is a **static website**: GitHub Pages serves one HTML page plus a folder of data files. There is no server
that computes anything when you open the site. All the work happens beforehand, in **GitHub Actions** (scheduled jobs on
GitHub's machines), which fetch data from public sources, compute what the page needs and save it as files. The page
then only reads those files and draws them.

So there are two halves:

- **Back end** (Python, in `pipeline/`, `collector/`, `newsletter/`, `scripts/`): fetches and computes. Runs on GitHub
  Actions on a timetable.
- **Front end** (`web/`: `index.html` as the shell, `css/base.css`, one JavaScript module per feature under `js/`): shows.
  Runs in your browser.

The **data contract** (`docs/DATA_CONTRACT.md`) is the list of files between the two halves.

## Diagram

```mermaid
flowchart LR
  subgraph Sources["Public data sources"]
    OM["Open-Meteo / ECMWF\nwind forecasts"]
    EC["Energy-Charts\nprices, generation (DE, FR, NL, ...)"]
    EN["ENTSO-E Transparency\nprices, generation, load, flows"]
    EL["Elexon BMRS, EirGrid\nGB / IE"]
    GS["ENTSOG, GIE\ngas flows, storage, LNG"]
    GEO["OpenStreetMap, PyPSA-Eur,\nEMODnet, Natural Earth\nturbines, grid, depth, borders"]
  end

  subgraph Jobs["GitHub Actions jobs (back end)"]
    H["hourly-feed\npipeline.run: forecast -> PyWake wake model\n-> market + system data"]
    C["collect (+ GB jobs)\nraw history into the data store"]
    M["metrics\ndaily metrics into the store"]
    B["build_browse / newsletter\n(inside hourly-feed, every 3 h)"]
    S["slow jobs\ncapture, gas, grid, osm-world,\nturbines, bathymetry"]
  end

  ST[("Data store\nParquet files on the\n'store' GitHub release")]

  subgraph Files["data/ files (the contract)"]
    F1["feed.json"]
    F2["browse/*  newsletter/*"]
    F3["site.json grid.json zones.json\ncapture.json gas.json gie.json bathy.*"]
  end

  subgraph Page["web/ (front end: one module per tab)"]
    T1["Map"] --- T2["Compare"] --- T3["Market"] --- T4["System"] --- T5["Flags"] --- T6["Newsletter"] --- T7["Data"]
  end

  OM --> H
  EC --> H
  EN --> H
  EL --> H
  EN --> C
  EL --> C
  C --> ST
  ST --> M --> ST
  ST --> B
  H --> F1
  B --> F2
  GS --> S
  GEO --> S
  EN --> S
  S --> F3
  F1 --> Page
  F2 --> Page
  F3 --> Page
```

## How data gets from a source to a tab (examples)

- **Romania's day-ahead price on the Map**: ENTSO-E publishes it -> `hourly-feed` (`pipeline/market.py`, `entsoe.py`)
  fetches it every hour -> `feed.json` `market.prices.RO` -> the page colours Romania on the map and draws its line in
  Market.
- **A Flags signal**: ENTSO-E prices and generation -> `collect` stores them in the data store every 2 h ->
  `build_browse.py` (inside `hourly-feed`, every 3 h) computes the daily metrics and percentiles (`newsletter/metrics.py`,
  `signals.py`) -> `browse/flags.json` and `browse/ts/RO.json` -> the Flags tab and its drill-down panel.
- **Wake losses of an offshore farm**: Open-Meteo / ECMWF wind -> `pipeline/run.py` runs PyWake for each farm ->
  `feed.json` `farms` -> Map and Compare. The map's live "what-if" wake drawing uses JavaScript copies of the same
  PyWake formulas (checked against PyWake by a test).
- **Capture prices**: ENTSO-E generation and prices -> `capture` job every 3 h -> `capture.json` (committed by a bot)
  -> Market tab.

## The jobs (workflows)

| Job | When | What it does |
|---|---|---|
| hourly-feed | every hour (:07, :37), on every push, after the data jobs | forecasts, PyWake, market and system data -> `feed.json`; every 3 h also the Data / Flags / Newsletter files; then publishes the site |
| collect | every 2 h + daily 12:35 UTC | ENTSO-E raw history into the data store |
| collect-gbie / gbhist / gbunits | every 2–6 h | GB and Ireland data into the store |
| metrics | after collect, daily 13:10 UTC | daily metrics into the store (`metrics_daily`) |
| capture | every 3 h | capture prices -> `capture.json` |
| gas | daily | ENTSOG and GIE -> `gas.json`, `gie.json` |
| grid, bathymetry, osm-world, turbines | monthly / on change | map layers -> `grid.json`, `bathy.*`, `site.json` |
| checks | every push | page syntax, Python tests, browser smoke test, code tidiness (no deploy) |

## Where things live

| Folder | What |
|---|---|
| `web/` | the page: `index.html` (shell + bootstrap), `css/base.css`, `js/core/` (shared), `js/features/<feature>/` (one folder per tab or map layer). Source only; nothing writes here |
| `data/static/` | committed inputs the page reads: `site.json`, `zones.json`, `grid.json`, `capture.json`, `gas.json`, `gie.json`, `bathy.*` (refreshed by bot workflows) |
| `build/` | not committed: what one run generates (`data/feed.json`, `data/browse/`, `data/newsletter/`, `data/meta.json`, `config.js`); uploaded as the `built-data` artifact |
| `dist/` | not committed: the assembled site = `web/` + `data/static/` + `build/`, made by `scripts/build_dist.py`; this is what GitHub Pages (and the private copy) serve |
| `pipeline/` | the hourly job: forecasts, wake model, market and system data |
| `collector/` | the data store and the collectors that fill it |
| `newsletter/` | daily metrics, signal rules (Flags), the newsletter draft |
| `scripts/` | one-off and scheduled data jobs, probes |
| `tests/` | Python tests, test data (`tests/fixtures/data/`), browser smoke test (`tests/e2e/`) |
| `docs/` | this page, the data contract, the decision log |
| `.github/workflows/` | the jobs above |

## From folders to the served site

```
web/            data/static/        build/                 (hourly job, or the built-data artifact)
index.html      site.json           data/feed.json
css/ js/        zones.json grid.json  data/browse/  data/newsletter/  data/meta.json
                capture.json gas.json  config.js
                gie.json bathy.*
      \               |                 /
       +--- scripts/build_dist.py ------+
                       |
                     dist/   index.html  css/  js/  config.js  data/{site,feed,zones,...}.json  data/browse/ ...
                       |
            GitHub Pages (public)   +   site_private/ (Cloudflare, with the spark spreads)
```
`pipeline/config.py` is the one place that knows these folders (`WEB`, `DATA_STATIC`, `BUILD_DATA`, `DIST`); every writer
takes its output path from there. The page itself only ever asks for `data/<file>` relative to its own URL, so it does
not know or care where a file came from.

## How the page is built (front end)

`index.html` holds only the tab bar, the panes and a small bootstrap that loads `data/site.json` and `data/feed.json`
and then `js/app.js`, the one entry module. Everything else is an **ES module**: a file that states at the top what it
needs from other files (`import`) and at the end what it offers (`export`). The browser loads them itself; there is no
build step or framework.

```
web/js/core/        shared by everyone
  data.js           site data, feed, shared state S (selected country, farm, tab, ...)
  feed.js           the 48-hour time axis, per-farm wind and PyWake series, market block MK, farm aggregation
  sysdata.js        System data per country (generation mix, load, flows), technology groups and colours
  gasdata.js        gas data (ENTSOG), loaded once on demand
  wake.js           in-browser wake models (must match pipeline/wake.py; tested)
  chart.js colours.js table.js cmp.js   SVG chart helpers, colour ramps, sortable tables, the many-series line chart
  flags.js          country flags and the country picker
  router.js         tab(t), draw(), go(country, farm); tabs and the map register themselves here
  load.js util.js sources.js            JSON loading, $ / formatting, the folded "Sources and notes"
web/js/features/
  map/              canvas + projection, tiles, paint, side pane, events, and layers/ (gas, grid, dc, interconnection, bathy, zones)
  compare/ market/ system/ flags/ data/ newsletter/   one folder per tab
web/js/app.js       imports every module in order and runs the start-up code
```

Rules (checked by `tests/test_modules.py`): a feature imports only from `core/` and its own folder, never from another
feature; `core/` never imports a feature; every module is reachable from `app.js`. A tab is a folder that calls
`registerTab("id", {el: "<pane id>", render})`; the map calls `registerMap({paint, pane, goto})`. The router draws
whichever is active and knows no tab by name, so adding a tab touches one new folder plus one line in `app.js`.

Settings that differ per deploy (the CARTO basemap key, build time, schema versions) come from `web/config.js`, written
by `scripts/build_config.py` at deploy time and never committed. Without it the page still works (keyless basemaps).

## Known weak spots (being addressed in spec 3)

- The map's layers do not yet share one `draw / hitTest / legend` contract; planned with the next layer (power plants).
