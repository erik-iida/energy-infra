"""The hourly run as one command (what Render's hourly cron job calls; hourly.yml does the same in separate steps):

    python -m jobs.hourly [--no-publish] [--tabs always|3h|never]

    1. pull state/ from the bucket (STATE_SYNC=1)           forecast, wake and ENTSO-E caches survive between runs
    2. derive feed                                           pipeline.run -> build/data/feed.json (+ farm output to the store)
    3. render tabs                                           Data / Flags / Newsletter files from the store (default: when the
                                                             previous ones in the bucket are older than 3 h, else reuse them)
    4. render site                                           meta.json, config.js, dist/, public / private split
    5. publish pages                                         hand build/data to deploy.yml (GitHub Pages); --no-publish to skip
    6. push state/ (and the tab files) back to the bucket
"""
from __future__ import annotations

import sys
import time

from common import paths

from . import _run, _state

TABS_MARK = "tabs_built_at"   # kept in state/, so the 3-hourly rhythm survives between runs


def _tabs_due(policy: str) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        return False
    mark = paths.STATE_DIR / TABS_MARK
    have = (paths.BUILD_DATA / "browse" / "index.json").exists()
    try:
        age = time.time() - float(mark.read_text())
    except (OSError, ValueError):
        age = 1e9
    return not have or age > 3 * 3600


def main(argv: list[str]) -> int:
    policy = argv[argv.index("--tabs") + 1] if "--tabs" in argv else "3h"
    t0 = time.time()
    _state.pull()
    # the tab files live in state/tabs/ between runs when STATE_SYNC is on (they are build output, but rebuilding them
    # every hour costs ~3 min); copy them into build/data first so "reuse" has something to reuse
    saved = paths.STATE_DIR / "tabs"
    if _state.enabled() and saved.exists() and not (paths.BUILD_DATA / "browse").exists():
        import shutil
        for d in ("browse", "newsletter"):
            if (saved / d).exists():
                shutil.copytree(saved / d, paths.BUILD_DATA / d, dirs_exist_ok=True)
    try:
        _run.module("pipeline.run")
        if _tabs_due(policy):
            _run.script("build_browse", soft=True)
            _run.script("build_newsletter_site", ["--days", "3"], soft=True)
            if (paths.BUILD_DATA / "browse" / "index.json").exists():
                paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
                (paths.STATE_DIR / TABS_MARK).write_text(str(time.time()))
                if _state.enabled():
                    import shutil
                    for d in ("browse", "newsletter"):
                        if (paths.BUILD_DATA / d).exists():
                            shutil.rmtree(saved / d, ignore_errors=True)
                            shutil.copytree(paths.BUILD_DATA / d, saved / d)
        _run.script("build_meta", soft=True)
        _run.script("build_config")
        _run.script("build_dist")
        _run.script("split_private")
        if "--no-publish" not in argv:
            from . import publish
            _run._exec("python -m jobs.publish pages", lambda: publish.pages([]), soft=False)
    finally:
        _state.push()
    print(f"hourly: done in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except _run.StepFailed as e:
        print(f"hourly: stopped at {e}")
        raise SystemExit(1)
