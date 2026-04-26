"""Fetch a curated set of public-domain hero images from Wikimedia Commons.

These are the wide banner images used at the top of landing pages
(home, themes index, timeline index, map, analytics, about).

Output:
  site/assets/heroes/<slug>.jpg     1600x500 cover-cropped
  site/data/heroes.json             attribution metadata
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HEROES = ROOT / "site" / "assets" / "heroes"
META = ROOT / "site" / "data" / "heroes.json"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "trump-corpus/0.1 (personal research)"

# Each entry: slug -> Wikimedia file title (PD-USGov or PD-self verified)
# These titles are public-domain official US Government photographs.
HEROES_LIST = {
    "white_house": "File:The White House North Portico in Washington, D.C.jpg",
    "oval_office": "File:Donald Trump in the Oval Office, June 2017.jpg",
    "oval_panorama": "File:Trump Oval Office panorama.jpg",
    "air_force_one": "File:Trump Force One at Stewart.jpg",
    "capitol": "File:US Capitol east side.JPG",
    "rally_crowd": "File:Trump rally crowd (33772798884).jpg",
    "signing_ceremony": "File:President Trump Signs an Executive Order (50119222336).jpg",
    "official_portrait": "File:Donald Trump official portrait.jpg",
}

TARGET_W, TARGET_H = 1600, 500  # ~3.2:1 cinematic banner


def _api(**params) -> dict:
    params.setdefault("format", "json")
    params.setdefault("action", "query")
    r = requests.get(COMMONS_API, params=params,
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_info(title: str) -> dict | None:
    data = _api(
        titles=title,
        prop="imageinfo|info",
        iiprop="url|user|extmetadata|size|mime",
        iiurlwidth="1800",
    )
    pages = data.get("query", {}).get("pages", {})
    for pg in pages.values():
        ii = (pg.get("imageinfo") or [{}])[0]
        if ii.get("url"):
            ii["title"] = title
            return ii
    return None


def banner_crop(img: Image.Image) -> Image.Image:
    """Crop to TARGET_W:TARGET_H aspect, scale up if needed."""
    w, h = img.size
    target_aspect = TARGET_W / TARGET_H
    cur_aspect = w / h
    if cur_aspect > target_aspect:
        # too wide: crop sides
        new_w = int(h * target_aspect)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        # too tall: crop top/bottom, biased toward upper third (head/sky)
        new_h = int(w / target_aspect)
        top = max(0, (h - new_h) // 3)  # bias up
        img = img.crop((0, top, w, top + new_h))
    return img.resize((TARGET_W, TARGET_H), Image.LANCZOS)


def main() -> int:
    HEROES.mkdir(parents=True, exist_ok=True)
    META.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict = {}
    for slug, title in HEROES_LIST.items():
        out = HEROES / f"{slug}.jpg"
        if out.exists() and out.stat().st_size > 50_000:
            print(f"  {slug}: already present ({out.stat().st_size // 1024} KB), reusing")
            # Still capture metadata
            info = fetch_info(title)
            if info:
                extm = info.get("extmetadata") or {}
                manifest[slug] = {
                    "title": title,
                    "artist": (extm.get("Artist") or {}).get("value"),
                    "license": (extm.get("LicenseShortName") or {}).get("value"),
                    "credit": (extm.get("Credit") or {}).get("value"),
                    "description_url": info.get("descriptionurl"),
                    "original_url": info.get("url"),
                }
            continue

        print(f"  {slug}: fetching {title}…")
        info = fetch_info(title)
        if not info:
            print(f"    NOT FOUND")
            continue
        url = info.get("thumburl") or info.get("url")
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"    download failed: {e}")
            continue

        cropped = banner_crop(img)
        cropped.save(out, "JPEG", quality=86, optimize=True, progressive=True)
        print(f"    -> {out.name}  {out.stat().st_size // 1024} KB")

        extm = info.get("extmetadata") or {}
        manifest[slug] = {
            "title": title,
            "artist": (extm.get("Artist") or {}).get("value"),
            "license": (extm.get("LicenseShortName") or {}).get("value"),
            "credit": (extm.get("Credit") or {}).get("value"),
            "description_url": info.get("descriptionurl"),
            "original_url": info.get("url"),
        }
        time.sleep(3.0)  # Wikimedia rate-limits aggressively (HTTP 429)

    META.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {META}  heroes={len(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
