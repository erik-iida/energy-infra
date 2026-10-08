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

## Percentiles (5 Oct 2026, text wording changed 7 Oct)
- Signals and "unusual" rows are ranked against every earlier day of the zone in the store (since Jan 2024), not a 90-day
  window. Unusual for the zone, not for the season. The window is NOT 90 days, so the text never says "last 3 months" for it:
  it says how often the level was reached ("on 12 days in 2025 and 31 days so far in 2026"), else "among the highest of the
  last N months" with N from the real history length. (Erik's #3 assumed 90 days; changing the window is a signal-definition
  decision, left open on issue #3.)
- **Only extremes reach the text** (Erik, #2): a metric is quoted only at or beyond P5 / P95 of its own history (`build.TEXT_PCT`).
  Context metrics (wind / solar output and shares, demand, gas share) at the extremes count as signals too, so the text is not
  all storage spreads. Per zone a non-spread signal beats a spread; at most 3 spread stories (`build.SPREAD_MAX`).

## Diagnoses (v3 draft, 5 Oct 2026, spec 4; format still to be judged by Erik)
- The headline sentence is followed by ONE sentence from the diagnosis of that signal (its top candidate driver).
- **Why they fired**: up to five more story candidates (fired signals in CEE/SEE, one per zone, strongest first, never daily
  capture rates), one line each: zone, signal and value, percentile, the top driver in plain numbers.
- Drivers state co-occurrence, never causation ("the priciest hours took in the residual-load peak", not "caused by"); no
  congestion claims until NTC is in the store. Every number comes from `newsletter/diagnose.py`'s structured dict (tested).
- The full context block per candidate (event hours, what happened in them, what else was unusual, next door, data gaps)
  is in `facts.json` -> `diagnoses[].text`; a chat session writing the editorial starts from it.
- Persistence is not news: the headline is the strongest signal that did not fire yesterday; a signal that keeps firing is
  marked "3rd day running" (Erik, 5 Oct 2026).
- A flow is never quoted alone: "imports from Y" always says what was happening in Y (its generation mix in those hours and
  what was unusual there: high wind, solar, a neighbour exporting nuclear...) (Erik, 5 Oct 2026).
- Open for Erik: which checks and thresholds stay (`diagnose.TH`), how many candidates, whether the "Why they fired" block
  belongs before or after Price decoupling, and whether import/export signals read well as "net export share of load".

## Stories, not a metrics dump (v4, 7 Oct 2026, issues #2 and #3)
Reader = energy professional, not a trader. Fewer numbers, more explanation, one clear take per section.
- **Headline**: ONE signal, one number, no second percentage. How unusual it is is told by counting: "a level reached or exceeded
  on N days in 2025 and M days so far in 2026" (days: the store keeps daily history; hours would need hourly reads).
- **Stories** (max 3, `build.stories`): the diagnosed signals are grouped by driver pattern (`group_of`): tight supply,
  wind and solar surplus, cheap overnight hours, imports, other. One paragraph per group, 2-4 sentences, starts with the take
  (who stood out for what), then the lead zone's drivers, then "the same pattern showed in X". The headline's story comes first
  and is the longest, so the headline always matches the body. Every paragraph answers "why" (drivers, from `diagnose.py`).
- **At most 3 figures per paragraph** (`build.FIGURES_MAX`; the first sentence is always kept). Pick the number that carries the point.
- **No jargon**: no P-values, no day counts of the history window ("1009 days"), no "the 5th day running" but "the 5th day in a
  row", no hour lists ("17:00, 18:00, 19:00"): "from 17:00 to 22:00" or "in the evening" (`diagnose.hours_phrase`).
- Say "storage spread" in text; TB2/TB4 only in the tables (explained once in the footer). "average power price", "consumption".
- Wording fixes: "almost no wind or solar" (not "wind 0 % and solar 0 %"); "coincided with the evening peak in residual load"
  (not "took in"); a "wind / solar peak" in the cheap hours needs >= 5 % of consumption and more than the day's share, else
  night hours are told as "fell at night, when demand is lowest"; no "other 30 %" in a generation mix (name the fuel or drop it);
  imports/exports are told as "imported in the evening, mostly from Bulgaria; in Bulgaria the power came mostly from coal, ..."
  (the neighbour's generation types, no MW clause).
- Drivers also name the zone's own plants in the priciest hours ("own output was mostly gas, coal and hydro": the likely
  price setters, named not asserted). Not done: "very low nuclear output compared to usual" (needs a stored nuclear metric).
- **Price decoupling**: no congestion claim ("the border was the bottleneck" is gone until NTC is in the store). Wording:
  "Prices separated in 16 of 24 hours, which is typical when the border limit is reached." Then what differed between the two
  zones from the diagnosis frames (wind + solar share, net flow, own mix); nothing beyond the data.
- **Next 24 h**: the widest 4-hour storage spread among zones not already told above, one line on when the low and the peak
  fall (midday solar, evening ramp), negative hours as "Greece (6 h)".
- **"Renewables leaders in the last 24h"** (was Fundamentals, last 30 days): the countries with the highest wind and solar
  output relative to average consumption of the day. Rank correlations are out of the text (still in facts.json).

## Ideas not yet in the brief (waiting for Erik's call)
- Flags counts from the Flags tab; negative-hours tally; week-on-week change.

## Feedback log (newest first)
- 2026-10-08, issues #2 (5 Oct) and #3 (6 Oct): applied as the v4 rules above. #2: no double percentage in the headline (counts per
  year), only P0-P5 / P95-P100 metrics and non-spread signals too, drivers name neighbours' generation types, bottleneck sentence
  removed, "(x h)" for negative hours, Fundamentals -> "Renewables leaders in the last 24h". #3: stories by driver pattern, max 3
  figures, no P-values / day counts / hour lists, headline = first story, "almost no wind or solar", "other" mix dropped, no
  correlations, "storage spread". Conflicts: #3 wants fewer numbers, #2 wants a year-count comparison: one count sentence in the
  headline only. Left open (Erik's call): brand name "Radial Economics" vs "GridEconomics" in the title; switching the percentile
  window to 90 days; a stored nuclear-output metric; hourly instead of daily counts. See the comments on the issues.
- 2026-10-03, issue #1 (on the 2 Oct editorial): too many numbers/signals in the headline; write country names in full;
  only monthly capture rates; decoupling is a good angle, frame it as the relative price gap between connected zones
  (insufficient cross-border capacity), less TB in commentary; Next 24 h is great; replace installed-capacity ratios by
  output % of load (IRENA outdated) and keep looking for correlations; table: capture rates out, wind and solar % of
  load in. Overall: rework capacity factors across the site with the 90-day maximum output as capacity proxy.
  Applied: draft_brief v2, fundamentals.peak_cf, Data tab capacity view, 2 Oct editorial rewritten.

## How the text gets on the site
`newsletter/build.py` writes the generated brief; `scripts/build_newsletter_site.py` publishes the last 3 days.
If `newsletter/editorial/<day>.md` exists it replaces the generated text on the site (the generated one is kept as `<day>.auto.md`).
