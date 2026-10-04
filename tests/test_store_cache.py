"""collector.store download cache: each asset downloaded once per id, shared across Store() objects and via STORE_CACHE."""
import json
import types

import pytest

from collector import store as ST


@pytest.fixture
def fake_gh(monkeypatch):
    monkeypatch.delenv("STORE_DIR", raising=False)
    ST._MEM.clear()
    ST._ASSETS.clear()
    state = {"assets": {"da_price_2026-10.parquet": 11, "x.json": 12}, "calls": []}

    def gh(self, *args, binary=False, check=True):
        state["calls"].append(args[:2])
        if args[0] == "api" and "releases/tags/" in args[1]:
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({"id": 1}).encode())
        if args[0] == "api" and args[1] == "--paginate":
            return types.SimpleNamespace(returncode=0, stdout="\n".join(f"{n}\t{i}" for n, i in state["assets"].items()).encode())
        if args[:2] == ("release", "download"):
            name = args[args.index("--pattern") + 1]
            if state.get("gone") == name:   # deleted by a concurrent upload: gh fails
                state.pop("gone")
                state["assets"][name] += 100
                raise RuntimeError("gh release download: no assets match")
            return types.SimpleNamespace(returncode=0, stdout=f"{name}@{state['assets'][name]}".encode())
        raise AssertionError(args)

    monkeypatch.setattr(ST.Store, "_gh", gh)
    return state


def downloads(state):
    return sum(1 for c in state["calls"] if c == ("release", "download"))


def listings(state):
    return sum(1 for c in state["calls"] if c[0] == "api" and c[1] == "--paginate")


def test_memory_cache_across_instances(fake_gh):
    for _ in range(3):
        assert ST.Store()._download("x.json") == b"x.json@12"
    assert downloads(fake_gh) == 1 and listings(fake_gh) == 1


def test_disk_cache_shared_between_processes(fake_gh, monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_CACHE", str(tmp_path))
    ST.Store()._download("x.json")
    ST._MEM.clear()   # a second process: memory empty, disk cache present
    assert ST.Store()._download("x.json") == b"x.json@12"
    assert downloads(fake_gh) == 1 and (tmp_path / "12-x.json").exists()


def test_new_asset_id_is_downloaded_again(fake_gh):
    ST.Store()._download("x.json")
    fake_gh["assets"]["x.json"] = 99
    ST._ASSETS.clear()   # listing refreshed, as after an upload
    assert ST.Store()._download("x.json") == b"x.json@99"
    assert downloads(fake_gh) == 2


def test_replaced_asset_retried_with_fresh_listing(fake_gh):
    fake_gh["gone"] = "da_price_2026-10.parquet"
    assert ST.Store()._download("da_price_2026-10.parquet") == b"da_price_2026-10.parquet@111"
    assert listings(fake_gh) == 2
