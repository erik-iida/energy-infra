"""The dataset registry (data/registry.toml): which data files may be served and where every dataset comes from.

    registry.files()                 {pattern: entry} for the files the page loads (pattern may contain <zone>, <day>)
    registry.check_files(paths)      -> (allowed, refused) for paths relative to dist/data; refused = not listed or not publishable
    registry.datasets(), registry.private()
"""
from __future__ import annotations

import re
import tomllib
from functools import lru_cache

from . import paths

FILE = paths.ROOT / "data" / "registry.toml"


@lru_cache(maxsize=1)
def load() -> dict:
    with FILE.open("rb") as f:
        return tomllib.load(f)


def files() -> dict[str, dict]:
    return load().get("files", {})


def datasets() -> dict[str, dict]:
    return load().get("datasets", {})


def private() -> dict[str, dict]:
    return load().get("private", {})


def _rx(pattern: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"<[^>]+>", r"[^/]+", re.escape(pattern).replace(r"\<", "<").replace(r"\>", ">")) + "$")


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[re.Pattern, str, dict]]:
    return [(_rx(p), p, e) for p, e in files().items()]


def entry_for(path: str) -> tuple[str, dict] | None:
    """The registry entry matching a served path (relative to data/), or None."""
    for rx, p, e in _compiled():
        if rx.match(path):
            return p, e
    return None


def check_files(served: list[str]) -> tuple[list[str], dict[str, str]]:
    """served: paths relative to dist/data. Returns (allowed, {path: reason}) — reason 'not in data/registry.toml' or
    'publishable = false'."""
    ok, bad = [], {}
    for s in served:
        m = entry_for(s)
        if m is None:
            bad[s] = "not in data/registry.toml"
        elif not m[1].get("publishable", False):
            bad[s] = f"publishable = false ({m[0]})"
        else:
            ok.append(s)
    return ok, bad
