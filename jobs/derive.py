"""Derive: forecasts and the store -> derived data.

    python -m jobs.derive feed [pipeline.run args]      forecast -> hub-height wind -> PyWake, + ENTSO-E market / system -> build/data/feed.json
    python -m jobs.derive metrics [--all]               daily metrics per zone and CET day -> store dataset metrics_daily
    python -m jobs.derive newsletter [--day D] [--out]  facts.json + brief (newsletter.build)
"""
import sys

from . import _run

TABLE = {
    "feed": ("hourly feed: forecasts, PyWake, market and system data -> build/data/feed.json (pipeline.run)", lambda a: _run.module("pipeline.run", a)),
    "metrics": ("daily metrics into the store (scripts/build_metrics.py; --all recomputes everything)", lambda a: _run.script("build_metrics", a)),
    "newsletter": ("facts.json, brief.md, brief.html (newsletter.build)", lambda a: _run.module("newsletter.build", a)),
}

if __name__ == "__main__":
    raise SystemExit(_run.dispatch("jobs.derive", TABLE, sys.argv[1:]))
