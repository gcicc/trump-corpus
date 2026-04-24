"""Fetch one public-domain Trump portrait per year (2009-2026) from Wikimedia Commons.

Strategy: query Commons' MediaWiki API for the `Donald_Trump_in_<YEAR>` category
(and a few variants), keep the first image whose license is clearly public
domain (US government work, PD-self, PD-US, PD-USGov-*). Resize to 256x256
center-cropped circular avatar, save to site/assets/avatars/<year>.jpg, and
record attribution in site/data/images.json.

If no PD image is found for a year, we fall back to a cropped detail of the
adjacent year's portrait so the site still has a visible avatar per year.
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
SITE = ROOT / "site"
AVATARS = SITE / "assets" / "avatars"
IMAGES_JSON = SITE / "data" / "images.json"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "trump-corpus/0.1 (personal research; MediaWiki API via requests)"

PD_TOKENS = (
    "PD-USGov", "PD-US", "Public domain", "PD-self", "PD-author",
    "CC0", "PDM", "White House", "federal government",
)


def _api(**params) -> dict:
    params.setdefault("format", "json")
    params.setdefault("action", "query")
    r = requests.get(COMMONS_API, params=params, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def category_members(cat: str, limit: int = 30) -> list[dict]:
    data = _api(
        list="categorymembers",
        cmtitle=f"Category:{cat}",
        cmtype="file",
        cmlimit=str(limit),
    )
    return data.get("query", {}).get("categorymembers", [])


def file_info(titles: list[str]) -> dict[str, dict]:
    if not titles:
        return {}
    out = {}
    for chunk_start in range(0, len(titles), 20):
        chunk = titles[chunk_start:chunk_start + 20]
        data = _api(
            titles="|".join(chunk),
            prop="imageinfo|info",
            iiprop="url|user|extmetadata|size|mime",
            iiurlwidth="800",
        )
        for pg in data.get("query", {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            out[pg["title"]] = ii
        time.sleep(0.25)
    return out


def is_pd(imageinfo: dict) -> tuple[bool, str]:
    extm = imageinfo.get("extmetadata") or {}
    license_short = (extm.get("LicenseShortName") or {}).get("value", "")
    license_url = (extm.get("LicenseUrl") or {}).get("value", "")
    permission = (extm.get("Permission") or {}).get("value", "")
    usage = (extm.get("UsageTerms") or {}).get("value", "")
    haystack = " ".join([license_short, license_url, permission, usage]).lower()
    if any(tok.lower() in haystack for tok in PD_TOKENS):
        return True, license_short or "Public domain"
    return False, license_short or "unknown"


def pick_image_for_year(year: int) -> tuple[dict | None, str]:
    """Return (picked_imageinfo, reason). picked_imageinfo includes extra key 'title'."""
    candidates = []
    for cat in [
        f"Donald_Trump_in_{year}",
        f"Donald_Trump_{year}",
        f"Photographs_of_Donald_Trump_in_{year}",
    ]:
        try:
            members = category_members(cat, limit=40)
        except Exception:  # noqa: BLE001
            continue
        candidates.extend(members)
        if members:
            break

    if not candidates:
        return None, f"no Commons category found for {year}"

    # dedupe by title
    seen = set()
    titles: list[str] = []
    for m in candidates:
        t = m["title"]
        if t not in seen and t.lower().endswith((".jpg", ".jpeg", ".png")):
            seen.add(t)
            titles.append(t)

    infos = file_info(titles)
    for t in titles:
        info = infos.get(t, {})
        pd, lic = is_pd(info)
        if pd and info.get("url"):
            info = dict(info, title=t, license=lic)
            return info, f"selected PD image ({lic})"

    return None, "no PD image among candidates"


def download_and_crop(url: str, out_path: Path) -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return False
    try:
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:  # noqa: BLE001
        return False
    # center-crop to square, resize to 256
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = int((h - side) * 0.28)  # bias up so heads aren't cropped
    top = max(0, min(top, h - side))
    img = img.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=88, optimize=True)
    return True


def fallback_crop(src_year: int, dst_year: int) -> bool:
    src = AVATARS / f"{src_year}.jpg"
    if not src.exists():
        return False
    img = Image.open(src).convert("RGB")
    # Slight zoom to differentiate from the source year
    w, h = img.size
    z = 0.88
    new_w, new_h = int(w * z), int(h * z)
    left = (w - new_w) // 2
    top = (h - new_h) // 2
    img = img.crop((left, top, left + new_w, top + new_h)).resize((256, 256), Image.LANCZOS)
    img.save(AVATARS / f"{dst_year}.jpg", "JPEG", quality=88, optimize=True)
    return True


def main() -> int:
    AVATARS.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"avatars": {}}
    years = list(range(2009, 2027))
    picks: dict[int, dict] = {}

    for y in years:
        out = AVATARS / f"{y}.jpg"
        if out.exists():
            print(f"  {y}: already present, skipping fetch")
            continue
        info, reason = pick_image_for_year(y)
        print(f"  {y}: {reason}")
        if info is None:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        if download_and_crop(url, out):
            picks[y] = info
        time.sleep(0.5)

    # Read back any existing avatars on disk so manifest stays current
    for y in years:
        out = AVATARS / f"{y}.jpg"
        if not out.exists():
            # Try a fallback from the nearest year we did fetch
            nearest = None
            for d in range(1, 5):
                for cand in (y - d, y + d):
                    if (AVATARS / f"{cand}.jpg").exists():
                        nearest = cand
                        break
                if nearest:
                    break
            if nearest is not None and fallback_crop(nearest, y):
                manifest["avatars"][y] = {"source": "fallback", "from_year": nearest}
                print(f"  {y}: fallback crop from {nearest}")
            continue

        if y in picks:
            info = picks[y]
            extm = info.get("extmetadata") or {}
            manifest["avatars"][y] = {
                "source": "wikimedia_commons",
                "commons_title": info.get("title"),
                "original_url": info.get("url"),
                "artist": (extm.get("Artist") or {}).get("value"),
                "license": info.get("license"),
                "credit": (extm.get("Credit") or {}).get("value"),
                "description_url": info.get("descriptionurl")
                or info.get("descriptionshorturl"),
            }
        else:
            manifest["avatars"].setdefault(y, {"source": "preexisting"})

    IMAGES_JSON.parent.mkdir(parents=True, exist_ok=True)
    IMAGES_JSON.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {IMAGES_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
