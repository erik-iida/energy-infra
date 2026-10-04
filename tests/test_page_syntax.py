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
    # `node --check file.js` silently passes a .js file that contains `import` (the module/CommonJS guess skips the
    # check, seen with Node 22): feed the source on stdin with --input-type=module, which really parses it.
    for f in files:
        with open(f, "rb") as src:
            r = subprocess.run(["node", "--input-type=module", "--check"], stdin=src, capture_output=True, text=True)
        assert r.returncode == 0, f"{f}: {r.stderr[-2000:]}"
