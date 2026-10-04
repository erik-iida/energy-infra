"""jobs/: the dispatchers run the right thing and stop on failure; state sync mirrors state/ to the bucket (moto);
the hourly tab rhythm."""
import time

import pytest

from jobs import _run, _state, hourly


def test_dispatch_lists_and_stops(capsys):
    table = {"ok": ("fine", lambda a: None), "bad": ("fails", lambda a: _run._exec("x", lambda: 1 / 0, soft=False))}
    assert _run.dispatch("jobs.t", table, []) == 2
    assert "usage" in capsys.readouterr().out
    assert _run.dispatch("jobs.t", table, ["ok"]) == 0
    assert _run.dispatch("jobs.t", table, ["bad"]) == 1
    assert "stopped at x" in capsys.readouterr().out
    assert _run._exec("soft", lambda: 1 / 0, soft=True) is False        # a soft step reports and continues


def test_script_runs_with_argv(capsys):
    assert _run.script("build_config", ["--out", "/tmp/claude-test-config.js"]) is True
    assert "config.js" in capsys.readouterr().out


def test_tabs_due(monkeypatch, tmp_path):
    monkeypatch.setattr(hourly.paths, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(hourly.paths, "BUILD_DATA", tmp_path / "build")
    assert hourly._tabs_due("3h") is True                                # nothing built yet
    (tmp_path / "build" / "browse").mkdir(parents=True)
    (tmp_path / "build" / "browse" / "index.json").write_text("{}")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / hourly.TABS_MARK).write_text(str(time.time()))
    assert hourly._tabs_due("3h") is False
    (tmp_path / "state" / hourly.TABS_MARK).write_text(str(time.time() - 4 * 3600))
    assert hourly._tabs_due("3h") is True
    assert hourly._tabs_due("never") is False and hourly._tabs_due("always") is True


def test_state_sync_roundtrip(monkeypatch, tmp_path):
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        for k, v in {"AWS_ACCESS_KEY_ID": "t", "AWS_SECRET_ACCESS_KEY": "t", "STORE_BUCKET": "gridecon-state-test", "STORE_PREFIX": "store",
                     "STORE_S3_REGION": "us-east-1", "STATE_SYNC": "1", "STORE_BACKEND": "s3"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("STORE_S3_ENDPOINT", raising=False)
        from common import store as ST
        ST._S3.clear(); _state._seen.clear()
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="gridecon-state-test")
        a = tmp_path / "a"; a.mkdir()
        monkeypatch.setattr(_state.paths, "STATE_DIR", a)
        assert _state.pull() == 0
        (a / "wake_cache.json").write_text("{}")
        (a / "sub").mkdir(); (a / "sub" / "x.bin").write_bytes(b"123")
        assert _state.push() == 2
        assert _state.push() == 0                                        # unchanged: nothing re-uploaded
        b = tmp_path / "b"                                               # a fresh machine
        monkeypatch.setattr(_state.paths, "STATE_DIR", b); _state._seen.clear()
        assert _state.pull() == 2 and (b / "sub" / "x.bin").read_bytes() == b"123"
        assert _state.pull() == 0                                        # already present
        ST._S3.clear()
