"""Render: derived data -> the files the page loads (build/) and the deployable site (dist/).

    python -m jobs.render tabs        Data / Flags / Newsletter tab files from the store -> build/data/{browse,newsletter}
                                      (each step soft: a failed export hides those tabs, never blocks the site)
    python -m jobs.render dist        build/config.js + dist/ from web/ + data/static/ + build/        (what deploy.yml runs)
    python -m jobs.render site        meta.json, config.js, dist/, public / private split            (what hourly.yml runs)
    python -m jobs.render all         tabs, then site
"""
import sys

from . import _run


def tabs(a):
    _run.script("build_browse", soft=True)
    _run.script("build_newsletter_site", ["--days", "3"], soft=True)


def dist(a):
    _run.script("build_config")
    _run.script("build_dist", a)


def site(a):
    _run.script("build_meta", soft=True)
    _run.script("build_config")
    _run.script("build_dist")
    _run.script("split_private", a)


TABLE = {
    "tabs": ("Data / Flags / Newsletter files from the store -> build/data (soft steps)", tabs),
    "dist": ("config.js + assemble dist/ (deploy)", dist),
    "site": ("meta.json, config.js, dist/, public / private split (hourly build)", site),
    "all": ("tabs, then site", lambda a: (tabs(a), site(a))),
}

if __name__ == "__main__":
    raise SystemExit(_run.dispatch("jobs.render", TABLE, sys.argv[1:]))
