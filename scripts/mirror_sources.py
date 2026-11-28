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
import plistlib
import re
import struct
import zlib
import sys
import urllib.error
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

CACHE_DIR = ROOT / "mirrors" / ".cache"


def probe_ipa(url):
    """Return {"ok": bool, "bundle": str|None} by reading only the zip index and Info.plist.

    ok=False means the link is dead (404/410). bundle=None means it couldn't be read."""
    try:
        # Storage behind GitHub releases rejects suffix ranges ("bytes=-N"), so get the size first.
        req = urllib.request.Request(url, headers={"User-Agent": "source-mirror", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 206:
                return {"ok": True, "bundle": None}  # no range support: don't download the whole file
            total = int(r.headers["Content-Range"].rsplit("/", 1)[1])
        tail = _read(url, max(0, total - 65536), total - 1)
    except urllib.error.HTTPError as e:
        return {"ok": e.code not in (404, 410), "bundle": None}
    except Exception:  # noqa: BLE001
        return {"ok": True, "bundle": None}
    try:
        tail_start = total - len(tail)
        i = tail.rfind(b"PK\x05\x06")
        cd_size, cd_off = struct.unpack_from("<II", tail, i + 12)
        if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:  # zip64
            j = tail.rfind(b"PK\x06\x07")
            z64 = struct.unpack_from("<Q", tail, j + 8)[0]
            rec = tail[z64 - tail_start:] if z64 >= tail_start else _read(url, z64, z64 + 55)
            cd_size, cd_off = struct.unpack_from("<QQ", rec, 40)
        cd = tail[cd_off - tail_start:cd_off - tail_start + cd_size] if cd_off >= tail_start \
            else _read(url, cd_off, cd_off + cd_size - 1)
        pos = 0
        while pos + 46 <= len(cd) and cd[pos:pos + 4] == b"PK\x01\x02":
            method, = struct.unpack_from("<H", cd, pos + 10)
            csize, usize = struct.unpack_from("<II", cd, pos + 20)
            nlen, elen, clen = struct.unpack_from("<HHH", cd, pos + 28)
            loff, = struct.unpack_from("<I", cd, pos + 42)
            name = cd[pos + 46:pos + 46 + nlen].decode("utf-8", "replace")
            extra = cd[pos + 46 + nlen:pos + 46 + nlen + elen]
            if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", name):
                vals = iter(struct.unpack_from(f"<{len(extra[4:]) // 8}Q", extra, 4)) \
                    if extra[:2] == b"\x01\x00" else iter(())
                if usize == 0xFFFFFFFF: usize = next(vals)
                if csize == 0xFFFFFFFF: csize = next(vals)
                if loff == 0xFFFFFFFF: loff = next(vals)
                head = _read(url, loff, loff + 29)
                ln, le = struct.unpack_from("<HH", head, 26)
                data = _read(url, loff + 30 + ln + le, loff + 30 + ln + le + csize - 1)
                raw = zlib.decompress(data, -15) if method == 8 else data
                return {"ok": True, "bundle": plistlib.loads(raw).get("CFBundleIdentifier")}
            pos += 46 + nlen + elen + clen
    except Exception:  # noqa: BLE001 - unusual zip layout: leave the entry alone
        pass
    return {"ok": True, "bundle": None}


def _read(url, start, end):
    req = urllib.request.Request(url, headers={"User-Agent": "source-mirror", "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def check_downloads(name, data):
    """Drop dead download links and fix bundle IDs that don't match the IPA.

    Checks versions newest first until one works (older ones are left alone). Results are
    cached per URL in mirrors/.cache, so each new version is checked once."""
    cache_file = CACHE_DIR / f"{name}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    for app in data.get("apps", []):
        kept, found_working = [], False
        for v in app.get("versions", []):
            url = v.get("downloadURL", "")
            if found_working or not url.lower().split("?")[0].endswith(".ipa"):
                kept.append(v)
                continue
            if url not in cache:
                cache[url] = probe_ipa(url)
            if cache[url]["ok"]:
                kept.append(v)
                found_working = True
            else:
                print(f"  {app.get('name')}: dropped dead link {url}")
        if not kept and app.get("versions"):
            app["versions"] = []
            fill_versions(app)  # latest GitHub release, else placeholder
        else:
            app["versions"] = kept
        real = cache.get(app["versions"][0].get("downloadURL", ""), {}).get("bundle") if app["versions"] else None
        if real and real != app.get("bundleIdentifier"):
            print(f"  {app.get('name')}: bundle ID {app.get('bundleIdentifier')} -> {real} (from the IPA)")
            app["bundleIdentifier"] = real
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=0, sort_keys=True) + "\n")


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
        check_downloads(name, data)
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"{name}: {len(data.get('apps', []))} apps, filled {n} missing fields -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
