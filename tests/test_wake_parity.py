"""The map's in-browser wake models (web/index.html) agree with PyWake (pipeline/wake.py).

The page draws wake losses live with JavaScript copies of three PyWake models. This test runs the page's own `run()`
in node on a few farms from tests/fixtures/data/site.json and compares farm power with the PyWake numbers stored in
tests/fixtures/wake_reference.json (rebuild with tests/fixtures/make_wake_reference.py after changing either side).
No network, no PyWake needed at test time.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "index.html"
REF = ROOT / "tests" / "fixtures" / "wake_reference.json"
SITE = ROOT / "tests" / "fixtures" / "data" / "site.json"

# browser model key -> PyWake model name, allowed error as share of no-wake farm power
MODELS = {"j": "jensen", "g": "bastankhah", "t": "turbopark"}
TOL = 0.005         # 0.5 % of the farm's no-wake power (measured agreement Oct 2026: ~0.001 %)


def wake_js() -> str:
    """The wake-model source from the page: power/thrust curves (URG, PC, CT) and the 'in-browser wake models' block."""
    s = PAGE.read_text(encoding="utf-8")
    curves = re.search(r"^const URG=.*?\n^const CT=.*?$", s, re.M | re.S)
    block = re.search(r"/\* -+ in-browser wake models \(map heatmap \+ what-if\) -+ \*/.*?(?=^function spacingOf)", s, re.M | re.S)
    assert curves and block, "wake-model code not found in web/index.html (markers moved?)"
    return curves.group(0) + "\n" + block.group(0)


@pytest.fixture(scope="module")
def browser_power():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    ref = json.loads(REF.read_text())
    harness = f"""
const DATA = JSON.parse(require('fs').readFileSync({json.dumps(str(SITE))}, 'utf8'));
const TY = DATA.types || [];
{wake_js()}
const ref = {json.dumps(ref)};
const out = {{}};
for (const id of Object.keys(ref.farms)) {{
  const f = DATA.farms.find(x => String(x.id) === id);
  // farm preparation as in the page
  f.lay = !!f.xy; f.tix = f.lay && f.ti != null && TY.length ? (Array.isArray(f.ti) ? f.ti : Array(f.xy.length / 2).fill(f.ti)) : null;
  out[id] = {{}};
  for (const m of {json.dumps(list(MODELS) + ["n"])})
    out[id][m] = ref.cases.map(([U, dir]) => run(f, m, U, dir, K_DEF[m] || 0).pw);
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return ref, json.loads(r.stdout)


def test_nowake_matches(browser_power):
    ref, js = browser_power
    for fid, r in ref["farms"].items():
        for i, (a, b) in enumerate(zip(js[fid]["n"], r["nowake"])):
            assert abs(a - b) <= 0.002 * max(b, 1), f"{r['name']} case {ref['cases'][i]}: no-wake {a:.1f} vs PyWake {b:.1f} MW"


@pytest.mark.parametrize("key", list(MODELS))
def test_wake_model_matches_pywake(browser_power, key):
    ref, js = browser_power
    bad = []
    for fid, r in ref["farms"].items():
        for i, (a, b) in enumerate(zip(js[fid][key], r[MODELS[key]])):
            if abs(a - b) > TOL * max(r["nowake"][i], 1):
                bad.append(f"{r['name']} U={ref['cases'][i][0]} dir={ref['cases'][i][1]}: browser {a:.1f} vs PyWake {b:.1f} MW")
    assert not bad, f"{MODELS[key]}: " + "; ".join(bad)
