"""Back-end package rules (spec 3 step 4): shared code lives in common/, which imports none of the other packages;
collector/ and newsletter/ do not import pipeline/; nothing imports from scripts/ or tools/.

pipeline/ may import collector/ (the hourly feed hands farm output to the store and reuses the GB collectors) and
newsletter/ (spark spreads): that is the derive stage using collect's clients, and it goes away with the collect /
derive / render entrypoints, not before.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("common", "pipeline", "collector", "newsletter")


def imports_of(path: Path) -> set[str]:
    """Top-level package names imported anywhere in the file (absolute imports only)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


def package_imports(pkg: str) -> dict[str, set[str]]:
    return {str(p.relative_to(ROOT)): imports_of(p) & set(PACKAGES + ("scripts", "tools")) for p in (ROOT / pkg).glob("*.py")}


def test_common_imports_no_package():
    bad = {f: i - {"common"} for f, i in package_imports("common").items() if i - {"common"}}
    assert not bad, f"common/ must not import other packages: {bad}"


def test_collector_and_newsletter_do_not_import_pipeline():
    for pkg in ("collector", "newsletter"):
        bad = {f: i for f, i in package_imports(pkg).items() if "pipeline" in i}
        assert not bad, f"{pkg}/ imports pipeline/ (move the shared code to common/): {bad}"


def test_nothing_imports_scripts():
    for pkg in PACKAGES:
        bad = {f: i for f, i in package_imports(pkg).items() if i & {"scripts", "tools"}}
        assert not bad, f"packages must not import scripts/ or tools/: {bad}"
