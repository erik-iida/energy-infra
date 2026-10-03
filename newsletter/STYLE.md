# Newsletter style guide (living document)

What Erik wants the daily brief to be, and what feedback has taught so far. A new chat reads this first, then the open
`newsletter-feedback` issues (see DEVNOTES: Newsletter tab). Update it whenever feedback is processed; keep it short.

## Format (v2, after Erik's feedback #1, 3 Oct 2026)
- Title line, **Headline** (ONE signal, in plain words, ideally with the one fact that explains it), **Price decoupling**
  (the widest baseload gap between connected zones, relative %, hours the prices split), **Next 24 h** (what tomorrow's
  auction already says, before generation data arrives: Erik likes this), **Fundamentals (last 30 days)** (wind and solar
  output as % of load, correlations with price signals), a one-line italic data note, then the two tables.
- Fewer signals: we are still learning to explain drivers, so quoting many signals clutters the text. Add commentary over time.
- Country and zone names written out in full (Romania, Germany-Luxembourg, southern Sweden (SE4)); codes only where no name fits.
- Capture rates: only 30-day ("monthly") values, never daily (a day is too short to separate them from baseload).
- Lean less on TB2/TB4 in the commentary; they stay in the table.
- No installed-capacity (IRENA) numbers: IRENA's year-end capacity is outdated. Use output as % of load; capacity factors
  use the highest hourly output in 90 days as the capacity proxy (label it so).
- Daily table: Zone | Baseload | TB2 | TB4 | Neg. h | Wind % of load | Solar % of load. 30-day table: shares, CF vs peak,
  30-day capture rates, baseload, TB4, negative hours.
- Whole numbers only (no decimals) in text and tables; correlation coefficients keep two decimals. Say "average power
  price" (column "Avg. power price"), not baseload; "% of consumption", not "% of load" (Erik, 3 Oct 2026).
- Lead with the take, only what the data supports. Under five minutes to read. Prices €/MWh.
- Public text never contains fuel prices or spark spreads (yfinance data is private); the site build runs with `--no-fuel`.
- CEE/SEE zones first; Western zones only as reference or as the other side of a decoupled border.

## Ideas not yet in the brief (waiting for Erik's call)
- Residual load peak and net import for the zone in the headline (stored as `metrics_daily`), to say *why* a spread was wide.
- Flags counts from the Flags tab; negative-hours tally; week-on-week change.

## Feedback log (newest first)
- 2026-10-03, issue #1 (on the 2 Oct editorial): too many numbers/signals in the headline; write country names in full;
  only monthly capture rates; decoupling is a good angle, frame it as the relative price gap between connected zones
  (insufficient cross-border capacity), less TB in commentary; Next 24 h is great; replace installed-capacity ratios by
  output % of load (IRENA outdated) and keep looking for correlations; table: capture rates out, wind and solar % of
  load in. Overall: rework capacity factors across the site with the 90-day maximum output as capacity proxy.
  Applied: draft_brief v2, fundamentals.peak_cf, Data tab capacity view, 2 Oct editorial rewritten.

## How the text gets on the site
`newsletter/build.py` writes the generated brief; `scripts/build_newsletter_site.py` publishes the last 3 days.
If `newsletter/editorial/<day>.md` exists it replaces the generated text on the site (the generated one is kept as `<day>.auto.md`).
