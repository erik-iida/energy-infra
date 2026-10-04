"""The S3 store backend (Cloudflare R2 / Backblaze B2 / AWS S3) behaves like the others: same merge rules, same names,
cache keyed by object version; and tools/store_migrate.py copies and verifies a store between backends."""
import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from common import store as ST  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def s3_env(monkeypatch):
    with moto.mock_aws():
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
        monkeypatch.setenv("STORE_BACKEND", "s3")
        monkeypatch.setenv("STORE_BUCKET", "gridecon-test")
        monkeypatch.setenv("STORE_PREFIX", "store")
        monkeypatch.setenv("STORE_S3_REGION", "us-east-1")
        monkeypatch.delenv("STORE_S3_ENDPOINT", raising=False)
        monkeypatch.delenv("STORE_DIR", raising=False)
        ST._MEM.clear(); ST._ASSETS.clear(); ST._S3.clear()
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="gridecon-test")
        yield
        ST._S3.clear()


def frame(n: int, start: int = 0) -> pd.DataFrame:
    ts = pd.date_range("2026-10-01", periods=n, freq="h", tz="UTC") + pd.Timedelta(hours=start)
    return pd.DataFrame({"zone": "RO", "ts": ts, "res_min": 60, "seq": 1, "price": range(start, start + n),
                         "currency": "EUR", "fetched": pd.Timestamp.now(tz="UTC")})


def test_write_merge_read_and_json(s3_env):
    st = ST.Store()
    assert st.kind == "s3"
    assert st.write("da_price", frame(5)) == {"2026-10": 5}
    assert st.write("da_price", frame(5, 3)) == {"2026-10": 8}          # 2 overlapping hours merged, not duplicated
    df = st.read("da_price", "2026-10")
    assert len(df) == 8 and df["price"].tolist() == list(range(8))
    assert "da_price_2026-10.parquet" in st.assets(refresh=True)
    st.write_json("backfill_state.json", {"done": ["2026-09"]})
    assert ST.Store().read_json("backfill_state.json") == {"done": ["2026-09"]}
    assert st.read("da_price", "2026-09") is None
    assert ST.backend_kind() == "s3"


def test_cache_is_keyed_by_object_version(s3_env, monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_CACHE", str(tmp_path))
    st = ST.Store()
    st.write_json("x.json", {"v": 1})
    assert ST.Store().read_json("x.json") == {"v": 1}
    st.write_json("x.json", {"v": 2})                                   # new ETag -> new download, old cache entry unused
    assert ST.Store().read_json("x.json") == {"v": 2}
    assert len(list(tmp_path.iterdir())) == 2


def test_migrate_local_to_s3_and_verify(s3_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STORE_DIR", str(tmp_path / "local"))
    local = ST.Store("local")
    local.write("da_price", frame(10))
    local.write("flows", pd.DataFrame({"from_zone": "RO", "to_zone": "HU", "ts": frame(4)["ts"], "res_min": 60, "mw": 1.0,
                                       "fetched": pd.Timestamp.now(tz="UTC")}))
    local.write_json("collector_log.json", {"runs": []})
    sys.path.insert(0, str(ROOT / "tools"))
    import store_migrate
    assert store_migrate.main(["--from", "local", "--to", "s3", "--dry-run"]) == 0
    assert ST.Store("s3").read("da_price", "2026-10") is None            # dry run copied nothing
    assert store_migrate.main(["--from", "local", "--to", "s3"]) == 0
    out = capsys.readouterr().out
    assert "copied 3" in out and "verified" in out
    assert len(ST.Store("s3").read("da_price", "2026-10")) == 10
    assert store_migrate.main(["--from", "local", "--to", "s3", "--verify-only"]) == 0
    assert store_migrate.main(["--from", "local", "--to", "s3"]) == 0 and "already identical 3" in capsys.readouterr().out
    os.environ.pop("STORE_DIR", None)
