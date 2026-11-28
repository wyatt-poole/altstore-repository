# Wyatt's Tweaked Apps

Automatically rebuilt, tweaked IPAs for AltStore, SideStore and Feather:

- **YouMod Pre-release**: YouTube with [YouMod](https://github.com/Tonwalter888/YouMod) built from its pre-release branch, plus a few companion tweaks
- **Spotify + Chroma**: Spotify patched with [Chroma](https://chroma.pw), optionally with [EeveeSpotify](https://github.com/whoeevee/EeveeSpotifyReincarnated)

Each app has its own GitHub Actions pipeline. Both publish to the same source.

---

## How to Add This Repo

1. Open **AltStore / SideStore / Feather** on your device
2. Navigate to **Sources** or **Repos**
3. Tap **+** and paste the URL below (use this exact `raw.githubusercontent.com` link — the normal GitHub repo page won't work and gives a "not valid JSON" error):

```
https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/apps.json
```

4. Both apps appear under Browse. Tap **Get** to install
5. When asked about app extensions, keep them (on a free Apple account each one uses an App ID)

> **Note:** You must have a signing method set up (AltStore, SideStore, Feather, Signulous, etc.) to install the IPA.

---

## Currently Supported

### YouMod Pre-release

| | |
|---|---|
| **YouTube version** | 21.45.4 |
| **YouMod version** | 2.1.0-5fd9e6e |
| **Last built** | November 27, 2026 |
| **Min iOS** | 14.0 |

### Spotify + Chroma

| | |
|---|---|
| **Spotify version** | not built yet |
| **Chroma version** | not built yet |
| **Spotify last built** | not built yet |

---

## YouMod Pre-release

### Included Tweaks

Only these tweaks are included — nothing else. YTVideoOverlay is a hard runtime
dependency of YTUHD (its reload button registers through YTVideoOverlay), so it rides along.

| Tweak | Description |
|---|---|
| [YouMod](https://github.com/Tonwalter888/YouMod) | The core tweak. Ad removal, background playback, UI customisation, and more — without a paywall. |
| [YTUHD](https://github.com/Tonwalter888/YTUHD) | Unlocks 1440p and 2160p resolutions in the iOS YouTube app. |
| [Return YouTube Dislikes](https://github.com/PoomSmart/Return-YouTube-Dislikes) | Brings back the dislike count on YouTube videos. |
| [DontEatMyContent](https://github.com/therealFoxster/DontEatMyContent) | Prevents the player from hiding behind the notch or Dynamic Island. |
| [YTVideoOverlay](https://github.com/PoomSmart/YTVideoOverlay) | Not a separate feature — YTUHD is built as a YTVideoOverlay plugin and crashes without it, so it ships alongside. |
| [Open in YouTube](https://github.com/BillyCurtis/OpenYouTubeSafariExtension) | Safari extension that opens YouTube links in the app. Enable it in Settings → Apps → Safari → Extensions → Open in YouTube, and set it to **Allow**. |

YouTube's own app extensions (share sheet, widgets, rich notifications, Siri) are kept.

### How the Build Works

```
Scheduled workflow checks YouMod's pre-release branch (every 2 hours)
        ↓
No release yet for <version>-<commit>? Start a build
        ↓
GitHub Actions compiles the tweaks from source
        ↓
cyan injects them (plus the Open in YouTube extension) into the decrypted YouTube IPA
        ↓
A GitHub release and apps.json are updated with a unique build number
```

The YouTube version and its decrypted IPA URL are pinned in [`config.yml`](config.yml) — editing it and pushing to `main` triggers a new build. You can also run **Build YouMod IPA & Update Repo** from the Actions tab.

A failed build is retried by the next scheduled check, so the repo does not get stuck on a broken version.

---

## Spotify + Chroma

### How the Build Works

```
Scheduled workflow checks chroma.pw for a new Chroma kit (every 6 hours)
        ↓
New Chroma or Spotify version? (chroma-state.json)
        ↓
Download the matching decrypted Spotify IPA
  PwEevee → EeveePrebuilt → EeveeIPA → decrypt.day
  (only a decrypted, untweaked com.spotify.client of the exact version is accepted)
        ↓
Run chroma.pw's in-browser patcher in headless Chromium, keeping Spotify's own icon
        ↓
Optional: put the Watch app back, inject the latest EeveeSpotify .deb with cyan
        ↓
A GitHub release and apps.json are updated with a unique build number
```

If nobody has uploaded a decrypted IPA for the Spotify version the newest Chroma needs, it builds the newest older Chroma kit whose Spotify version is available (for example Chroma 1.0.1 for Spotify 9.1.90), and switches to the newest kit once that IPA appears. EeveePrebuilt and EeveeIPA only publish IPAs with EeveeSpotify already inside, so in practice PwEevee is the source of clean IPAs.

Run **Build Spotify + Chroma & Update Repo** from the Actions tab for a manual build. `force` rebuilds the current version, and `base_ipa_url` uses a decrypted IPA link of your choice.

### Options

Repository variables (Settings → Secrets and variables → Actions → Variables). None are required.

| Variable | Default | |
|---|---|---|
| `INJECT_EEVEE` | `true` | `false` ships Chroma only |
| `EEVEE_REPO` | `whoeevee/EeveeSpotifyReincarnated` | where the latest `*iphoneos-arm64.deb` comes from |
| `CHROMA_CHANNEL` | `stable` | `beta` builds the newest Chroma pre-release |
| `RESTORE_WATCH` | `false` | `true` copies the Watch app back in (Chroma removes it). Experimental: needs a paid Apple ID and a signer that handles Watch apps, such as Sideloadly. SideStore/AltStore won't install it to the watch |
| `BASE_IPA_URL` | | always use this decrypted IPA instead of searching |
| `DOWNLOAD_BASE_URL` | | Worker URL if this repo is ever made private (see [`cloudflare/worker.js`](cloudflare/worker.js)) |

**CarPlay** won't appear in sideloaded Spotify. It needs Apple's CarPlay audio entitlement in the signing profile, and Apple grants that only on request. A tweak or a different bundle ID can't add it.

---

## 🙏 Credits

| Developer | Work |
|---|---|
| [Tonwalter888](https://github.com/Tonwalter888) | YouMod, YTUHD |
| [PoomSmart](https://github.com/PoomSmart) | Return YouTube Dislikes, YTVideoOverlay |
| [therealFoxster](https://github.com/therealFoxster) | DontEatMyContent |
| [BillyCurtis](https://github.com/BillyCurtis) | Open in YouTube Safari extension |
| [Chroma](https://chroma.pw) | Chroma for Spotify |
| [whoeevee](https://github.com/whoeevee) | EeveeSpotify |
| [asdfzxcvbn](https://github.com/asdfzxcvbn) | cyan (IPA injection tool) |
| [MountainofPenguin](https://github.com/MountainofPenguin/Altstore-Repository) | Original repo this is forked from |
