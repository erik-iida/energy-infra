# Decision log

One line per structural decision: date, what, why, alternatives, who decided. Structural changes (a new folder, a
rename, a deleted file group, a changed workflow trigger) need Erik's go-ahead and an entry here (spec 3).

| Date | Decision | Why | Alternatives considered | Decided by |
|---|---|---|---|---|
| 2026-10-04 | Front end split into components with native ES modules (`<script type="module">`), one folder per tab/feature; no framework, no bundler, no front-end build step | Plain HTML/JS, hostable anywhere, fewest moving parts | Preact or lit later, only for Flags drill-down / Data tab if hand-written DOM updates become the problem | Erik (kickoff, spec 3 default 1) |
| 2026-10-04 | No rewrites while moving code: a move and a logic change never share a commit | Any visual change can be traced to one cause | — | Erik (default 2) |
| 2026-10-04 | Keep package names `pipeline/`, `collector/`, `newsletter/`; add `common/` for shared code; renaming waits for spec 2's collect / derive / render refactor | Rename once, not twice | Rename now | Erik (default 3) |
| 2026-10-04 | `dist/` is the build output (git-ignored): `web/` + `data/static/` + built data + `config.js`; `dist/` is what gets deployed | `web/` holds only hand-written source | Keep deploying `web/` | Erik (default 4) |
| 2026-10-04 | Fast deploy takes its data from the hourly run's Actions artifact `built-data` (last successful run) | No extra infrastructure; fallback is a release asset | Release asset; worker (spec 2) from the start | Erik (default 5) |
| 2026-10-04 | Public site content unchanged during the restructuring (`--no-fuel` / `SPARK` rules stay, no new public data) | Restructuring must not change what is published | — | Erik (default 6) |
| 2026-10-04 | Order of work: step 0 (done) → step 1 safety net → step 5 fast deploy → step 2 split `index.html` → step 3 source/build → step 4 with spec 2 → step 6 | Step 0 showed the delay is the full pipeline on every push (median ~6, p90 ~17 min), not queueing; the fast deploy speeds up every later step | Spec order: steps 0–3, 4 with spec 2, 5 last | Erik (default 7, changed after step 0) |
| 2026-10-04 | Folder names as in spec 3's target layout: `web/css`, `web/js/core`, `web/js/features/<feature>`, `common/`, `tools/probes/`, `data/static/`, `docs/`, `tests/fixtures`, `tests/e2e`, `dist/` | — | — | Erik (kickoff) |

## Spec 3 step 5: fast deploy (4 Oct 2026)
| Decision | Choice |
|---|---|
| Page-only pushes (`web/`, `docs/`, `tests/`, `*.md`) | `deploy.yml` only (~1 min), no pipeline |
| Bot commits from data jobs (capture, gas, grid, osm-world, bathymetry, turbines) | `deploy.yml` only (Erik, 4 Oct) |
| Deploy concurrency | one group `pages-deploy`; deploys wait instead of cancelling each other (Erik, 4 Oct) |
| Data handed from build to deploy | `built-data` artifact, 3 days, **public files only** (spark stripped before upload: artifacts of a public repo are downloadable by any GitHub user) |
| Private Cloudflare site | still deployed by the hourly build job only (page-only pushes reach it at the next hourly run) |
| Follow-ups | 5b fewer API calls, 5c remove market_history.json: separate pushes after the deploy is verified |

Rollback: delete `.github/workflows/deploy.yml`; in `hourly.yml` remove `paths-ignore`, restore the `workflow_run` list
(gas, grid, osm-world, bathymetry, global-turbines, extra-turbines, capture) and the Pages steps at the end of the job.

## Spec 3 step 5b: market data source (4 Oct 2026)
| Decision | Choice |
|---|---|
| Hourly feed market source | ENTSO-E only (Erik). Energy-Charts failed from GitHub runners most hours and cost ~50 s per run |
| Countries on the System tab | 30, all ENTSO-E; DK / NO / SE summed over bidding zones |
| PyWake | results cached per farm-hour while inputs are unchanged |
| GIE | incremental 14-day download, weekly full refresh |

## Spec 3 step 2: split `index.html` into components (4 Oct 2026)
Erik gave the go-ahead for the whole step at once (backup copy of the repo made first). Six pushes, each checked with the
Python tests, the browser smoke test and a pixel comparison of the 15 baseline screenshots (125 % and phone width): all
identical to before.
| Decision | Choice |
|---|---|
| CSS | one `web/css/base.css` for now; per-feature CSS files only if that proves useful |
| The former `main(DATA, FEED)` closure | dissolved: the page script became page-level code, then 32 files, then ES modules |
| Module conversion | generated from scope analysis (every free name becomes an import, every name used elsewhere an export); evaluation order kept equal to the old script order and checked for forward references |
| Four variables written from another file | one owner each: `anim`/`paintReq` in `map/view.js`, `wakeFarm()` in `core/wake.js`, `MK` in `core/feed.js` (the only logic edits of the split) |
| Cross-feature imports (25 after the mechanical cut) | removed by moving shared code to `core/` (feed aggregation, system data, gas data, chart helpers, colour ramps, sortable tables, `go`/`draw`) and a Market click handler that sat in the System section back to `market/` |
| Tab interface | `registerTab(id, {el, render})` and `registerMap({paint, pane, goto})` in `core/router.js`; the router names no feature. A fuller `mount / unmount` was not needed: panes are static elements in `index.html` |
| Map-layer contract (`draw / hitTest / legend / needs`) | deferred to the next layer (power plants): it is a logic change, not a move |
| CARTO key | `web/config.js` (`window.CFG`, generated by `scripts/build_config.py`, git-ignored) replaces the `sed` on `index.html` in both workflows |
| CI | `checks.yml` on Node 22 (ES modules in `.js` files parse without flags); `tests/test_modules.py` enforces the import rules |

## Spec 3 step 3: source and build separated (4 Oct 2026)
Erik approved the step as proposed (including deleting tracked files from `web/data/`; the data store is not affected).
| Decision | Choice |
|---|---|
| Committed page inputs | moved `web/data/{site,grid,zones,capture,gas,gie}.json`, `bathy.png/.json` to `data/static/` (git history kept) |
| Stale committed `feed.json` | removed from git; built every hour into `build/data/` |
| Generated files | `build/` (git-ignored): `data/feed.json`, `data/meta.json`, `data/browse/`, `data/newsletter/`, `config.js` |
| Deployed site | `dist/` (git-ignored) assembled by `scripts/build_dist.py` from `web/` + `data/static/` + `build/`; Pages and the private copy serve `dist/` |
| Paths | one module (`pipeline/config.py`: `WEB`, `DATA_STATIC`, `BUILD_DATA`, `DIST`, `static_file()`, `build_file()`); no script spells out an output folder |
| Bot workflows | capture, gas, grid, osm-world, bathymetry, extra-turbines commit to `data/static/`; deploy.yml triggers on `data/static/**`; hourly.yml ignores it |
| Rollback | revert the commit (restores files and workflows); re-run the bots |

## Spec 3 step 4: back-end packages, jobs, bucket, Render (4 Oct 2026)
Erik: go ahead; repo goes private once the back end runs on Render; bucket vendor and public host undecided (R2 and
"keep Pages for now" recommended); probes folded into one workflow; caches: Claude to decide (bucket, see below).
| Decision | Choice |
|---|---|
| Shared back-end code | `common/` (paths, ENTSO-E client, FX, store); `collector/` and `newsletter/` no longer import `pipeline/`; `pipeline/` may still import `collector/` and `newsletter/` (tested) |
| Entrypoints | `jobs.collect / derive / render` (+ `jobs.hourly`, `jobs.publish`), running the existing code via runpy; every workflow calls them; old commands kept |
| Store backend | `STORE_BACKEND=github|s3|local`, S3-compatible so the vendor stays open; `tools/store_migrate.py` with row-count verification |
| Caches on Render | mirrored to the bucket (`<prefix>-state/`), not a persistent disk: Render cron jobs start empty and have no disk |
| Publishing from Render | release asset `built-data.zip` + dispatch of `deploy.yml` (`source=release`); GitHub Pages kept for now; Cloudflare Pages target later |
| What stays on GitHub | deploy, checks, docker-build, probe, and the bots that commit `data/static/` |
| Probes | `tools/probes/` + one `probe.yml` (eleven workflows removed) |
| Dependencies | `requirements.lock` (uv compile of requirements.in) for the image; workflows keep the per-area files until the cutover |

