# Running the back end on Render (and what stays on GitHub)

Plain-language guide for the cutover planned for October 2026. Written 4 Oct 2026 with spec 3 step 4; the code side is
done, the accounts and settings are Erik's to create. Nothing here is needed while everything still runs on GitHub Actions.

## The picture after the cutover

```
 Render (cron jobs, Docker image from this repo)         GitHub (private repo)
 ------------------------------------------------         ---------------------------------------------
 hourly:   python -m jobs.hourly                          deploy.yml   publishes dist/ to Pages (1 min), dispatched by
           forecast -> PyWake -> market/system ->                      jobs.publish or by a page push
           feed.json, tabs, dist/, publish                checks.yml   tests on every push
 2-hourly: python -m jobs.collect entsoe auto             slow bots    capture (3 h), gas (daily), grid, osm-world,
 daily:    collect entsoe daily, derive metrics,                       bathymetry, turbines: they commit data/static/
           collect gb-ie / gb-units / gb-hist                          (a few minutes a day, inside the free allowance)
                      |                                                  ^
                      v                                                  |
            bucket (S3 API): store/ = the history database,  <----- built data handed over as a release asset
                            store-state/ = caches between runs
```

Why this split: the hourly feed and the collectors are what burn Actions minutes (~24,000 a month, DEVNOTES "Spec 3 step
0"); they move. The jobs that *commit files to git* (the static map inputs) stay on GitHub because a Render job has no
business pushing commits, and they are cheap. The deploy stays on GitHub because that is where Pages is.

## Before the cutover (one-time)

1. **Bucket.** Create one (Cloudflare R2 recommended: same account as the private site; Backblaze B2 or AWS S3 work the
   same way). Note: bucket name, S3 endpoint URL, an access key + secret with read/write on that bucket.
2. **Copy the history** from the GitHub release to the bucket, from any machine with `gh` logged in:
   ```
   export STORE_BUCKET=... STORE_S3_ENDPOINT=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
   python tools/store_migrate.py --from github --to s3 --dry-run     # lists what would be copied
   python tools/store_migrate.py --from github --to s3               # copies, then checks every file's row count
   ```
   Re-run it just before switching; it only copies what changed. (It can also run as a GitHub Actions step if no
   machine has `gh`: ask for a one-off workflow.)
3. **GitHub token for publishing.** Settings > Developer settings > Fine-grained tokens: this repository only,
   permissions Contents: read and write, Actions: read and write. This is `GH_TOKEN` on Render; it lets `jobs.publish`
   upload the built data and start `deploy.yml`. It is never printed.
4. **Render.** New > Blueprint, pick this repo; Render reads `render.yaml` and asks for the values marked `sync: false`:
   `STORE_BUCKET`, `STORE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ENTSOE_TOKEN`, `GIE_KEY`,
   `GH_TOKEN`, `CARTO_KEY`. Same values as the GitHub secrets of the same name (Erik copies them; never paste them in chat).
   Region Frankfurt (closest to the data sources and to you).

## Environment variables (names only)

| Variable | Used by | Meaning |
|---|---|---|
| `STORE_BACKEND` | everything that reads or writes history | `s3` on Render; `github` (default) on Actions until the switch; `local` with `STORE_DIR` for a copy on a laptop |
| `STORE_BUCKET`, `STORE_PREFIX`, `STORE_S3_ENDPOINT`, `STORE_S3_REGION` | s3 backend | bucket name, folder inside it (`store`), endpoint URL (R2 / B2 need it), region (`auto` for R2) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | s3 backend | the bucket's access key (any S3-compatible provider uses these names) |
| `STATE_SYNC` | `jobs.hourly` | `1` = mirror `state/` (forecast, wake, ENTSO-E caches, 3-hourly tab files) to `<prefix>-state/` in the bucket, because a Render cron job starts from an empty machine |
| `STATE_DIR`, `BUILD_DIR`, `DIST_DIR`, `STORE_CACHE` | all jobs | scratch folders (set in the Dockerfile; no need to change) |
| `ENTSOE_TOKEN`, `GIE_KEY` | collect, derive feed | API keys |
| `WM_SOURCE`, `WM_OPENMETEO_MODEL`, `WM_DAILY_CALL_CAP` | derive feed | forecast source settings (same as the Actions variables) |
| `ENTSOE_PER_MIN`, `COLLECT_PER_MIN` | feed / collector | ENTSO-E rate budget per process (400/min is the API limit for both together) |
| `BACKFILL_FROM` | collectors | first month of the history (`2024-01`) |
| `COLLECT_FARMS` | derive feed | `1` = write farm wind and wake output to the store |
| `GITHUB_REPOSITORY`, `GH_TOKEN` | `jobs.publish` | where to hand the built data and start the deploy |
| `CARTO_KEY` | render site | basemap key, ends up in `config.js` |
| `SPARK` | render site | spark spreads: empty (off), `private` (login site only), `public` |

## The cutover, step by step (spec 2's migration plan)

1. Bucket created, history copied and verified (above).
2. **Run both for a few days.** Approve the blueprint on Render while the GitHub schedules keep running. Both write to
   their own store (GitHub release vs bucket); compare the site data: `jobs.hourly` on Render publishes through
   `deploy.yml source=release`, the Actions run through the artifact, so whichever ran last is live. Watch the Render job
   logs (Render shows them in the dashboard) and `data/meta.json` on the site (`built` time, per-file `last_data`).
3. **Switch the store on Actions too** (repository variables `STORE_BACKEND=s3` + the bucket secrets) or disable the
   Actions schedules: in `hourly.yml`, `collect.yml`, `collect-gb*.yml`, `metrics.yml` comment out the `schedule:` block
   (keep `workflow_dispatch` for manual runs). From then on the bucket is the only store. Run `store_migrate --verify-only`
   once more first.
4. **Repo private.** Settings > General > Danger zone > Change visibility. Before that: Pages from a private repo needs
   GitHub Pro (or move the public site to Cloudflare Pages like the private copy: `wrangler pages deploy dist`; then
   `jobs.publish` gets a `cloudflare` target). The remaining Actions minutes (deploy ~1 min per run, the bots) fit the
   2,000 free minutes; check Settings > Billing after the first week.
5. Rollback at any point: re-enable the Actions schedules, set `STORE_BACKEND` back to `github`; the release still holds
   the history up to the switch, and `store_migrate --from s3 --to github` copies newer months back.

## Day-to-day on Render

- `python -m jobs` in any job's shell lists the commands; each cron job runs one of them.
- A failed job shows red in the Render dashboard and can send an e-mail (Render > Account > Notifications). The site
  keeps the last good data: `deploy.yml` refuses an incomplete build.
- Logs: Render keeps them per run; they are readable there (unlike Actions logs from the cloud session).
- Costs: cron jobs are billed per run-minute of the instance plan; the hourly job is ~3-5 min, the collectors ~2-5 min
  every two hours, plus the bucket (a few hundred MB). Check the Render and bucket invoices after the first month and
  write the numbers into DEVNOTES.
