"""Publish the site from a machine that is not GitHub Actions (Render).

    python -m jobs.publish cloudflare   dist/ -> Cloudflare Pages project CF_PAGES_PUBLIC (the public site) and, when SPARK=private
                                        and site_private/ exists, site_private/ -> CF_PAGES_PROJECT (the login-protected copy).
                                        Needs CLOUDFLARE_API_TOKEN (Pages: Edit), CLOUDFLARE_ACCOUNT_ID, and wrangler (in the image).
    python -m jobs.publish pages        zip build/data -> asset `built-data.zip` of the GitHub release `built-data`, then dispatch
                                        deploy.yml with source=release (it assembles dist/ and publishes to GitHub Pages). Needs
                                        GH_TOKEN (contents + actions write) and GITHUB_REPOSITORY. Fallback / transition path.

The public feed must already be stripped of spark spreads (jobs.render site does that). Nothing touches the repo:
no commit, no data in git.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import zipfile

import requests

from common import paths

API = "https://api.github.com"
TAG = "built-data"
ASSET = "built-data.zip"


def _hdr():
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise SystemExit("GH_TOKEN not set")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _repo() -> str:
    r = os.environ.get("GITHUB_REPOSITORY")
    if not r:
        raise SystemExit("GITHUB_REPOSITORY not set (owner/repo)")
    return r


def zip_build() -> bytes:
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths.BUILD_DATA.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(paths.BUILD_DATA).as_posix())
                n += 1
    if not n:
        raise SystemExit(f"nothing to publish: {paths.BUILD_DATA} is empty")
    print(f"publish: {n} files, {buf.tell() / 1e6:.1f} MB zipped")
    return buf.getvalue()


def upload_release_asset(data: bytes) -> None:
    repo, h = _repo(), _hdr()
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{TAG}", headers=h, timeout=60)
    if r.status_code == 404:
        r = requests.post(f"{API}/repos/{repo}/releases", headers=h, timeout=60, json={
            "tag_name": TAG, "name": "Built site data", "prerelease": True, "make_latest": "false",
            "body": "feed.json, browse/, newsletter/, meta.json of the newest back-end run (written by jobs.publish; "
                    "deploy.yml reads it). Overwritten every run."})
    r.raise_for_status()
    rel = r.json()
    for a in rel.get("assets", []):
        if a["name"] == ASSET:
            requests.delete(f"{API}/repos/{repo}/releases/assets/{a['id']}", headers=h, timeout=60).raise_for_status()
    up = rel["upload_url"].split("{")[0]
    r = requests.post(f"{up}?name={ASSET}", headers={**h, "Content-Type": "application/zip"}, data=data, timeout=300)
    r.raise_for_status()
    print(f"publish: uploaded {ASSET} to release {TAG}")


def dispatch_deploy() -> None:
    repo, h = _repo(), _hdr()
    r = requests.post(f"{API}/repos/{repo}/actions/workflows/deploy.yml/dispatches", headers=h, timeout=60,
                      json={"ref": "main", "inputs": {"source": "release"}})
    r.raise_for_status()
    print("publish: deploy.yml dispatched (source=release)")


def pages(args: list[str]) -> None:
    data = zip_build()
    if "--dry-run" in args:
        print("publish: dry run, not uploading")
        return
    upload_release_asset(data)
    dispatch_deploy()


def _wrangler(folder, project: str) -> None:
    exe = shutil.which("wrangler") or shutil.which("npx")
    if not exe:
        raise SystemExit("wrangler not installed (the Docker image has it; locally: npm i -g wrangler)")
    cmd = ([exe] if exe.endswith("wrangler") else [exe, "--yes", "wrangler"]) + \
          ["pages", "deploy", str(folder), "--project-name", project, "--branch", "main", "--commit-dirty=true"]
    env = {k: v for k, v in os.environ.items()}
    for k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not env.get(k):
            raise SystemExit(f"{k} not set")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
    tail = (r.stdout + r.stderr)[-1500:]
    tail = tail.replace(env["CLOUDFLARE_API_TOKEN"], "***")
    if r.returncode != 0:
        raise SystemExit(f"wrangler pages deploy {project} failed:\n{tail}")
    url = [ln for ln in tail.splitlines() if "https://" in ln]
    print(f"publish: {folder} -> Cloudflare Pages project {project}" + (f" ({url[-1].strip()})" if url else ""))


def cloudflare(args: list[str]) -> None:
    pub = os.environ.get("CF_PAGES_PUBLIC", "")
    if not pub:
        raise SystemExit("CF_PAGES_PUBLIC not set (the Pages project name of the public site)")
    if not (paths.DIST / "index.html").exists():
        raise SystemExit(f"nothing to publish: {paths.DIST} is empty (run jobs.render site first)")
    if "--dry-run" in args:
        print(f"publish: dry run, would deploy {paths.DIST} to {pub}")
        return
    _wrangler(paths.DIST, pub)
    priv = paths.ROOT / "site_private"
    proj = os.environ.get("CF_PAGES_PROJECT", "")
    if os.environ.get("SPARK") == "private" and proj and (priv / "index.html").exists():
        _wrangler(priv, proj)


TABLE = {
    "cloudflare": ("dist/ -> Cloudflare Pages (CF_PAGES_PUBLIC; site_private/ -> CF_PAGES_PROJECT when SPARK=private)", cloudflare),
    "pages": ("build/data -> release asset built-data.zip -> dispatch deploy.yml (GitHub Pages); fallback", pages),
}

if __name__ == "__main__":
    from . import _run
    raise SystemExit(_run.dispatch("jobs.publish", TABLE, sys.argv[1:]))
