"""Front-end module rules (spec 3): a feature imports only from js/core/ and its own folder; core never imports a feature;
every module is reachable from js/app.js.

Shared code lives in js/core/ (data, feed, chart helpers, colours, tables, router). A feature talks to another feature
only through core: the router's registerTab / registerMap, shared state S, or data modules. If two features need the
same function, move it to core/ rather than importing across. KNOWN is the (empty) list of tolerated exceptions.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
IMPORT = re.compile(r'^import (?:\{[^}]*\} from )?["\']([^"\']+)["\'];', re.M)

# (importing module, imported module) pairs allowed to cross a feature boundary: none since step 2 push 6
KNOWN: set[tuple[str, str]] = set()


def modules() -> dict[str, list[str]]:
    """module path (relative to web/js) -> list of imported module paths (relative to web/js)."""
    out = {}
    for p in sorted(JS.rglob("*.js")):
        rel = p.relative_to(JS).as_posix()
        out[rel] = [(p.parent / m).resolve().relative_to(JS.resolve()).as_posix() for m in IMPORT.findall(p.read_text(encoding="utf-8"))]
    return out


def feature_of(rel: str):
    parts = rel.split("/")
    return parts[1] if parts[0] == "features" else None


def test_feature_imports_stay_inside_core_and_own_folder():
    crossing = set()
    for mod, imps in modules().items():
        if mod == "app.js":          # the entry module wires every feature up
            continue
        for imp in imps:
            if imp.startswith("features/") and feature_of(imp) != feature_of(mod):
                crossing.add((mod, imp))
    new = crossing - KNOWN
    gone = KNOWN - crossing
    assert not new, f"new cross-feature import(s): {sorted(new)} — move the shared code to js/core/ instead"
    assert not gone, f"these cross-feature imports are gone, remove them from KNOWN: {sorted(gone)}"


def test_every_module_is_loaded_from_app():
    mods = modules()
    seen, todo = set(), ["app.js"]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(mods.get(m, []))
    assert set(mods) == seen, f"modules not reachable from js/app.js: {sorted(set(mods) - seen)}"


def test_imports_resolve():
    for mod, imps in modules().items():
        for imp in imps:
            assert (JS / imp).exists(), f"{mod} imports missing file {imp}"
