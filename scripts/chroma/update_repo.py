#!/usr/bin/env python3
"""IPA post-processing and AltStore / SideStore source generation.

  update_repo.py stamp IPA BUILD
      Set CFBundleVersion in the IPA (and its Watch app / extensions) to BUILD, so a new
      Chroma build of the same Spotify version still shows up as an update.

  update_repo.py restore-watch BASE_IPA IPA
      Copy the Watch app from BASE_IPA back into IPA (Chroma strips it).

  update_repo.py TAG SPOTIFY_VER CHROMA_VER IPA_PATH REPO_SLUG [--build N] [--eevee VER]
      Add this build to apps.json, keeping the newest 3 versions.
      If DOWNLOAD_BASE_URL is set (e.g. a Cloudflare Worker fronting a private repo),
      downloadURL becomes {DOWNLOAD_BASE_URL}/{TAG}/Spotify.ipa.
"""

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS_JSON = ROOT / "apps.json"
BUNDLE_ID = "com.spotify.client"
KEEP_VERSIONS = 3
APP_STORE_ID = "324684580"


INFO_RE = re.compile(r"Payload/[^/]+\.app/Info\.plist")


def app_info(ipa: Path) -> dict:
    with zipfile.ZipFile(ipa) as z:
        return plistlib.loads(z.read(next(n for n in z.namelist() if INFO_RE.fullmatch(n))))


def rewrite_ipa(ipa: Path, edit):
    """Copy ipa entry by entry; edit(name, data) returns new bytes, or None to drop the entry."""
    tmp = ipa.with_suffix(".tmp")
    with zipfile.ZipFile(ipa) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = edit(item.filename, src.read(item.filename))
            if data is not None:
                dst.writestr(item, data, compress_type=zipfile.ZIP_STORED if item.is_dir() else zipfile.ZIP_DEFLATED)
    shutil.move(tmp, ipa)


def stamp(ipa: Path, build: str):
    # The Watch app and extensions must carry the same CFBundleVersion as the app that contains them.
    old = app_info(ipa).get("CFBundleVersion")
    print(f"CFBundleVersion {old} -> {build}")

    def edit(name, data):
        if name.endswith("/Info.plist") and name.startswith("Payload/"):
            try:
                info = plistlib.loads(data)
            except Exception:  # noqa: BLE001 - not every Info.plist-named file is a bundle plist
                return data
            if info.get("CFBundleVersion") == old:
                info["CFBundleVersion"] = build
                return plistlib.dumps(info, fmt=plistlib.FMT_BINARY)
        return data
    rewrite_ipa(ipa, edit)


WATCH_DIRS = ("Watch/", "WatchKit/", "com.apple.WatchPlaceholder/")


def restore_watch(base: Path, ipa: Path):
    """Put back the Watch app that a patcher stripped, copied untouched from the base IPA."""
    with zipfile.ZipFile(base) as z:
        app_dir = next(n for n in z.namelist() if INFO_RE.fullmatch(n)).rsplit("/", 1)[0] + "/"
        watch = {i.filename: (i, z.read(i.filename)) for i in z.infolist()
                 if i.filename.startswith(tuple(app_dir + d for d in WATCH_DIRS))}
    if not watch:
        print("Base IPA has no Watch app; nothing to restore")
        return
    with zipfile.ZipFile(ipa, "a", zipfile.ZIP_DEFLATED) as z:
        present = set(z.namelist())
        for name, (info, data) in watch.items():
            if name not in present:
                z.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.is_dir() else zipfile.ZIP_DEFLATED)
    print(f"Restored {len(watch)} Watch entries from {base.name}")


def spotify_icon_url() -> str:
    try:
        with urllib.request.urlopen(f"https://itunes.apple.com/lookup?id={APP_STORE_ID}", timeout=20) as r:
            return json.load(r)["results"][0]["artworkUrl512"]
    except Exception:  # noqa: BLE001
        return ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def default_source(owner: str, repo_url: str) -> dict:
    return {
        "name": "Spotify + Chroma",
        "identifier": f"com.{owner.lower()}.chroma-spotify",
        "apiVersion": "v2",
        "subtitle": "Auto-built Spotify with Chroma",
        "description": "Unofficial Spotify IPA patched with Chroma (chroma.pw), rebuilt automatically when Chroma updates.",
        "website": repo_url,
        "apps": [],
        "news": [],
    }


def update_feed(a):
    ipa = Path(a.ipa_path)
    owner = a.repo_slug.split("/")[0]
    repo_url = f"https://github.com/{a.repo_slug}"
    base = os.environ.get("DOWNLOAD_BASE_URL", "").rstrip("/")
    download_url = f"{base}/{a.tag}/Spotify.ipa" if base else f"{repo_url}/releases/download/{a.tag}/Spotify.ipa"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    size = os.path.getsize(ipa)
    digest = sha256(ipa)

    data = json.loads(APPS_JSON.read_text()) if APPS_JSON.exists() else default_source(owner, repo_url)
    app = next((x for x in data.get("apps", []) if x.get("bundleIdentifier") == BUNDLE_ID), None)
    if app is None:
        app = {
            "name": "Spotify + Chroma",
            "bundleIdentifier": BUNDLE_ID,
            "developerName": "Chroma",
            "subtitle": "Spotify with Chroma's shaders and lyrics",
            "localizedDescription": "Spotify patched with Chroma: shaders behind the player, word-by-word lyrics, lock-screen lyrics and more.",
            "iconURL": spotify_icon_url(),
            "tintColor": "1DB954",
            "category": "entertainment",
            "screenshots": [],
            "versions": [],
            "appPermissions": {"entitlements": [], "privacy": {}},
        }
        data.setdefault("apps", []).append(app)

    extras = f" + EeveeSpotify {a.eevee}" if a.eevee else ""
    description = f"Spotify {a.spotify_ver} patched with Chroma {a.chroma_ver}{extras}."
    entry = {
        "version": a.spotify_ver,
        "buildVersion": a.build or a.spotify_ver,
        "date": now,
        "localizedDescription": description,
        "downloadURL": download_url,
        "size": size,
        "sha256": digest,
        "minOSVersion": app_info(ipa).get("MinimumOSVersion", "15.0"),
    }
    versions = [v for v in app.get("versions", []) if v.get("downloadURL") != download_url]
    app["versions"] = [entry] + versions[: KEEP_VERSIONS - 1]

    # Legacy (pre-v2) top-level fields, still read by older AltStore / Feather builds.
    app.update({
        "version": entry["version"],
        "versionDate": now,
        "versionDescription": description,
        "downloadURL": download_url,
        "size": size,
        "sha256": digest,
    })

    APPS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"apps.json: {a.spotify_ver} (build {entry['buildVersion']}) -> {download_url}")
    print(f"  size {size}  sha256 {digest}")


def main(argv):
    if argv and argv[0] in ("stamp", "restore-watch"):
        if len(argv) != 3:
            sys.exit("usage: update_repo.py stamp IPA BUILD | restore-watch BASE_IPA IPA")
        if argv[0] == "stamp":
            stamp(Path(argv[1]), argv[2])
        else:
            restore_watch(Path(argv[1]), Path(argv[2]))
        return
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tag")
    p.add_argument("spotify_ver")
    p.add_argument("chroma_ver")
    p.add_argument("ipa_path")
    p.add_argument("repo_slug")
    p.add_argument("--build", help="CFBundleVersion stamped into the IPA")
    p.add_argument("--eevee", help="EeveeSpotify version injected, if any")
    update_feed(p.parse_args(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
