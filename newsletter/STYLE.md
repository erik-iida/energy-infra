# Newsletter style guide (living document)

What Erik wants the daily brief to be, and what feedback has taught so far. A new chat reads this first, then the open
`newsletter-feedback` issues (see DEVNOTES: Newsletter tab). Update it whenever feedback is processed; keep it short.

## Format (v1, set by Claude, not yet reviewed by Erik)
- Title line, then **Headline** (one sentence: which zone, what number, vs the regional median), then 2-4 short paragraphs of
  *what stood out*, then **Next 24 h**, then **Fundamentals (30 days)**, then a one-line italic data note, then the two tables.
- Lead with the take, not the signal list: say what the number implies ("paid at the peak, not at midday"), and only
  with what the data in the brief supports. No causes that are not in the data.
- Under five minutes to read. Prices EUR/MWh, TB2/TB4, capture rate, bidding zones. Technology colours as on the site.
- Public text never contains fuel prices or spark spreads (yfinance data is private); the site build runs with `--no-fuel`.
- CEE/SEE zones first; Western zones only as reference.

## Ideas not yet in the brief (waiting for Erik's call)
- Residual load peak and net import for the zone in the headline (stored as `metrics_daily`), to say *why* a spread was wide.
- Flags counts from the Flags tab; negative-hours tally; week-on-week change.

## Feedback log (newest first)
(nothing yet: first feedback arrives as GitHub issues labelled newsletter-feedback)

## How the text gets on the site
`newsletter/build.py` writes the generated brief; `scripts/build_newsletter_site.py` publishes the last 3 days.
If `newsletter/editorial/<day>.md` exists it replaces the generated text on the site (the generated one is kept as `<day>.auto.md`).
