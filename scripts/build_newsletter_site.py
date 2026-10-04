"""Newsletter tab data: build/data/newsletter/{index.json, <day>.md} (public site, no fuel prices / spark spreads).

    python scripts/build_newsletter_site.py [--days 3]

For each of the last N complete CET days it runs newsletter.build (from the data store; STORE_DIR / GH_TOKEN as usual) and
writes the generated brief. If newsletter/editorial/<day>.md exists (a draft written or edited by hand / in a chat), that
text is published as the day's brief and the generated one is kept as <day>.auto.md. index.json lists the days.
Not committed: the deploy job builds it (see .github/workflows/hourly.yml). A day that fails is skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
from pipeline import config  # noqa: E402  (paths: data/static, build/)
sys.path.insert(0, str(ROOT))
OUT = config.BUILD_DATA / "newsletter"
EDIT = ROOT / "newsletter" / "editorial"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    a = ap.parse_args(argv)
    from newsletter import build as B
    from newsletter import metrics as M
    OUT.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now(tz=M.CET).tz_localize(None).normalize()
    days, failed = [], []
    for k in range(1, a.days + 1):
        d = (today - pd.Timedelta(days=k)).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                B.main(["--day", d, "--out", tmp, "--no-fuel"])
                auto = (Path(tmp) / "brief.md").read_text()
            except BaseException as e:  # SystemExit: no price rows for that day
                failed.append(d)
                print(f"newsletter {d}: skipped ({type(e).__name__})", file=sys.stderr)
                if not isinstance(e, SystemExit):
                    traceback.print_exc()
                continue
        ed = EDIT / f"{d}.md"
        if ed.exists():
            (OUT / f"{d}.md").write_text(ed.read_text())
            (OUT / f"{d}.auto.md").write_text(auto)
        else:
            (OUT / f"{d}.md").write_text(auto)
        days.append({"day": d, "source": "editorial" if ed.exists() else "auto"})
    if not days:
        raise SystemExit("no newsletter day could be built")
    (OUT / "index.json").write_text(json.dumps({"schema": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "latest": days[0]["day"], "days": days,
        "repo": "erik-iida/energy-infra"}, indent=1) + "\n")
    print(f"newsletter: {[x['day'] for x in days]} written to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
