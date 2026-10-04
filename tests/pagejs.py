"""Where the page's JavaScript lives: inline <script> blocks in web/index.html plus every file under web/js/.

Spec 3 step 2 moves the script out of index.html into js/ files; the page tests read it through here so they do not
care how many files it is cut into.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
INDEX = WEB / "index.html"


def inline_scripts() -> list[str]:
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", INDEX.read_text(encoding="utf-8"), re.S)


def js_files() -> list[Path]:
    return sorted((WEB / "js").rglob("*.js")) if (WEB / "js").exists() else []


def all_js() -> str:
    """Every line of page JavaScript, files in path order, inline blocks last."""
    parts = [p.read_text(encoding="utf-8") for p in js_files()] + inline_scripts()
    return "\n;\n".join(parts)


def page_text() -> str:
    """index.html plus all page JavaScript (for tests that look for data paths or markers anywhere in the page)."""
    return INDEX.read_text(encoding="utf-8") + "\n" + all_js()
