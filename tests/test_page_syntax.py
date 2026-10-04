"""The page's JavaScript parses (node --check on the inline <script> of web/index.html)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_page_script_parses(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", PAGE.read_text(encoding="utf-8"), re.S)
    assert scripts, "no inline <script> in web/index.html"
    js = tmp_path / "page.js"
    js.write_text("\n;\n".join(scripts), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
