# YouMod Pre-release

Automated YouMod IPA builds from the **pre-release** branch of [YouMod](https://github.com/Tonwalter888/YouMod), delivered to AltStore, SideStore, or Feather. Rebuilt automatically whenever a new pre-release commit lands. Pre-release builds may be unstable.

---

## How to Add This Repo

1. Open **AltStore / SideStore / Feather** on your device
2. Navigate to **Sources** or **Repos**
3. Tap **+** and paste the URL below:

```
https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/apps.json
```

4. **YouMod Pre-release** will appear under Browse — tap **Get** to install
5. When asked about app extensions, keep them (on a free Apple account each one uses an App ID)

> **Note:** You must have a signing method set up (AltStore, SideStore, Feather, Signulous, etc.) to install the IPA.

---

## Currently Supported

| | |
|---|---|
| **YouTube version** | 21.45.4 |
| **YouMod version** | 2.1.0-5fd9e6e |
| **Last built** | November 27, 2026 |
| **Min iOS** | 14.0 |

---

## Included Tweaks

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

---

## How Automatic Builds Work

This repo builds and publishes a new YouMod IPA automatically.

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

Older builds stay on the [Releases](https://github.com/wyatt-poole/altstore-repository/releases) page if you need to roll back.

A failed build is retried by the next scheduled check, so the repo does not get stuck on a broken version.

---

## 🙏 Credits

| Developer | Tweaks |
|---|---|
| [Tonwalter888](https://github.com/Tonwalter888) | YouMod, YTUHD |
| [PoomSmart](https://github.com/PoomSmart) | Return YouTube Dislikes, YTVideoOverlay |
| [therealFoxster](https://github.com/therealFoxster) | DontEatMyContent |
| [asdfzxcvbn](https://github.com/asdfzxcvbn) | cyan (IPA injection tool) |
| [BillyCurtis](https://github.com/BillyCurtis) | Open in YouTube Safari extension |
| [MountainofPenguin](https://github.com/MountainofPenguin/Altstore-Repository) | Original repo this is forked from |
