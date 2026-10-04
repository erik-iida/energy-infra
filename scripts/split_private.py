"""Split the assembled site (dist/) into the public part (GitHub Pages) and a private copy (site_private/, login-protected host).

SPARK=private  spark spreads are computed (pipeline/spark.py) but only the private copy keeps them: site_private/ is a full
               copy of dist/ made BEFORE market.spark is removed from the public feed.json (in dist/data and in build/data,
               which becomes the built-data artifact).
SPARK=public   nothing is stripped (the spreads are public: see DEVNOTES, they reveal the gas price de facto).
unset          no spark data exists; nothing to do (site_private/ is still produced when --always is given).
Run by hourly.yml after scripts/build_dist.py. Prints what it did, never any price.
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import paths as config  # noqa: E402

DIST, PRIV = config.DIST, ROOT / "site_private"
mode = os.environ.get("SPARK", "")
shutil.rmtree(PRIV, ignore_errors=True)
if mode == "private" or "--always" in sys.argv:
    shutil.copytree(DIST, PRIV)
    print(f"private copy: {sum(1 for _ in PRIV.rglob('*') if _.is_file())} files")
if mode != "public":
    for feed in (DIST / "data" / "feed.json", config.FEED_JSON):
        if not feed.exists():
            continue
        d = json.loads(feed.read_text(encoding="utf-8"))
        mk = d.get("market")
        if mk and "spark" in mk:
            del mk["spark"]
            feed.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
            print(f"spark removed from the public feed ({feed.relative_to(ROOT)})")
