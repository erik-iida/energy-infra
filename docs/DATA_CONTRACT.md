# Data contract: what the page loads

The page (`web/index.html`) is a static site: it reads files from the relative folder `data/` and nothing else
(no server, no API). This file is the agreement between the **data side** (Python scripts and workflows, the "back
end") and the **page** (the "front end"): which file exists, who writes it, who reads it, which fields the page relies
on, how often it changes and whether it is public.

Rules
- Every file the page fetches is listed here. `tests/test_contract.py` reads the `fetch(...)` / `dbJson(...)` calls in
  `web/index.html` and fails if one is missing from the table below.
- Each JSON file carries a schema version in `data/meta.json` (`files.<name>.schema`); per-run JSON files also carry a
  top-level `"schema"` field. Bump the number when a field the page reads is renamed, removed or changes meaning, and
  update the page in the same push.
- Public means "on GitHub Pages". Only openly licensed data is published: `data/registry.toml` lists every served file
  and every stored dataset with its source and a `publishable` flag, and `scripts/build_dist.py` refuses to build the
  site if a file under `dist/data` is not listed as publishable (`tests/test_registry_files.py`). Private series (spark
  spreads from fuel prices) never enter these files (`scripts/split_private.py`, `--no-fuel`).
- All URLs stay relative (`data/...`): Pages serves the site under `/energy-infra/`.

## Files

| File (under `data/`) | Schema | Written by | Run by / cadence | Read by (tab / feature) | Fields the page relies on | Public |
|---|--:|---|---|---|---|---|
| `site.json` | 1 | `scripts/build_site.py` | osm-world, extra-turbines workflows (when turbine data changes); committed | Map (farms, coast, turbine types), Compare, all tabs at start | `farms[]` (name, country, capacity, turbines, layout, region), `types`, `zones` (future zones), `coast`, `dbox`, `tile` | yes |
| `feed.json` | 1 | `pipeline/run.py` (+ `pipeline/market.py`, `gbie_live.py`); `split_private.py` strips `market.spark` | hourly-feed (each run, ~hourly); **not** committed in practice (the committed copy is stale) | Map (wind, wake, prices, flows, zone colours), Compare, Market, System | `generated`, `source`, `nwp_model`/`windy_model`, `models`, `hours`, `fc_hours`, `farms` (per farm hourly P, U, dir, free/waked), `market.prices`, `market.price_source`, `market.core_zones`, `market.restricted_zones`, `market.farm_zone`, `market.actual_offshore`, `market.fx`, `market.system.<country>` (`series`, `names`, `flows`, `flow_names`, `zones`, `lag_h`) | yes (spark removed) |
| `zones.json` | 1 | `scripts/build_zones.py` | by hand when outlines change; committed | Map zone colours, interconnection layer (borders), DC link ends | `zones.<code>.p` (rings of lon/lat pairs) | yes |
| `capture.json` | 1 | `scripts/fetch_capture.py` | capture workflow, every 3 h; committed by bot | Market (capture prices by technology, monthly) | `months`, `zones.<code>.<month>` (`b` baseload, `h` hours, `t.<tech>` = [capture price, GWh, share at negative prices], `tb2`, `tb4`, `neg`), `names`, `fx` | yes |
| `gas.json` | 1 | `scripts/fetch_gas.py` | gas workflow, daily 09:17 UTC; committed by bot | Map gas layer, System gas cards | `days`, `points[]` (position, type, flows), `countries` | yes |
| `gie.json` | 1 | `scripts/fetch_gie.py` | gas workflow, daily; committed by bot | System (storage, LNG cards) | `storage.<area>`, `lng.<area>` daily series | yes |
| `grid.json` | 1 | `scripts/fetch_grid.py` | grid workflow, monthly; committed by bot | Map HV grid layer, interconnection layer (DC link geometry) | `lines[]` = `[kV (0 = DC), flags, [lon, lat, ...]]` | yes |
| `bathy.json`, `bathy.png` | 1 | `scripts/fetch_bathymetry.py` | bathymetry workflow, on change; committed | Map depth layer | `bbox`, `w`, `h`, `encoding` (+ greyscale PNG) | yes |
| `browse/index.json` | 1 | `scripts/build_browse.py` | hourly-feed, rebuilt every 3 h (cached between) | Data tab | `zones`, `groups`, `vars[]`, `avail.<zone>`, `capacity`, `generated`, `window` | yes |
| `browse/ts/<zone>.json` | 1 | `scripts/build_browse.py` | as above | Data tab, Flags drill-down (zone + neighbours), System tab detail charts for 72 h / 1 wk / 1 mo (`core/range.js`) | `t0`, `step`, `cols[]` (`id`, `name`, `grp`, `tech`, `unit`), `v[][]` | yes |
| `browse/capacity.json` | 1 | `scripts/build_browse.py` | as above | Data tab, capacity view | `classes`, `rows[]` (`gw`, `pk`, `cf`, `zones`), `cf_window`, `peak_window` | yes |
| `browse/flags.json` | 1 | `scripts/build_browse.py` (`newsletter/signals.py`) | as above | Flags tab (latest day) | `day`, `days`, `rules`, `scan[]`, `context_rules`, `context[]`, `focus`, `window_days`, `min_hist`, `hist_days`, `generated` | yes |
| `browse/flags/<day>.json` | 1 | `scripts/build_browse.py` | as above, last 14 days | Flags tab (Day selector, deep links) | as `flags.json` | yes |
| `browse/xflow.json` | 1 | `scripts/build_browse.py` | as above | Map interconnection layer | `pairs[]` = `[zone a, zone b, latest hour (epoch s), net MW a->b, last 24 h]` | yes |
| `newsletter/index.json` | 1 | `scripts/build_newsletter_site.py` | hourly-feed, every 3 h with the browse export | Newsletter tab | `latest`, `days[]` (`day`, `source`), `repo` | yes |
| `newsletter/<day>.md` | — | `scripts/build_newsletter_site.py` (or `newsletter/editorial/<day>.md` by hand) | as above, last 3 days | Newsletter tab | Markdown text with fixed section headings and two tables | yes |
| `meta.json` | 1 | `scripts/build_meta.py` | hourly-feed, every run, before deploy | not read by the page yet (planned "data N h old" labels) | `built`, `files.<name>` (`schema`, `bytes`, `generated` / `last_data`) | yes |

## Outside this contract
- Basemap tiles (CARTO, OpenStreetMap, EOX), terrain tiles: fetched directly from those hosts, credited on the map.
- The CARTO key is written into `index.html` at deploy from the `CARTO_KEY` Actions secret (it is client-side by nature).
- `site_private/` (login-protected copy with spark spreads) is produced by `split_private.py` and never deployed to Pages.
