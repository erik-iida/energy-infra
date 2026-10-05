"""Browser smoke test: the page opens on the test data and every tab draws something, with no script errors.

    python -m pytest tests/e2e -q                     # needs playwright + chromium
    UPDATE_BASELINE=1 python -m pytest tests/e2e -q   # rewrite tests/e2e/baseline/*.jpg

web/ is served locally with tests/fixtures/data as data/ (the committed web/data is never touched). Requests to any
other host (basemap tiles, fonts) are blocked, and the clock is fixed at the test data's "now", so the run is the same
every time and needs no network. Each tab is opened at desktop size with 125 % scaling (Erik's screen) and at phone
width; screenshots go to tests/e2e/out/ (uploaded by the checks workflow), baselines live in tests/e2e/baseline/.
"""
import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
WEB, FIX = ROOT / "web", ROOT / "tests" / "fixtures" / "data"
OUT, BASE = Path(__file__).parent / "out", Path(__file__).parent / "baseline"
NOW = "2026-10-04T11:30:00Z"          # tests/fixtures/make_fixtures.py NOW (+30 min)
TABS = ["map", "cmp", "mkt", "sys", "flg", "nws", "dat"]
PANE = {"cmp": "#dash", "mkt": "#mkt", "sys": "#sys", "flg": "#flg", "nws": "#nws", "dat": "#dat"}
VIEWS = {"desk125": dict(viewport={"width": 1536, "height": 864}, device_scale_factor=1.25),   # 1920x1080 at 125 %
         "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)}
DEEP = "#flags/GR/neg_hours/2026-10-03"   # a signal in the fixture flags whose zone has an hourly series


class Handler(SimpleHTTPRequestHandler):
    """web/ as the site root, tests/fixtures/data as data/."""
    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/data/"):
            return str(FIX / p[len("/data/"):])
        return super().translate_path(path)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(WEB)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        exe = os.environ.get("CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        yield b
        b.close()


def open_page(browser, base_url, view, hash_=""):
    ctx = browser.new_context(**VIEWS[view], timezone_id="Europe/Copenhagen", locale="en-GB")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: m.type == "error" and "net::ERR" not in m.text and "Failed to load resource" not in m.text
            and errors.append(f"console: {m.text}"))
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base_url) else r.abort())
    page.clock.set_fixed_time(NOW)
    page.goto(base_url + hash_)
    page.wait_for_function("document.querySelector('#tabs button.on') && document.getElementById('C2').options.length > 0",
                           timeout=20000)
    page.wait_for_timeout(800)
    return ctx, page, errors


def shot(page, name):
    OUT.mkdir(exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.jpg"), type="jpeg", quality=70, full_page=False)
    if os.environ.get("UPDATE_BASELINE"):
        BASE.mkdir(exist_ok=True)
        page.screenshot(path=str(BASE / f"{name}.jpg"), type="jpeg", quality=70, full_page=False)


def map_painted(page) -> bool:
    """The map canvas has more than a handful of distinct colours (zones, farms, coast drawn)."""
    return page.evaluate("""() => { const c = document.getElementById('cv'); if (!c || !c.width) return false;
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, s = new Set();
      for (let i = 0; i < d.length; i += 4 * 97) s.add(d[i] << 16 | d[i+1] << 8 | d[i+2]);
      return s.size > 20; }""")


def pane_filled(page, sel) -> dict:
    return page.evaluate("""sel => { const e = document.querySelector(sel); if (!e) return {ok: false, why: 'missing'};
      const r = e.getBoundingClientRect(), txt = e.innerText.trim().length,
            gfx = [...e.querySelectorAll('svg, canvas')].filter(g => { const b = g.getBoundingClientRect(); return b.width > 40 && b.height > 20 }).length;
      return {ok: r.height > 100 && txt > 200, txt, gfx, h: Math.round(r.height)}; }""", sel)


@pytest.mark.parametrize("view", list(VIEWS))
def test_all_tabs(browser, base_url, view):
    ctx, page, errors = open_page(browser, base_url, view)
    try:
        for t in TABS:
            page.click(f'#tabs button[data-t="{t}"]')
            page.wait_for_timeout(700)
            shot(page, f"{view}_{t}")
            if t == "map":
                assert map_painted(page), f"{view}: map canvas looks empty"
            else:
                r = pane_filled(page, PANE[t])
                assert r["ok"], f"{view}/{t}: pane looks empty {r}"
                if t in ("cmp", "mkt", "sys"):
                    assert r["gfx"] > 0, f"{view}/{t}: no chart drawn {r}"
                if t == "dat":
                    assert page.locator("#dat table tr").count() > 20, f"{view}/dat: data table has no rows"
        assert not errors, f"{view}: script errors: {errors[:5]}"
    finally:
        ctx.close()


def test_flags_deep_link_opens(browser, base_url):
    ctx, page, errors = open_page(browser, base_url, "desk125", DEEP)
    try:
        page.wait_for_timeout(1500)
        assert page.evaluate("document.querySelector('#tabs button.on').dataset.t") == "flg"
        r = page.evaluate("""() => { const p = document.querySelector('#flg .fxp');
          return p ? {txt: p.innerText.length, gfx: p.querySelectorAll('svg').length} : null }""")
        assert r and r["gfx"] > 0, f"drill-down panel not open for {DEEP}: {r}"
        # merit order (fixture feed has a synthetic market.srmc): a stack, the demand line and a marginal block in the caption
        m = page.evaluate("""() => { const s = document.querySelector('#flg svg.fxmo'); if (!s) return null;
          const cap = s.closest('.fxch').nextElementSibling.nextElementSibling.innerText;
          return {blocks: s.querySelectorAll('rect[data-mt]').length, cap} }""")
        assert m and m["blocks"] >= 3 and "Marginal block" in m["cap"], f"merit order not drawn: {m}"
        page.select_option("#fxmh", "11")
        page.wait_for_timeout(600)
        cap = page.evaluate("[...document.querySelectorAll('#flg .fxcap')].map(e => e.innerText).join(' ')")
        assert "At 11:00 CET" in cap, "hour selector did not redraw the merit order"
        shot(page, "desk125_flags_deeplink")
        assert not errors, f"script errors: {errors[:5]}"
    finally:
        ctx.close()
