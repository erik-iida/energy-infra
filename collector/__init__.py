"""GridEconomics data store: collects every openly published series the site shows into a growing history.

Layout (see DEVNOTES.md "Data store"):
  collector/store.py    Parquet files as assets of one GitHub release (tag "store"), merged by key, never shrunk
  collector/entsoe_raw.py  ENTSO-E fetchers at native resolution (prices, generation, forecasts, load, flows)
  collector/collect.py  daily window + resumable monthly backfill (python -m collector.collect daily|backfill)
  collector/farms.py    per-farm hub-height wind and wake-model power, written by the hourly pipeline
"""
