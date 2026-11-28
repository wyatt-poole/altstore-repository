#!/usr/bin/env python3
"""Mirror third-party AltStore/SideStore sources that SideStore refuses to load, with the
missing required fields filled in. Each mirror lives at mirrors/<name>.json.

  python3 scripts/mirror_sources.py OWNER/REPO

OWNER/REPO is this repository, used to point each mirror's sourceURL at itself (otherwise
SideStore follows sourceURL back to the broken original on refresh).
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRRORS = {
    "ryp0": "https://raw.githubusercontent.com/Sami-Wali/ryP0-repository/main/repo.json",
}


def fix(data: dict, self_url: str) -> int:
    fixed = 0
    for app in data.get("apps", []):
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
