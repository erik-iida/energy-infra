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

## Known gaps / next ideas
- Direction-uncertainty averaging (±5°) for aligned rows (Horns Rev I at 270° gives ~55–70 % loss vs ~40 % measured).
- Farm-to-farm (cluster) wakes: run neighbouring farms together in PyWake.
- Inter-array cables, bathymetry layer.
- Validation per farm: Elexon (UK, per BM unit) and ENTSO-E per unit; country-level check vs Energy-Charts is in the Market tab.
- Product thinking: capture-price discount and wake-cost analytics per farm/zone are the most commercial part so far.
- Price data and cross-border flows (later phase).
- Onshore Denmark with satellite roughness (v2); DK onshore turbine file exists but is not in this repo.

## Working from a browser-only session
The code runs on GitHub, not locally. Clone the repo, edit, push to `main`; the workflow runs the pipeline
and redeploys the site in ~3 minutes. Check the run in the Actions tab.
