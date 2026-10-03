"""Split the built site into a public part (GitHub Pages: web/) and a private part (site_private/, for a login-protected host).

SPARK=private  spark spreads are computed (pipeline/spark.py) but only the private copy keeps them: site_private/ is a full
               copy of web/ made BEFORE market.spark is removed from the public web/data/feed.json.
SPARK=public   nothing is stripped (the spreads are public: see DEVNOTES, they reveal the gas price de facto).
unset          no spark data exists; nothing to do (site_private/ is still produced when --always is given).
Run by hourly.yml after pipeline.run. Prints what it did, never any price.
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB, PRIV = ROOT / "web", ROOT / "site_private"
mode = os.environ.get("SPARK", "")
feed = WEB / "data" / "feed.json"
shutil.rmtree(PRIV, ignore_errors=True)
if mode == "private" or "--always" in sys.argv:
    shutil.copytree(WEB, PRIV)
    print(f"private copy: {sum(1 for _ in PRIV.rglob('*') if _.is_file())} files")
if mode != "public" and feed.exists():
    d = json.loads(feed.read_text(encoding="utf-8"))
    mk = d.get("market")
    if mk and "spark" in mk:
        del mk["spark"]
        feed.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        print("spark removed from the public feed")
