# Wyatt's Tweaked Apps

Automatically rebuilt, tweaked IPAs for AltStore, SideStore and Feather:

- **YouMod Pre-release**: YouTube with [YouMod](https://github.com/Tonwalter888/YouMod) built from its pre-release branch, plus a few companion tweaks
- **Spotify + Chroma**: Spotify patched with [Chroma](https://chroma.pw). Variants with [EeveeSpotify](https://github.com/SideloadLabs/EeveeSpotifyReincarnated) have their own source URLs ([below](#other-spotify-variants))

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
| **Last built** | November 28, 2026 |
| **Min iOS** | 14.0 |

### Spotify + Chroma

The source shows the Chroma version in the app's name (e.g. *Spotify + Chroma (Chroma 1.2.0-beta.3)*). The home-screen name stays *Spotify*.

| | |
|---|---|
| **Spotify version** | 9.1.98 |
| **Chroma version** | 1.2.0-beta.3 |
| **Spotify last built** | November 28, 2026 |

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

### Other Spotify variants

The main source above has plain **Spotify + Chroma**. Each variant also has its own source. Add only the one you want, since they share Spotify's bundle ID and replace each other:

| Variant | Source URL |
|---|---|
| Chroma + Watch | `https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/sources/spotify-chroma-watch.json` |
| Chroma | `https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/sources/spotify-chroma.json` |
| Chroma + Eevee + Watch | `https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/sources/spotify-chroma-eevee-watch.json` |
| Chroma + Eevee | `https://raw.githubusercontent.com/wyatt-poole/altstore-repository/main/sources/spotify-chroma-eevee.json` |

- **Eevee:** EeveeSpotify mainly unlocks Premium features on free accounts. If you pay for Premium, skip it: it overrides the account checks Spotify relies on and can break things like downloads.
- **Watch** (experimental): Chroma removes the Watch app, and these variants put it back. SideStore/AltStore rename the app for your Apple ID (`com.spotify.client.<team ID>`) but not the Watch app's link to it, which iOS rejects (`InvalidCompanionAppBundleIdentifier`). So the Watch variants are built with that link already pointing at `com.spotify.client.<SIDESTORE_TEAM_ID>`. Set the variable to the suffix your SideStore install shows (it's in that error message). Signers that keep the original bundle ID, such as Sideloadly, need `SIDESTORE_TEAM_ID` set to empty instead. Experimental: needs a paid Apple ID for the extra app IDs.
- **CarPlay** won't appear in sideloaded Spotify. It needs Apple's CarPlay audio entitlement in the signing profile, which Apple grants only on request. A tweak or a different bundle ID can't add it.

Variants are defined in [`chroma-variants.json`](chroma-variants.json).

### How the Build Works

```
Scheduled workflow checks chroma.pw for the newest Chroma kit (every 6 hours, betas included)
        ↓
New Chroma or Spotify version? (chroma-state.json)
        ↓
Download the matching decrypted Spotify IPA
  private IPA cache (decrypt.day, via your Mac) → PwEevee → EeveePrebuilt → EeveeIPA
  (only a decrypted, untweaked com.spotify.client of the exact version is accepted)
        ↓
Run chroma.pw's in-browser patcher in headless Chromium, keeping Spotify's own icon
        ↓
Build the variants: Watch app restored, EeveeSpotify injected with cyan
        ↓
One GitHub release with every variant; apps.json and sources/*.json updated with a unique build number
```

**When the newest Chroma's Spotify IPA isn't anywhere yet:**
1. The build asks the private [`ipa-cache`](https://github.com/wyatt-poole/ipa-cache) repo to fetch it from decrypt.day. That runs once, on your Mac, then re-runs this build. decrypt.day blocks cloud servers, so the download can't happen here. Setup is in that repo's README. You can also upload the IPA there by hand.
2. Meanwhile it builds the newest older Chroma whose Spotify is available. The listing says so and names the version it's waiting for.

EeveePrebuilt and EeveeIPA only publish IPAs with EeveeSpotify already inside, so their builds are never used as the base.

Run **Build Spotify + Chroma & Update Repo** from the Actions tab for a manual build. `force` rebuilds the current version, and `base_ipa_url` uses a direct IPA link of your choice. decrypt.day's own links don't work there, because they're blocked from cloud servers and expire after 5 minutes.

### Options

Repository variables (Settings → Secrets and variables → Actions → Variables). None are required.

| Variable | Default | |
|---|---|---|
| `CHROMA_CHANNEL` | `beta` | `beta` builds the newest kit; `stable` builds the one chroma.pw marks *recommended* |
| `EEVEE_REPOS` | `SideloadLabs/EeveeSpotifyReincarnated NotDarkn/EeveePrebuilt` | repos tried in order for the newest rootless EeveeSpotify `.deb`. If none has one, only the Eevee variants are skipped |
| `IPA_CACHE_REPO` | `wyatt-poole/ipa-cache` | private repo holding decrypt.day IPAs |
| `SIDESTORE_TEAM_ID` | `N228KQ7JL6` | suffix SideStore adds to bundle IDs on your Apple ID. The Watch variants point the Watch app at `com.spotify.client.<this>`. Empty for other signers |
| `BASE_IPA_URL` | | always use this decrypted IPA instead of searching |
| `DOWNLOAD_BASE_URL` | | Worker URL if this repo is ever made private (see [`cloudflare/worker.js`](cloudflare/worker.js)) |

Secret (Settings → Secrets and variables → Actions → Secrets): `IPA_CACHE_TOKEN`, the token described in the ipa-cache README. Without it, the build skips the cache and the decrypt.day requests.

---

## 🙏 Credits

| Developer | Work |
|---|---|
| [Tonwalter888](https://github.com/Tonwalter888) | YouMod, YTUHD |
| [PoomSmart](https://github.com/PoomSmart) | Return YouTube Dislikes, YTVideoOverlay |
| [therealFoxster](https://github.com/therealFoxster) | DontEatMyContent |
| [BillyCurtis](https://github.com/BillyCurtis) | Open in YouTube Safari extension |
| [Chroma](https://chroma.pw) | Chroma for Spotify |
| [whoeevee](https://github.com/whoeevee), [SideloadLabs](https://github.com/SideloadLabs/EeveeSpotifyReincarnated) | EeveeSpotify |
| [asdfzxcvbn](https://github.com/asdfzxcvbn) | cyan (IPA injection tool) |
| [MountainofPenguin](https://github.com/MountainofPenguin/Altstore-Repository) | Original repo this is forked from |
