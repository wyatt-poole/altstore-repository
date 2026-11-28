#!/usr/bin/env python3
"""Mirror third-party AltStore/SideStore sources that SideStore refuses to load, with the
missing required fields filled in. Each mirror lives at mirrors/<name>.json.

  python3 scripts/mirror_sources.py OWNER/REPO

Apps without any version (source-code-only ports) get the newest .ipa from their GitHub
project's latest release if there is one (GH_TOKEN helps with rate limits), otherwise a
placeholder version linking to the project, so SideStore loads the source and keeps them listed.

OWNER/REPO is this repository, used to point each mirror's sourceURL at itself (otherwise
SideStore follows sourceURL back to the broken original on refresh).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MIRRORS = {
    "ryp0": "https://raw.githubusercontent.com/Sami-Wali/ryP0-repository/main/repo.json",
}


def latest_ipa(github_url: str):
    """Newest .ipa asset in a project's latest GitHub release, or None."""
    parts = github_url.rstrip("/").split("github.com/")[-1].split("/")
    if len(parts) < 2:
        return None
    headers = {"User-Agent": "source-mirror", "Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    req = urllib.request.Request(f"https://api.github.com/repos/{parts[0]}/{parts[1]}/releases/latest", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rel = json.load(r)
    except Exception:  # noqa: BLE001 - no releases, private, rate-limited...
        return None
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".ipa")), None)
    if not asset:
        return None
    return {
        "version": (rel.get("tag_name") or "1.0").lstrip("v"),
        "date": rel.get("published_at") or TODAY,
        "localizedDescription": rel.get("name") or rel.get("tag_name") or "",
        "downloadURL": asset["browser_download_url"],
        "size": asset["size"],
    }


def fill_versions(app: dict) -> str:
    """SideStore rejects apps with no versions. Use the project's released IPA if it has one,
    otherwise a placeholder pointing at the project page so the app stays listed."""
    if app.get("versions"):
        return ""
    if app.get("downloadURL"):  # legacy single-version fields
        app["versions"] = [{
            "version": app.get("version", "1.0"), "date": app.get("versionDate", TODAY),
            "localizedDescription": app.get("versionDescription", ""),
            "downloadURL": app["downloadURL"], "size": app.get("size", 0),
        }]
        return "legacy"
    url = app.get("githubURL", "")
    real = latest_ipa(url) if "github.com/" in url else None
    if real:
        app["versions"] = [real]
        return "release"
    app["versions"] = [{
        "version": "0",
        "date": TODAY,
        "localizedDescription": f"Source code only, no IPA to install. Build it yourself: {url or 'see the project page'}",
        "downloadURL": url or data_fallback_url(app),
        "size": 0,
    }]
    app["localizedDescription"] = "[Source code only, no IPA] " + app.get("localizedDescription", "")
    return "placeholder"


def data_fallback_url(app: dict) -> str:
    return app.get("website") or app.get("iconURL") or "https://github.com"


def fix(data: dict, self_url: str) -> int:
    fixed = 0
    for app in data.get("apps", []):
        how = fill_versions(app)
        if how:
            print(f"  {app.get('name')}: versions from {how}")
            fixed += 1
        for key, fallback in (
            ("localizedDescription", app.get("subtitle") or "No description"),
            ("developerName", "Unknown"),
            ("name", app.get("bundleIdentifier", "Unknown")),
            ("iconURL", data.get("iconURL", "")),
        ):
            if not app.get(key):
                app[key] = fallback
                fixed += 1
    data["sourceURL"] = self_url
    data["identifier"] = f"{data.get('identifier') or 'source'}.fixed"
    return fixed


def main(repo_slug: str):
    for name, url in MIRRORS.items():
        req = urllib.request.Request(url, headers={"User-Agent": "source-mirror"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        out = ROOT / "mirrors" / f"{name}.json"
        self_url = f"https://raw.githubusercontent.com/{repo_slug}/main/mirrors/{name}.json"
        n = fix(data, self_url)
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"{name}: {len(data.get('apps', []))} apps, filled {n} missing fields -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
