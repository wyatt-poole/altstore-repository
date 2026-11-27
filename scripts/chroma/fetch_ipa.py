#!/usr/bin/env python3
"""Find the Chroma release to build and download the matching decrypted Spotify IPA.

Writes should_build / chroma_ver / spotify_ver / base_source to $GITHUB_OUTPUT.
Exits 0 whenever there is simply nothing to build, so scheduled runs stay green.

Environment:
  GH_TOKEN        token for the GitHub API (60 req/h unauthenticated is not enough on shared runners)
  CHROMA_CHANNEL  "stable" (default: the kit chroma.pw marks recommended) or "beta" (newest kit)
  BASE_IPA_URL    skip discovery and download this exact decrypted IPA
  FORCE_BUILD     "true" to build even if state.json already matches
"""

import json
import os
import plistlib
import re
import struct
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "chroma-state.json"
OUT_FILE = ROOT / "base_spotify.ipa"
MIN_SIZE = 50 * 1024 * 1024
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
SPOTIFY_APP_STORE_ID = "324684580"

session = requests.Session()
session.headers["User-Agent"] = UA


def log(msg):
    print(msg, flush=True)


def set_output(**values):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in values.items()]
    if path:
        with open(path, "a") as f:
            f.write("\n".join(lines) + "\n")
    for line in lines:
        log(f"  output {line}")


def finish_without_build(reason):
    log(reason)
    set_output(should_build="false")
    sys.exit(0)


# ---------------------------------------------------------------- version discovery

def discover_versions():
    """Return (chroma_ver, spotify_ver). The JSON API is what the patch page itself reads."""
    channel = os.environ.get("CHROMA_CHANNEL", "stable").strip().lower()
    try:
        r = session.get("https://chroma.pw/api/patcher", timeout=30)
        r.raise_for_status()
        kits = r.json()["kits"]
        if channel == "beta":
            kit = kits[0]
        else:
            kit = next((k for k in kits if k.get("recommended")), None) \
                or next(k for k in kits if not k.get("prerelease"))
        log(f"chroma.pw API: Chroma {kit['version']} for Spotify {kit['spotify']} ({channel})")
        return kit["version"], kit["spotify"]
    except Exception as e:  # noqa: BLE001 - fall back to scraping on any API change
        log(f"::warning::chroma.pw API failed ({e}); scraping the patch page instead")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.goto("https://chroma.pw/patch", wait_until="networkidle", timeout=90_000)
        text = page.inner_text("body")
        browser.close()
    m = re.search(r"Chroma\s+([\d.]+(?:-[\w.]+)?)\s*for\s*Spotify\s+([\d.]+)", text, re.I)
    if not m:
        raise SystemExit("::error::Could not find 'Chroma X for Spotify Y' on chroma.pw/patch")
    log(f"chroma.pw page: Chroma {m.group(1)} for Spotify {m.group(2)}")
    return m.group(1), m.group(2)


# ---------------------------------------------------------------- IPA validation

def _cryptid(macho: bytes):
    """Return LC_ENCRYPTION_INFO cryptid of a (thin or fat) Mach-O, or None if absent."""
    magic = struct.unpack_from(">I", macho)[0]
    if magic in (0xCAFEBABE, 0xCAFEBABF):  # fat: check the first slice
        n = struct.unpack_from(">I", macho, 4)[0]
        if n == 0:
            return None
        off = struct.unpack_from(">I", macho, 8 + 8)[0] if magic == 0xCAFEBABE \
            else struct.unpack_from(">Q", macho, 8 + 8)[0]
        return _cryptid(macho[off:])
    magic_le = struct.unpack_from("<I", macho)[0]
    if magic_le not in (0xFEEDFACF, 0xFEEDFACE):
        return None
    ncmds = struct.unpack_from("<I", macho, 16)[0]
    off = 32 if magic_le == 0xFEEDFACF else 28
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", macho, off)
        if cmd in (0x21, 0x2C):  # LC_ENCRYPTION_INFO(_64)
            return struct.unpack_from("<I", macho, off + 16)[0]
        off += size
    return None


def validate_ipa(path: Path, spotify_ver: str):
    """Raise ValueError unless this is a vanilla, decrypted Spotify IPA of the wanted version."""
    size = path.stat().st_size
    if size < MIN_SIZE:
        raise ValueError(f"too small ({size} bytes)")
    if not zipfile.is_zipfile(path):
        raise ValueError("not a ZIP archive")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        plist_name = next((n for n in names if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)), None)
        if not plist_name:
            raise ValueError("no Payload/*.app/Info.plist")
        info = plistlib.loads(z.read(plist_name))
        app_dir = plist_name.rsplit("/", 1)[0]
        if info.get("CFBundleIdentifier") != "com.spotify.client":
            raise ValueError(f"bundle id is {info.get('CFBundleIdentifier')}")
        if info.get("CFBundleShortVersionString") != spotify_ver:
            raise ValueError(f"version is {info.get('CFBundleShortVersionString')}, want {spotify_ver}")
        tweaked = [n for n in names if re.search(r"(eevee|spotifyglass|chroma|substrate|ellekit)", n, re.I)
                   and n.startswith(app_dir)]
        if tweaked:
            raise ValueError(f"already tweaked ({tweaked[0]})")
        exe = f"{app_dir}/{info.get('CFBundleExecutable', 'Spotify')}"
        with z.open(exe) as f:
            header = f.read(1 << 20)
        try:
            encrypted = bool(_cryptid(header))
        except struct.error:
            encrypted = False  # unusual layout; chroma.pw checks encryption itself too
        if encrypted:
            raise ValueError("main binary is still FairPlay-encrypted")


# ---------------------------------------------------------------- downloading

def normalize_url(url: str) -> str:
    m = re.match(r"https?://pixeldrain\.com/u/(\w+)", url)
    if m:
        return f"https://pixeldrain.com/api/file/{m.group(1)}?download"
    return url


def try_download(url: str, spotify_ver: str, source: str) -> bool:
    url = normalize_url(url)
    tmp = OUT_FILE.with_suffix(".ipa.part")
    log(f"  trying {url}")
    try:
        headers = {}
        if "api.github.com" in url:
            headers["Accept"] = "application/octet-stream"
            if os.environ.get("GH_TOKEN"):
                headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
        with session.get(url, stream=True, timeout=60, allow_redirects=True, headers=headers) as r:
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200 or "text/html" in ctype:
                log(f"    skip: HTTP {r.status_code} {ctype}")
                return False
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        validate_ipa(tmp, spotify_ver)
    except (requests.RequestException, ValueError, zipfile.BadZipFile, KeyError, struct.error) as e:
        log(f"    rejected: {e}")
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(OUT_FILE)
    log(f"  OK from {source}: {OUT_FILE.stat().st_size / 1e6:.1f} MB")
    return True


# ---------------------------------------------------------------- sources

def gh_releases(repo: str):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    r = session.get(f"https://api.github.com/repos/{repo}/releases?per_page=30", headers=headers, timeout=30)
    if r.status_code != 200:
        log(f"  GitHub API {repo}: HTTP {r.status_code}")
        return []
    return r.json()


PATCHED = re.compile(r"eevee|patched|tweaked|chroma|modded|injected", re.I)
UNPATCHED = re.compile(r"un-?patched|non-?patched|not patched|unmodified|vanilla|original|clean|base ipa|decrypted only", re.I)
URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")


def body_candidates(body: str):
    """URLs in a release body, preferring ones labelled unpatched, else the last one."""
    found = []  # (url, label)
    lines = (body or "").splitlines()
    for i, line in enumerate(lines):
        for url in URL_RE.findall(line):
            url = url.rstrip(".,")
            if url.lower().endswith(".ipa") or re.search(r"catbox\.moe|pixeldrain\.com", url):
                label = " ".join(lines[max(0, i - 1):i + 1])
                found.append((url, re.sub(URL_RE, "", label)))
    unpatched = [u for u, label in found if UNPATCHED.search(label)]
    if unpatched:
        return unpatched
    neutral = [u for u, label in found if not PATCHED.search(label)]
    # EeveePrebuilt lists the patched IPA first and the stock one last.
    return list(reversed(neutral or [u for u, _ in found]))


def source_pweevee(ver):
    for rel in gh_releases("codeboy2012/PwEevee"):
        for a in rel.get("assets", []):
            name = a["name"]
            if (name.endswith(".ipa") and ver in name
                    and re.search(r"com\.spotify\.client|und3fined", name, re.I)
                    and not PATCHED.search(name)):
                yield a["browser_download_url"]


def source_release_bodies(repo):
    def gen(ver):
        for rel in gh_releases(repo):
            text = f"{rel.get('tag_name', '')} {rel.get('name') or ''} {rel.get('body') or ''}"
            if ver not in text:
                continue
            assets = [a for a in rel.get("assets", []) if a["name"].endswith(".ipa")]
            stock = [a for a in assets if UNPATCHED.search(a["name"]) or not PATCHED.search(a["name"])]
            for a in stock:
                yield a["browser_download_url"]
            yield from body_candidates(rel.get("body"))
    return gen


def source_decrypt_day(ver):
    """Best effort: decrypt.day is behind Cloudflare and often wants a login."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            page.goto(f"https://decrypt.day/app/id{SPOTIFY_APP_STORE_ID}", wait_until="networkidle", timeout=60_000)
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.href, e.innerText + ' ' + (e.closest('li,tr,div')?.innerText || '')])")
            browser.close()
    except Exception as e:  # noqa: BLE001
        log(f"  decrypt.day unavailable: {e}")
        return
    for href, text in links:
        if ver in text and re.search(r"download|\.ipa", href + text, re.I):
            yield href


SOURCES = [
    ("codeboy2012/PwEevee", source_pweevee),
    ("NotDarkn/EeveePrebuilt", source_release_bodies("NotDarkn/EeveePrebuilt")),
    ("estrogencat/EeveeIPA", source_release_bodies("estrogencat/EeveeIPA")),
    ("decrypt.day", source_decrypt_day),
]


def main():
    chroma_ver, spotify_ver = discover_versions()
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    force = os.environ.get("FORCE_BUILD", "").lower() == "true"
    if not force and state.get("chroma") == chroma_ver and state.get("spotify") == spotify_ver:
        finish_without_build("Already up to date")

    if OUT_FILE.exists():
        OUT_FILE.unlink()

    override = os.environ.get("BASE_IPA_URL", "").strip()
    sources = [("BASE_IPA_URL", lambda _v: iter([override]))] if override else SOURCES

    for name, finder in sources:
        log(f"Searching {name} for Spotify {spotify_ver}")
        seen = set()
        try:
            for url in finder(spotify_ver):
                if url in seen:
                    continue
                seen.add(url)
                if try_download(url, spotify_ver, name):
                    set_output(should_build="true", chroma_ver=chroma_ver,
                               spotify_ver=spotify_ver, base_source=name)
                    return
        except requests.RequestException as e:
            log(f"  {name} failed: {e}")

    log(f"::warning::Target Spotify {spotify_ver} not yet available in fallback sources")
    set_output(should_build="false")


if __name__ == "__main__":
    main()
