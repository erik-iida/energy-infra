"""PyWake reference for the in-browser wake models (tests/test_wake_parity.py): tests/fixtures/wake_reference.json.

    python tests/fixtures/make_wake_reference.py      # needs py_wake (requirements.txt)

Farm power [MW] from pipeline/wake.farm_power for a few farms of tests/fixtures/data/site.json and wind cases chosen to
cover wake-heavy directions, partial load and rated output. Re-run when pipeline/wake.py or the browser models change.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import wake  # noqa: E402

FARMS = [6359, 6426, 23352, 6556]                   # Lillgrund, Anholt, Hollandse Kust Zuid, Gode Wind 1+2
CASES = [(7.0, 222.0), (9.5, 270.0), (11.0, 45.0), (14.0, 180.0)]  # (hub-height wind m/s, direction deg)


def main() -> None:
    site = json.loads((ROOT / "tests" / "fixtures" / "data" / "site.json").read_text())
    farms = {int(f["id"]): f for f in site["farms"]}
    ws = np.array([c[0] for c in CASES])
    wd = np.array([c[1] for c in CASES])
    out = {"cases": CASES, "farms": {}}
    for fid in FARMS:
        f = farms[fid]
        r = wake.farm_power(f, site["types"], ws, wd)
        out["farms"][str(fid)] = {"name": f["n"], **{k: [round(float(x), 3) for x in v] for k, v in r.items() if not k.startswith("_")}}
        print(f["n"], {k: [round(float(x), 1) for x in v] for k, v in r.items() if not k.startswith("_")})
    (ROOT / "tests" / "fixtures" / "wake_reference.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
