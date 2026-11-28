---
name: tweaked-app-source
description: Build or extend an auto-updating AltStore/SideStore/Feather source for a tweaked iOS app. Use when the user wants a GitHub Actions pipeline that grabs a decrypted IPA, patches or injects tweaks (web patcher, prebuilt .deb, or tweaks compiled with Theos), publishes it to GitHub Releases and updates apps.json. Also covers app customisation (name, icon, bundle ID, extensions, Watch app) and what CarPlay, Watch and free Apple IDs allow.
---

# Tweaked app source

Working examples are in this repo. Copy them rather than starting from scratch:

| Pipeline | Files | Pattern |
|---|---|---|
| YouMod (YouTube) | `.github/workflows/check-youmod.yml`, `build.yml`, `config.yml` | upstream commit watcher → Theos build on macOS → cyan inject. Base IPA pinned in config |
| Spotify + Chroma | `.github/workflows/chroma-spotify.yml`, `scripts/chroma/*`, `chroma-state.json` | version API/scrape → multi-source IPA search → Playwright drives a web patcher → optional .deb inject |

`scripts/chroma/fetch_ipa.py` (IPA search + validation) and `scripts/chroma/update_repo.py` (`stamp`, `restore-watch`, feed writer) are generic apart from their constants. Lift them for new apps.

## 1. Ask first, briefly

The user wants short messages and prefers multiple-choice questions (AskUserQuestion) or an artifact over long text. Ask only what changes the build:

1. **App + tweak(s)**: upstream repos, or a web patcher URL.
2. **Base IPA source**: pinned URL in config, GitHub releases of community repos, or decrypt sites. Ask which repos they trust.
3. **Patch method**: prebuilt `.deb` from releases (ubuntu runner), compile with Theos (macOS runner, see `build.yml` for SDK/roothide fixes), or a browser patcher (Playwright).
4. **Customisation**: display name, icon, bundle ID, keep or remove extensions, restore the Watch app.
5. **Trigger**: upstream release/commit, version API, schedule interval, stable or beta channel.
6. **Where it lives**: add to this source (one feed, several apps) or a new repo. In cloud sessions Claude cannot create repos; the user makes an empty one at github.com/new, or runs a local session where `gh repo create` works.

## 2. Pipeline checklist

- **Detect**: prefer a JSON API over scraping (check the page's network requests with Playwright). Save the last-built versions in a state file, or check whether the release tag exists (YouMod style). Exit 0 with `should_build=false` when there is nothing new, so scheduled runs stay green.
- **Fetch + validate** every candidate before use: ZIP, > ~50 MB, `Payload/*.app/Info.plist` has the right bundle ID and exact `CFBundleShortVersionString`, main binary `cryptid == 0` (decrypted), and no tweak dylibs already inside. Reject HTML responses. Convert `pixeldrain.com/u/ID` to `/api/file/ID?download`. Use `GH_TOKEN` for the GitHub API. Community "unpatched" builds often still contain the tweak (EeveePrebuilt's "Unpatched" only means not patched for paid-cert signing), so check what a source really ships. If the exact version a patcher needs isn't uploaded anywhere, fall back to an older patcher release that supports an available version.
- **Patch**: web patchers may not auto-download. Inspect the page and wait for the `a[download]` link, then click it. Catch the page's own error text, and screenshot on failure (`patch_error.png` artifact). Read a patcher's kit/manifest to see what it removes (Chroma removes `Watch/`).
- **Inject**: cyan (`uv tool install --with lief "cyan @ git+https://github.com/asdfzxcvbn/pyzule-rw"`, or pipx + `pipx inject cyan lief`). Run `cyan -h` before relying on a flag. Common ones: `-f` files, `-n` name, `-b` bundle ID, `-k` icon, `-u` drop UISupportedDevices, `-w` remove Watch app, `-e` remove extensions.
- **Stamp** a unique `CFBundleVersion` (`<app version>.<run number>`) with `update_repo.py stamp`. It updates the Watch app and extensions too, because iOS refuses to install when they don't match. Without a new build number, SideStore won't show a rebuild of the same app version as an update.
- **Release**: tag per build (`gh release delete --cleanup-tag` first when re-running), with the asset name fixed so feed URLs are predictable.
- **Variants instead of forks**: build every combination in one run and give each its own feed file (`sources/<variant>.json`, each with its own `identifier`), plus a main feed taking the preferred variant that was built (`chroma-variants.json`). Optional pieces like a tweak `.deb` should skip only their variants when missing, never fail the build. Put the patcher/tweak version in the source listing's app `name` and `subtitle`; the home-screen name comes from the IPA.
- **Feed**: v2 `versions[]` entry with `version` (must equal the IPA's short version), `buildVersion`, ISO date, `downloadURL`, `size`, `sha256`, `minOSVersion` read from the IPA's `MinimumOSVersion`. Keep the last 3–5 entries. Find apps by `bundleIdentifier`, never by index, since another workflow may write the same file. Commit with `git pull --rebase` before pushing.
- **Never change a published source's top-level `identifier`**: clients key sources by it, so changing it breaks the source for existing users. Change `name`/`description` instead.
- **Private repo**: SideStore can't send auth. Use `cloudflare/worker.js` and set `DOWNLOAD_BASE_URL`.
- **Sites that block cloud servers** (Cloudflare 403 on GitHub runners, even for signed download links), such as decrypt.day: don't try to get past the block. Fetch from the user's Mac with a self-hosted runner registered to a *private* repo (never a public one, where fork PRs could run code on it), once per version, store the IPA as a private release, and read it with a fine-grained token. Template: the user's private `ipa-cache` repo (`decrypt_day.py`, `decrypt-day.yml`).
- Source URL for users is always the `raw.githubusercontent.com/.../apps.json` link.

## 3. What sideloading can and can't do (tell the user up front)

- **CarPlay**: needs Apple's CarPlay entitlement (e.g. `com.apple.developer.carplay-audio`) in the provisioning profile. Apple grants it per App ID on request. A tweak or a made-up bundle ID cannot add it, and SideStore/AltStore strip entitlements the profile lacks. Only route: a paid account applies for that App ID, then signs manually with that profile. Approval isn't guaranteed.
- **Watch app**: it can be kept or restored (`update_repo.py restore-watch BASE IPA`, the Watch variants in `chroma-variants.json`), but SideStore/AltStore can't install it at all: they suffix the app's bundle ID with the team ID (e.g. `com.spotify.client.N228KQ7JL6`) without updating the Watch app's `WKCompanionAppBundleIdentifier`, so iOS fails with InvalidCompanionAppBundleIdentifier. Never make a Watch variant the default in a SideStore feed. It needs a paid account plus a signer such as Sideloadly or Xcode, and may still fail if app groups or bundle IDs differ from the phone app. Label it experimental.
- **Free Apple ID**: 3 active sideloaded apps and 10 App IDs per 7 days. Each extension uses an App ID, so offer to remove unneeded extensions.
- **Changing the bundle ID** lets the app sit next to the App Store version, but it can break app groups, keychain sharing, push notifications and some logins.
- Public releases of decrypted IPAs carry DMCA takedown risk. Mention once; private repo + Worker is the safer option.

## 4. Before handing back

`python -m py_compile`, `node --check`, `python -m json.tool` on every JSON file, YAML load of each workflow. Exercise `fetch` validation and `update_repo.py` on fake IPAs built with `zipfile` (include a Mach-O header with an `LC_ENCRYPTION_INFO_64` load command). Don't run real patch or publish steps unless the user asks.
