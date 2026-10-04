# Going private: the public site on Cloudflare Pages, the back end on Render

Plain-language guide for the cutover (Erik's decision, 4 Oct 2026: website off Cloudflare, hourly API calls and site build
off Render, GitHub repo private). The code side is done; the accounts and settings are Erik's to create. Nothing here is
needed while everything still runs on GitHub Actions. Steps marked **you** need your accounts; **me** = done from a chat.

## The picture after the cutover

```
 Render (cron jobs, Docker image built from this repo)        Cloudflare
 ---------------------------------------------------------     --------------------------------------------------
 hourly:   python -m jobs.hourly                               Pages project <public>:  the site (gridecon.pages.dev
           forecast -> PyWake -> market/system -> feed.json,                            or your own domain)
           tabs every 3 h, dist/, publish ------------------>  Pages project <private>: full copy incl. spark spreads,
 2-hourly: jobs.collect entsoe auto                                                     behind Cloudflare Access
 daily:    collect entsoe daily, derive metrics,               R2 bucket:  store/        the history database (Parquet)
           collect gb-ie / gb-units / gb-hist                              store-state/  caches between runs
                      |                                                     ^
                      +-----------------------------------------------------+
 GitHub (private repo)
 ---------------------------------------------------------
 code; checks.yml on every push; docker-build.yml; probe.yml; the slow bots that commit data/static/ (capture 3 h, gas
 daily, grid, osm-world, bathymetry, turbines; they read the same R2 bucket). deploy.yml stays as a fallback only.
```

Why this split: the hourly feed and the collectors burn Actions minutes (~24,000 a month, DEVNOTES "Spec 3 step 0") and
move to Render. Jobs that *commit files to git* stay on GitHub (a Render job should not push commits) and are cheap. The
site moves to Cloudflare because GitHub Pages from a private repo needs a paid plan and Cloudflare does not care; the
login-protected copy is already there.

## 1. You: Cloudflare (~20 min)

1. **R2 bucket** for the history: R2 -> Create bucket, name e.g. `gridecon-store`, location hint EU. Then R2 -> Manage R2
   API tokens -> Create: permission Object Read & Write, scoped to that bucket. Note four values: bucket name, the S3 API
   endpoint shown on the bucket page (`https://<account id>.r2.cloudflarestorage.com`), Access Key ID, Secret Access Key.
2. **Pages project for the public site**: Workers & Pages -> Create -> Pages -> *Direct Upload* (not "connect to Git"),
   name e.g. `gridecon`. It answers at `gridecon.pages.dev`; add your own domain under Custom domains whenever you like.
   The first upload comes from Render (step 3); the dashboard may ask for a first manual upload to finish creating the
   project: upload any single small file, it is replaced at the first real deploy.
3. **API token**: the `CLOUDFLARE_API_TOKEN` you created for the private site works if it has *Cloudflare Pages: Edit* on
   the account; otherwise My Profile -> API Tokens -> Create, with exactly that permission. Note it and the Account ID
   (Workers & Pages overview, right-hand side).

## 2. You: Render (~15 min)

New -> Blueprint -> connect the GitHub repository (Render asks for GitHub access; grant it for this repo only). Render reads
`render.yaml`, builds the image (~5 min, node + wrangler included) and asks for the values marked `sync: false`:

| asked for | what to enter |
|---|---|
| `STORE_BUCKET`, `STORE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the four R2 values |
| `CF_PAGES_PUBLIC`, `CF_PAGES_PROJECT` | the Pages project names (public, private copy) |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | from step 1.3 |
| `ENTSOE_TOKEN`, `GIE_KEY`, `CARTO_KEY` | the same values as the GitHub secrets of those names (copy them; never paste them in chat) |

Approve. The cron jobs appear with their schedules; nothing meaningful runs until the bucket has the history (step 3).
Region Frankfurt. Render bills cron jobs per run-minute of the instance; the hourly job is ~3-5 min, the collectors 2-5 min
every two hours, plus the bucket (a few hundred MB). Write the first invoice into DEVNOTES.

## 3. Together: copy the history, run side by side (2-3 days)

- **me**: run `tools/store_migrate.py --from github --to s3` as a one-off Actions workflow (so no machine of yours is
  involved), with the R2 values added as GitHub secrets (`STORE_BUCKET`, `STORE_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`) by you first. It copies every monthly file and prints a row-count table per dataset.
- **you**: Render dashboard -> gridecon-hourly -> Trigger run. **me**: read its log, open the Pages address.
- From then on both run: GitHub publishes to `erik-iida.github.io/energy-infra` from the GitHub release store, Render to
  `gridecon.pages.dev` from the bucket. Same inputs, two addresses; compare `data/meta.json` (`built`, per-file
  `last_data`) on both for a couple of days. Both collectors write their own store; the bucket is re-synced at the switch.

## 4. You, with me watching: the switch (10 min)

1. GitHub -> Settings -> Secrets and variables -> Actions: variable `STORE_BACKEND=s3` (the R2 secrets from step 3 are
   already there). The remaining GitHub jobs (the bots) now read and write the bucket. **me**: `store_migrate --from github
   --to s3` once more (fills the days collected since step 3), then comment out the `schedule:` blocks in `hourly.yml`,
   `collect.yml`, `collect-gb*.yml`, `metrics.yml` (manual runs stay possible).
2. One day on Render alone; `store_migrate --verify-only` as the last check.
3. **Update the link you share** (LinkedIn etc.) to `gridecon.pages.dev` or your custom domain. Then GitHub -> Settings ->
   Pages -> disable: the old `erik-iida.github.io/energy-infra` address stops working here.
4. GitHub -> Settings -> General -> Danger zone -> Change visibility -> Private. From now on the code, the release and the
   Actions logs are yours only.

## After the switch

- **Actions minutes**: 2,000 free a month on a private repo. What stays (capture every 3 h, gas daily, grid monthly,
  checks on your pushes) is roughly 600-1,200 min/month at today's run times: check Settings -> Billing after a week; if it
  is tight, capture moves to Render too (it is the only frequent one).
- **"Send feedback" on the Newsletter tab** opens a GitHub issue in the repo: with a private repo only you can. Fine while
  you are the only reader; it needs another channel before the 15-user test.
- **Failures**: a red run in the Render dashboard (e-mail under Account -> Notifications). The site keeps the last good
  deploy; `jobs.render site` refuses to serve an unregistered file (`data/registry.toml`).
- **Rollback** at any step: GitHub schedules back on, `STORE_BACKEND=github`, Pages re-enabled, repo public again. Nothing in
  this sequence deletes data; `store_migrate --from s3 --to github` copies newer months back.

## Environment variables (names only)

| Variable | Used by | Meaning |
|---|---|---|
| `STORE_BACKEND` | everything that reads or writes history | `s3` on Render and, from the switch, on Actions; `github` (default) before; `local` with `STORE_DIR` for a copy on a laptop |
| `STORE_BUCKET`, `STORE_PREFIX`, `STORE_S3_ENDPOINT`, `STORE_S3_REGION` | s3 backend | bucket name, folder inside it (`store`), endpoint URL, region (`auto` for R2) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | s3 backend | the bucket's access key (every S3-compatible provider uses these names) |
| `STATE_SYNC` | `jobs.hourly` | `1` = mirror `state/` (forecast, wake, ENTSO-E caches, 3-hourly tab files) to `<prefix>-state/` in the bucket, because a Render cron job starts from an empty machine |
| `PUBLISH` | `jobs.hourly` | `cloudflare` (the plan), `pages` (GitHub Pages via deploy.yml: needs `GH_TOKEN` + `GITHUB_REPOSITORY`), `both`, `none` |
| `CF_PAGES_PUBLIC`, `CF_PAGES_PROJECT`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | `jobs.publish cloudflare` | Pages project names (public site, private copy) and the token that may deploy to them |
| `SPARK` | render site / publish | spark spreads: empty (off), `private` (private copy only), `public` |
| `STATE_DIR`, `BUILD_DIR`, `DIST_DIR`, `STORE_CACHE` | all jobs | scratch folders (set in the Dockerfile) |
| `ENTSOE_TOKEN`, `GIE_KEY`, `CARTO_KEY` | collect, derive feed, render | API keys |
| `WM_SOURCE`, `WM_OPENMETEO_MODEL`, `WM_DAILY_CALL_CAP` | derive feed | forecast source settings |
| `ENTSOE_PER_MIN`, `COLLECT_PER_MIN` | feed / collector | ENTSO-E rate budget per process (400/min is the API limit for both together) |
| `BACKFILL_FROM` | collectors | first month of the history (`2024-01`) |
| `COLLECT_FARMS` | derive feed | `1` = write farm wind and wake output to the store |
