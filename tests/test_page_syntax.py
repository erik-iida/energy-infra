"""The page's JavaScript parses: node --check on every file under web/js/ and on the inline <script> of web/index.html."""
import shutil
import subprocess

import pytest

from tests import pagejs


def test_page_script_parses(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    files = list(pagejs.js_files())
    inline = pagejs.inline_scripts()
    assert files or inline, "no page JavaScript found (web/js/*.js or inline <script> in web/index.html)"
    if inline:
        js = tmp_path / "inline.js"
        js.write_text("\n;\n".join(inline), encoding="utf-8")
        files.append(js)
    major = int(subprocess.run(["node", "-p", "process.versions.node.split('.')[0]"], capture_output=True, text=True).stdout or 0)
    flags = [] if major >= 22 else ["--experimental-detect-module"]   # ES modules in .js files: automatic from Node 22
    for f in files:
        r = subprocess.run(["node", *flags, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f}: {r.stderr[-2000:]}"
