# Development notes

Handover notes for whoever (human or Claude) picks this up next. Keep them current.

## How it runs
- GitHub Actions (`.github/workflows/hourly.yml`) runs `python -m pipeline.run` hourly at :07, on every
  push to `main`, and on "Run workflow". It then deploys `web/` to GitHub Pages.
- `state/` (forecast cache, 24 h history, call counter) lives in the Actions cache, not in git.
- Default forecast source: Open-Meteo, model `ecmwf_ifs` (HRES 9 km) via the /v1/ecmwf endpoint for 100 m wind
  (falls back to /v1/forecast `ecmwf_ifs025`, 10 m wind, if that fails), free
  non-commercial tier (<10 000 calls/day). About 3 requests / 115 locations per refresh, refresh every 6 h.
- PyWake 2.6: Jensen (k 0.04), Bastankhah 2014 (k 0.0324), Niayifar 2016, TurbOPark (Nygaard 2022), plus no-wake.
- Web page is plain HTML/JS in `web/index.html` (no build step). It loads `data/site.json` + `data/feed.json`.
  Map heatmap uses in-browser Jensen/Gaussian; Compare tab uses the PyWake numbers from the feed.

## Decisions so far
- Windy dropped: free key returns shuffled test data (500 calls/day), Professional is €990/yr and has no ECMWF.
- Generic power curve P = rated × (U/U_rated)³, U_rated from rated power and D with Cp 0.45; Ct 0.8 below rated.
  (A first version with (U − cut-in)³ overstated wake losses badly.)
- Farms without turbine positions (37 of 128, mostly DE and NL) use free-stream power × 0.9.
- Outline capacities in the source file are unreliable (e.g. every Hornsea 2 phase lists 1 386 MW);
  installed MW uses turbine count × rated power where turbines exist.
- Wind and output are never on a shared dual axis; separate charts.
- The user's PC folder is on OneDrive: don't create virtual environments there.

## Known gaps / next ideas
- Direction-uncertainty averaging (±5°) for aligned rows (Horns Rev I at 270° gives ~55–70 % loss vs ~40 % measured).
- Farm-to-farm (cluster) wakes: run neighbouring farms together in PyWake.
- Real power/Ct curves per turbine type.
- Turbine positions for the missing German and Dutch farms (EMODnet / operators).
- Inter-array cables, bathymetry layer.
- Validation against actual output: ENTSO-E per country, Elexon per UK farm.
- Price data and cross-border flows (later phase).
- Onshore Denmark with satellite roughness (v2); DK onshore turbine file exists but is not in this repo.

## Working from a browser-only session
The code runs on GitHub, not locally. Clone the repo, edit, push to `main`; the workflow runs the pipeline
and redeploys the site in ~3 minutes. Check the run in the Actions tab.
