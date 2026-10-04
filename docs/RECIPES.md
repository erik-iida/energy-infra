# Recipes

Short, tested procedures for the changes that come up most. Each ends with the checks to run and the docs to update.
Written while doing the thing, so they stay honest: if a recipe does not match the code any more, fix the recipe in
the same push. (Spec 3 step 6; started 4 Oct 2026 with the recipes the page split exercised.)

## Run the checks locally

```
python -m pytest tests -q              # Python tests, data contract, wake-model parity, page syntax, module rules
python -m pytest tests/e2e -q          # browser smoke test: every tab at 125 % and phone width, flags deep link
```
The smoke test serves `web/` with `tests/fixtures/data` as `data/`, so it needs no network and no store. Screenshots
land in `tests/e2e/out/`; `UPDATE_BASELINE=1` rewrites `tests/e2e/baseline/`. To look at the real page locally:
`python scripts/build_dist.py --serve 8000` (page + `data/static/` + whatever is in `build/`; without a pipeline run there is
no `feed.json`, so download the `built-data` artifact into `build/data/` first or run `python -m pipeline.run`). A page
push deploys in ~1 minute (`deploy.yml`); then look at the live site.

## Add a tab

1. Make a folder `web/js/features/<name>/` with one module, say `<name>.js`. Write a `render()` that fills the pane
   from `S` (shared state, `core/data.js`) and the data it loads with `dbJson()` (`core/load.js`).
2. Add the pane to `web/index.html`: `<div id="<pane>"></div>` next to the other panes, and a button
   `<button data-t="<id>">Label</button>` in `#tabs`.
3. At the end of the module: `registerTab("<id>", {el: "<pane>", render});` (import `registerTab` from
   `../../core/router.js`). The router shows the pane and calls `render()` when the tab is opened or the selection changes.
4. Add `import "./features/<name>/<name>.js";` to the list in `web/js/app.js`.
5. Import only from `js/core/` and your own folder. If you need something another feature has, move it to `core/`
   first (that is a separate, pure-move commit).
6. If the tab loads a new data file: add it to `docs/DATA_CONTRACT.md`, `scripts/build_meta.py` SCHEMAS and
   `tests/fixtures/data/` (the contract test fails until all three agree).
7. Checks: both pytest commands above; add the tab id to `TABS` / `PANE` in `tests/e2e/test_smoke.py` so it gets a
   screenshot. Docs: a line in `docs/ARCHITECTURE.md` (folder list) and DEVNOTES.md.

## Move code between modules

- A move and a logic change never share a commit (decision log, 4 Oct 2026).
- Cut the whole top-level declaration, paste it into the target module, then fix imports: every name the moved code
  uses becomes an `import` in the target, every module that used the name imports it from the new place, and the
  `export { ... }` lists on both sides change. `python -m pytest tests/test_page_syntax.py tests/test_modules.py` finds
  missing files and rule breaches; the browser smoke test finds a missing import at run time (console error).
- Watch for module evaluation order: code that runs at load (not inside a function) may only use names from modules
  that are evaluated before it. In practice: keep load-time code in `app.js` or at the end of a feature module.

## Add a map layer

Today a layer is a module under `web/js/features/map/layers/` with its own `load`, `draw`, `hit` and tooltip
functions, called from `features/map/paint.js` and `features/map/events.js` by name. Until the layer contract exists
(planned with the power-plant layer), adding one means: the module, one call in `paint.js` in the right drawing order,
one hit-test call in `events.js`, a legend entry (`LCAT` / `HID` in `features/map/view.js`) and its toggle, and an
attribution line. Then update this recipe with the contract.

## Add a data file the page reads

0. Decide where it lives: slow and committed -> `data/static/` (`config.static_file("x.json")`, refreshed by a bot workflow
   that `git add`s it); generated every run -> `build/data/` (`config.build_file("x.json")`, added to the `built-data`
   artifact list in `hourly.yml`). Never write into `web/`.
1. The writer stamps `"schema": 1` into the file (see `scripts/build_meta.py` for the pattern).
2. Add a row to `docs/DATA_CONTRACT.md` and the file to `SCHEMAS` in `scripts/build_meta.py`.
3. Add a small version to `tests/fixtures/data/` (`tests/fixtures/make_fixtures.py` if it can be derived).
4. Read it in the page with `dbJson("data/<file>")` (or `fetch` for non-JSON). `tests/test_contract.py` checks the
   three places agree.

## Add a daily metric (back end)

One entry in `newsletter/registry.py` plus the function in `newsletter/metrics.py`; bump `registry.VERSION`; run the
`metrics` workflow with mode=all. It then appears in the Data tab, the Flags matrix and the newsletter (details in
DEVNOTES.md "Metric catalogue").

## Add a workflow

Copy the closest one in `.github/workflows/`. Rules that every job follows: `uv pip install --system` for packages,
secrets only through `${{ secrets.X }}` and redacted in logs, a `concurrency` group if it writes to the store, no
writes into `web/` except through the deploy. Note the trigger in `docs/ARCHITECTURE.md` (jobs table) and DEVNOTES.md.
