"""data/registry.toml covers everything the site serves and everything the store holds, and build_dist enforces it."""
import sys
from pathlib import Path

import pytest

from common import registry
from common.store import KEYS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_contract import contract_rows, page_paths  # noqa: E402


def test_every_file_the_page_loads_is_registered_and_publishable():
    missing, private = [], []
    for p in page_paths():
        if p.endswith("/"):            # a family like browse/ts/ : the contract rows carry the concrete patterns
            continue
        m = registry.entry_for(p)
        if m is None:
            missing.append(p)
        elif not m[1].get("publishable"):
            private.append(p)
    assert not missing, f"page loads files that are not in data/registry.toml: {missing}"
    assert not private, f"page loads files marked publishable = false: {private}"


def test_contract_rows_are_registered():
    missing = [n for n in contract_rows() if registry.entry_for(n) is None]
    assert not missing, f"docs/DATA_CONTRACT.md rows without a registry entry: {missing}"


def test_every_store_dataset_is_registered():
    missing = sorted(set(KEYS) - set(registry.datasets()))
    assert not missing, f"store datasets without a registry entry: {missing}"


def test_entries_have_a_source():
    for section in (registry.files(), registry.datasets(), registry.private()):
        for name, e in section.items():
            assert e.get("source"), f"{name}: no source"
            assert "publishable" in e, f"{name}: no publishable flag"


def test_gate_refuses_unlisted_and_private_files(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_dist
    (tmp_path / "web").mkdir(); (tmp_path / "web" / "index.html").write_text("<html></html>")
    static = tmp_path / "static"; static.mkdir()
    (static / "site.json").write_text("{}")
    monkeypatch.setattr(build_dist.config, "WEB", tmp_path / "web")
    monkeypatch.setattr(build_dist.config, "DATA_STATIC", static)
    monkeypatch.setattr(build_dist.config, "BUILD_DATA", tmp_path / "nobuild")
    monkeypatch.setattr(build_dist.config, "BUILD", tmp_path / "nobuild")
    out = tmp_path / "dist"
    assert build_dist.build(out)["checked"] == 1 and (out / "data" / "site.json").exists()
    (static / "fuel_prices.json").write_text("{}")                      # unlisted
    with pytest.raises(build_dist.NotPublishable) as e:
        build_dist.build(out)
    assert "fuel_prices.json" in str(e.value) and not out.exists()      # nothing half-built is left behind
    assert build_dist.main(["--out", str(out)]) == 1
