"""Where files live (spec 3 step 3). The one place that knows the folder layout; every writer takes its path from here.
Environment overrides: STATE_DIR (scratch that must survive between runs: forecast and wake caches; on Render a
persistent disk), BUILD_DIR, DIST_DIR.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Where files live (spec 3 step 3: source and build output are separate folders).
#   web/          the page as written by hand (index.html, css/, js/). Nothing generates files here.
#   data/static/  slow inputs the page reads, committed to git and refreshed by bot workflows
#                 (site.json, zones.json, grid.json, capture.json, gas.json, gie.json, bathy.*)
#   build/        what one run generates, never committed: data/feed.json, data/meta.json, data/browse/,
#                 data/newsletter/, config.js. The hourly job uploads it as the `built-data` artifact.
#   dist/         the assembled site = web/ + data/static/ (as data/) + build/ (as data/ and config.js);
#                 scripts/build_dist.py makes it, the deploy publishes it. Never committed.
WEB = ROOT / "web"
DATA_STATIC = ROOT / "data" / "static"
BUILD = Path(os.environ.get("BUILD_DIR") or ROOT / "build")
BUILD_DATA = BUILD / "data"
DIST = Path(os.environ.get("DIST_DIR") or ROOT / "dist")
SITE_JSON = DATA_STATIC / "site.json"
FEED_JSON = BUILD_DATA / "feed.json"
STATE_DIR = Path(os.environ.get("STATE_DIR") or ROOT / "state")  # forecast / wake / ENTSO-E caches, call budget: Actions cache today, a disk on Render


def static_file(name: str) -> Path:
    """A committed page input (data/static/<name>)."""
    return DATA_STATIC / name


def build_file(*parts: str) -> Path:
    """A generated page file (build/data/<parts>), parent folder created."""
    p = BUILD_DATA.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
