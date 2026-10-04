"""Assemble dist/, the site that gets deployed (spec 3 step 3).

    python scripts/build_dist.py [--out dist] [--serve 8000]

dist/ = web/ (the hand-written page) + data/static/ as data/ (committed inputs: site, zones, grid, capture, gas, gie,
bathy) + build/data/ as data/ (what the last run generated: feed.json, meta.json, browse/, newsletter/) + build/config.js.
Nothing is written into web/. dist/ is rebuilt from scratch each time and is never committed.

Missing pieces are reported, not fatal: a local build without build/ gives a page with the static layers only, and the
deploy's own completeness check decides what may go live. `--serve` starts a local http server on dist/ for a look.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import config  # noqa: E402


def copy_tree(src: Path, dst: Path) -> int:
    """Copy src/** into dst (merging), return the number of files."""
    n = 0
    for p in src.rglob("*"):
        if p.is_file():
            q = dst / p.relative_to(src)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
            n += 1
    return n


def build(out: Path = config.DIST) -> dict:
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    report = {"web": copy_tree(config.WEB, out)}
    report["static"] = copy_tree(config.DATA_STATIC, out / "data") if config.DATA_STATIC.exists() else 0
    report["build"] = copy_tree(config.BUILD_DATA, out / "data") if config.BUILD_DATA.exists() else 0
    cfg = config.BUILD / "config.js"
    if cfg.exists():
        shutil.copy2(cfg, out / "config.js")
        report["config"] = 1
    else:
        report["config"] = 0
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.DIST))
    ap.add_argument("--serve", type=int, metavar="PORT", help="after building, serve dist/ on this port")
    a = ap.parse_args(argv)
    out = Path(a.out)
    r = build(out)
    print(f"dist: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {r['web']} page files, "
          f"{r['static']} static data files, {r['build']} built data files, config.js {'yes' if r['config'] else 'no (keyless basemaps)'}")
    for name in ("site.json", "feed.json"):
        if not (out / "data" / name).exists():
            print(f"  note: data/{name} missing" + (" (run the pipeline or download the built-data artifact into build/)" if name == "feed.json" else ""))
    if a.serve:
        import functools
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        print(f"serving {out} on http://localhost:{a.serve}  (Ctrl+C to stop)")
        ThreadingHTTPServer(("", a.serve), functools.partial(SimpleHTTPRequestHandler, directory=str(out))).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
