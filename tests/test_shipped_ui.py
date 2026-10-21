"""The committed web UI export (src/hermes_jarvis/static/app) works with the server's security policy."""
import base64
import hashlib
import re

import pytest
from webhelpers import PASSWORD, login, with_client

from hermes_jarvis import admin as admin_mod

APP = admin_mod.APP_DIR
pytestmark = pytest.mark.skipif(not (APP / "index.html").exists(), reason="UI not built: run scripts/build_ui.sh")

PAGES = {"/": "index.html", "/login/": "login/index.html", "/setup/": "setup/index.html", "/settings/": "settings/index.html"}
INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)


def test_every_page_exists_and_has_inline_scripts_that_the_csp_can_hash():
    for rel in PAGES.values():
        html = (APP / rel).read_text()
        assert "<script" in html and "<html" in html, rel
        assert not re.search(r"\son[a-z]+=\"", html), f"{rel}: inline event handlers would need unsafe-inline"
        assert "<style" not in html or rel.startswith("404"), f"{rel}: an inline <style> block would be blocked"


def test_every_asset_a_page_references_is_shipped():
    missing = []
    for rel in PAGES.values():
        html = (APP / rel).read_text()
        for ref in re.findall(r'(?:src|href)="(/_next/[^"?#]+)', html):
            if not (APP / ref.lstrip("/")).is_file():
                missing.append((rel, ref))
    assert not missing, missing


def test_the_csp_covers_every_inline_script_and_nothing_unsafe():
    async def run(c, _s):
        out = {}
        responses = {"/login/": await c.get("/login/")}      # the login page is only served to signed-out visitors
        await login(c)
        for path in PAGES:
            responses.setdefault(path, await c.get(path))
        for path, rel in PAGES.items():
            r = responses[path]
            assert r.status == 200, path
            csp = r.headers["Content-Security-Policy"]
            html = (APP / rel).read_text()
            hashes = {base64.b64encode(hashlib.sha256(b.encode()).digest()).decode() for b in INLINE.findall(html) if b.strip()}
            script_src = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
            out[path] = (all(f"'sha256-{h}'" in script_src for h in hashes), "unsafe" in script_src, len(hashes))
        return out

    for path, (covered, unsafe, n) in with_client(run).items():
        assert covered and not unsafe and n > 0, path


def test_the_whole_signed_out_to_signed_in_flow_serves_the_real_app():
    async def run(c, _s):
        anon = await c.get("/", allow_redirects=False)
        login_page = await c.get("/login/")
        csrf = await login(c)
        dash = await c.get("/")
        asset = None
        for ref in re.findall(r'src="(/_next/static/[^"]+\.js)"', await dash.text()):
            asset = await c.get(ref)
            break
        out = await c.post("/api/logout", headers={"X-CSRF-Token": csrf, "Origin": f"http://{c.server.host}:{c.server.port}"})
        after = await c.get("/", allow_redirects=False)
        return anon.status, login_page.status, dash.status, asset.status if asset else None, out.status, after.status

    assert with_client(run) == (302, 200, 200, 200, 200, 302)


def test_pages_are_not_cached_but_built_assets_are():
    async def run(c, _s):
        await login(c)
        page = await c.get("/")
        ref = re.findall(r'src="(/_next/static/[^"]+\.js)"', await page.text())[0]
        asset = await c.get(ref)
        return page.headers["Cache-Control"], asset.headers["Cache-Control"]

    page, asset = with_client(run)
    assert page == "no-store" and "immutable" in asset
