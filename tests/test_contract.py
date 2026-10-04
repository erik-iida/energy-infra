"""The data contract (docs/DATA_CONTRACT.md) matches what the page loads and what the writers stamp.

- every `data/...` path in the page (web/index.html and web/js/) is listed in the contract table, and every listed file is still used;
- the schema numbers in the table equal scripts/build_meta.py SCHEMAS;
- the test data (tests/fixtures/data) has every file the page loads, and the schema stamped in each file agrees.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_meta  # noqa: E402
from tests import pagejs  # noqa: E402

PAGE = pagejs.page_text()
CONTRACT = (ROOT / "docs" / "DATA_CONTRACT.md").read_text(encoding="utf-8")
FIX = ROOT / "tests" / "fixtures" / "data"


def page_paths() -> set[str]:
    """Paths after data/ in string literals of the page; a prefix ending in '/' stands for a family of files."""
    return set(re.findall(r"[\"'`]data/([^\"'`$]*)", PAGE))


def contract_rows() -> dict[str, str]:
    """File name -> schema column, from the Files table (a cell may list two files: `bathy.json`, `bathy.png`)."""
    rows = {}
    for line in CONTRACT.splitlines():
        m = re.match(r"^\|\s*(`[^|]+)\|\s*([^|]*)\|", line)
        if m:
            for name in re.findall(r"`([^`]+)`", m.group(1)):
                rows[name] = m.group(2).strip()
    return rows


def covers(path: str, name: str) -> bool:
    return path == name or (path.endswith("/") and name.startswith(path) and "<" in name)


def test_every_page_fetch_is_in_contract():
    rows = contract_rows()
    missing = [p for p in page_paths() if not any(covers(p, n) for n in rows)]
    assert not missing, f"page loads files not listed in docs/DATA_CONTRACT.md: {missing}"


def test_every_contract_file_is_used():
    paths = page_paths()
    unused = [n for n in contract_rows() if n != "meta.json" and not any(covers(p, n) for p in paths)]
    assert not unused, f"listed in docs/DATA_CONTRACT.md but not loaded by the page: {unused}"


def test_contract_schema_matches_build_meta():
    rows = contract_rows()
    for name, ver in build_meta.SCHEMAS.items():
        assert name in rows, f"{name} is in build_meta.SCHEMAS but not in the contract table"
        assert rows[name] == str(ver), f"{name}: contract says schema {rows[name]!r}, build_meta says {ver}"


def test_fixtures_have_every_file_the_page_loads():
    missing = []
    for p in page_paths():
        if p.endswith("/"):
            if not any((FIX / p).glob("*")):
                missing.append(p + "*")
        elif not (FIX / p).exists():
            missing.append(p)
    assert not missing, f"tests/fixtures/data lacks {missing} (re-run tests/fixtures/make_fixtures.py)"


def test_stamped_schema_agrees():
    meta = json.loads((FIX / "meta.json").read_text())
    assert meta["schema"] == build_meta.SCHEMAS["meta.json"]
    bad = {k: v for k, v in meta["files"].items() if "schema_in_file" in v or v.get("unreadable")}
    assert not bad, f"schema stamp or readability problems in fixtures: {bad}"
    for f in sorted((FIX / "browse" / "ts").glob("*.json")) + sorted((FIX / "browse" / "flags").glob("*.json")):
        d = json.loads(f.read_text())
        assert d.get("schema") == 1, f"{f.relative_to(FIX)}: schema {d.get('schema')!r}"
