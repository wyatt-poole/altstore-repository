#!/usr/bin/env python3
"""IPA post-processing and AltStore / SideStore source generation.

  update_repo.py stamp IPA BUILD
      Set CFBundleVersion in the IPA (and its Watch app / extensions) to BUILD, so a new
      Chroma build of the same Spotify version still shows up as an update.

  update_repo.py restore-watch BASE_IPA IPA
      Copy the Watch app from BASE_IPA back into IPA (Chroma strips it).

  update_repo.py TAG SPOTIFY_VER CHROMA_VER REPO_SLUG [--build N] [--eevee VER]
      For each variant in chroma-variants.json whose IPA was built, add the build to
      that variant's feeds (keeping the newest 3 versions). If DOWNLOAD_BASE_URL is set
      (e.g. a Cloudflare Worker fronting a private repo), downloads go through it.
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
VARIANTS = ROOT / "chroma-variants.json"
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
        sys.exit(2)
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


def default_source(owner: str, repo_url: str, feed: Path, name: str) -> dict:
    return {
        "name": name,
        "identifier": f"com.{owner.lower()}.{feed.stem}",
        "apiVersion": "v2",
        "subtitle": "Auto-built Spotify with Chroma",
        "description": f"Unofficial {name} IPA, rebuilt automatically when Chroma updates. "
                       f"More variants: {repo_url}#spotify--chroma",
        "iconURL": spotify_icon_url(),
        "website": repo_url,
        "tintColor": "1DB954",
        "apps": [],
        "news": [],
    }


def update_feed(feed: Path, tag, spotify_ver, chroma_ver, ipa: Path, asset, repo_slug,
                name="Spotify + Chroma", build=None, eevee=None, watch=False, newest=None):
    owner = repo_slug.split("/")[0]
    repo_url = f"https://github.com/{repo_slug}"
    base = os.environ.get("DOWNLOAD_BASE_URL", "").rstrip("/")
    download_url = f"{base}/{tag}/{asset}" if base else f"{repo_url}/releases/download/{tag}/{asset}"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    size = os.path.getsize(ipa)
    digest = sha256(ipa)

    data = json.loads(feed.read_text()) if feed.exists() else default_source(owner, repo_url, feed, name)
    app = next((x for x in data.get("apps", []) if x.get("bundleIdentifier") == BUNDLE_ID), None)
    if app is None:
        app = {
            "bundleIdentifier": BUNDLE_ID,
            "developerName": "Chroma",
            "subtitle": "Spotify with Chroma's shaders and lyrics",
            "iconURL": spotify_icon_url(),
            "tintColor": "1DB954",
            "category": "entertainment",
            "screenshots": [],
            "versions": [],
            "appPermissions": {"entitlements": [], "privacy": {}},
        }
        data.setdefault("apps", []).append(app)
    extras = "".join([
        " EeveeSpotify is included." if eevee else "",
        " The Watch app is included (experimental: needs a paid Apple ID and a signer that installs Watch apps)." if watch else "",
    ])
    # Only the source listing shows this name; the home screen keeps the IPA's own "Spotify".
    app["name"] = f"{name} (Chroma {chroma_ver})"
    app["subtitle"] = f"Chroma {chroma_ver} · Spotify {spotify_ver}"
    app["localizedDescription"] = ("Spotify patched with Chroma (chroma.pw): shaders behind the player, "
                                   "word-by-word lyrics, lock-screen lyrics and more." + extras +
                                   " Rebuilt automatically when Chroma updates.")

    parts = [f"Chroma {chroma_ver}"] + ([f"EeveeSpotify {eevee}"] if eevee else []) + (["Watch app"] if watch else [])
    description = f"Spotify {spotify_ver} + " + " + ".join(parts) + "."
    if newest:
        description += (f" Older Chroma: the newest ({newest}) is waiting on a decrypted Spotify IPA. "
                        "This updates automatically once one is available.")
    entry = {
        "version": spotify_ver,
        "buildVersion": build or spotify_ver,
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

    feed.parent.mkdir(parents=True, exist_ok=True)
    feed.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{feed.relative_to(ROOT)}: {name} {spotify_ver} (build {entry['buildVersion']}) -> {download_url}")


def update_variants(a):
    """Add every built variant in chroma-variants.json to its own feed, and the preferred
    built variant to the main feed (apps.json, shared with YouMod)."""
    cfg = json.loads(VARIANTS.read_text())
    by_asset = {v["asset"]: v for v in cfg["variants"]}

    def publish(v, feed):
        update_feed(ROOT / feed, a.tag, a.spotify_ver, a.chroma_ver, ROOT / v["asset"], v["asset"], a.repo_slug,
                    name=v["name"], build=a.build, eevee=a.eevee if v["eevee"] else None, watch=v["watch"],
                    newest=a.newest or None)

    for v in cfg["variants"]:
        if (ROOT / v["asset"]).exists():
            publish(v, v["feed"])
        else:
            print(f"skip {v['name']}: {v['asset']} was not built")

    main = cfg["main_feed"]
    pick = next((by_asset[x] for x in main["prefer"] if (ROOT / x).exists()), None)
    if pick:
        publish(pick, main["feed"])
    else:
        print(f"::warning::none of {main['prefer']} was built; {main['feed']} not updated")


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
    p.add_argument("repo_slug")
    p.add_argument("--build", help="CFBundleVersion stamped into the IPAs")
    p.add_argument("--eevee", help="EeveeSpotify version in the Eevee variants")
    p.add_argument("--newest", help="newest Chroma kit, when an older one was built as a fallback")
    update_variants(p.parse_args(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
