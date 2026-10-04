"""Run a module or script as if from the command line, from inside a job."""
from __future__ import annotations

import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StepFailed(RuntimeError):
    pass


def _exec(label: str, fn, soft: bool) -> bool:
    t0 = time.time()
    ok = False
    print(f"::group::{label}" if _in_actions() else f"== {label}", flush=True)
    try:
        fn()
        ok = True
    except SystemExit as e:               # scripts call sys.exit(); 0 / None is success
        ok = e.code in (0, None)
        if not ok:
            print(f"{label}: exit {e.code}")
    except Exception as e:                # noqa: BLE001  (a job step may fail for any reason; we report and decide below)
        ok = False
        print(f"{label}: {type(e).__name__}: {e}")
    finally:
        print(f"{label}: {'ok' if ok else 'FAILED'} after {time.time() - t0:.0f} s" + (" (continuing)" if not ok and soft else ""))
        print("::endgroup::" if _in_actions() else "", flush=True)
    if not ok and not soft:
        raise StepFailed(label)
    return ok


def _in_actions() -> bool:
    import os
    return os.environ.get("GITHUB_ACTIONS") == "true"


def module(name: str, args: list[str] | None = None, soft: bool = False) -> bool:
    """`python -m <name> <args>`."""
    def fn():
        sys.argv = [name, *(args or [])]
        runpy.run_module(name, run_name="__main__", alter_sys=True)
    return _exec(f"python -m {name} {' '.join(args or [])}".rstrip(), fn, soft)


def script(name: str, args: list[str] | None = None, soft: bool = False) -> bool:
    """`python scripts/<name>.py <args>`."""
    path = ROOT / "scripts" / f"{name}.py"
    def fn():
        sys.argv = [str(path), *(args or [])]
        runpy.run_path(str(path), run_name="__main__")
    return _exec(f"python scripts/{name}.py {' '.join(args or [])}".rstrip(), fn, soft)


def dispatch(prog: str, table: dict[str, tuple], argv: list[str]) -> int:
    """argv[0] picks an entry of `table` = {name: (help, callable(args))}; the rest is passed through."""
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in table:
        if argv and argv[0] not in ("-h", "--help"):
            print(f"{prog}: unknown '{argv[0]}'\n")
        width = max(len(k) for k in table)
        print(f"usage: python -m {prog} <what> [args]\n")
        for k, (h, _) in table.items():
            print(f"  {k:{width}}  {h}")
        return 2
    try:
        table[argv[0]][1](argv[1:])
    except StepFailed as e:
        print(f"{prog} {argv[0]}: stopped at {e}")
        return 1
    return 0
