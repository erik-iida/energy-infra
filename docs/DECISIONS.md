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
