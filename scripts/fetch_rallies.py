"""Scrape Wikipedia's lists of Donald Trump rallies; geocode cities; emit
site/data/locations.json for the map page.

Lists covered:
  - List of 2016 Donald Trump presidential campaign rallies  -> campaign-2016
  - List of post-election Donald Trump rallies (2017-2020)   -> potus-first-term
  - List of 2020 Donald Trump presidential campaign rallies  -> potus-first-term
  - List of 2024 Donald Trump presidential campaign rallies  -> campaign-2024

Plus a small set of fixed "home base" stops (Trump Tower, Mar-a-Lago,
Bedminster, White House) that carry era tags.

Geocoding: geopy + Nominatim, cached to data/raw/geocoding_cache.json so
re-runs are cheap. 1 req/sec rate limit respected.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CACHE = ROOT / "data" / "raw" / "geocoding_cache.json"
OUT = SITE / "data" / "locations.json"

UA = "trump-corpus/0.1 (personal research; Nominatim via geopy)"

LISTS = [
    ("https://en.wikipedia.org/wiki/List_of_rallies_for_the_2016_Donald_Trump_presidential_campaign", "campaign-2016"),
    ("https://en.wikipedia.org/wiki/List_of_Donald_Trump_rallies_(December_2016%E2%80%932022)",        "potus-first-term"),
    ("https://en.wikipedia.org/wiki/List_of_rallies_for_the_2024_Donald_Trump_presidential_campaign",  "campaign-2024"),
    ("https://en.wikipedia.org/wiki/List_of_Donald_Trump_rallies_(2025%E2%80%93present)",              "potus-second-term"),
]

HOME_BASES = [
    {"label": "Trump Tower, Manhattan",  "city": "New York, NY",       "lat": 40.7625,  "lng": -73.9737, "phase": "campaign-2016",  "type": "headquarters", "date": "2015-06-16"},
    {"label": "The White House",          "city": "Washington, DC",     "lat": 38.8977,  "lng": -77.0365, "phase": "potus-first-term", "type": "residence",     "date": "2017-01-20"},
    {"label": "Mar-a-Lago",               "city": "Palm Beach, FL",     "lat": 26.6760,  "lng": -80.0373, "phase": "post-presidency",  "type": "residence",     "date": "2021-01-20"},
    {"label": "Bedminster",               "city": "Bedminster, NJ",     "lat": 40.6800,  "lng": -74.6460, "phase": "post-presidency",  "type": "residence",     "date": "2022-06-01"},
    {"label": "The White House (2nd)",    "city": "Washington, DC",     "lat": 38.8977,  "lng": -77.0365, "phase": "potus-second-term","type": "residence",     "date": "2025-01-20"},
]


# --------- Wikipedia scraping ---------

_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}",
    re.IGNORECASE,
)

US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
STATE_CODES = set(US_STATES.values())
STATE_NAME_ALT = {n.lower(): code for n, code in US_STATES.items()}

_CITY_ST_RE = re.compile(r"\b([A-Z][a-zA-Z'.\- ]{2,40}?),\s*([A-Z]{2})\b")
_CITY_STATENAME_RE = re.compile(
    r"\b([A-Z][a-zA-Z'.\- ]{2,40}?),\s*("
    + "|".join(re.escape(n) for n in US_STATES.keys())
    + r")\b"
)


def _extract_city(cells: list[str]) -> str | None:
    joined = " | ".join(cells)
    m = _CITY_ST_RE.search(joined)
    if m:
        city, st = m.group(1).strip(), m.group(2).strip()
        if st in STATE_CODES:
            return f"{city}, {st}"
    m2 = _CITY_STATENAME_RE.search(joined)
    if m2:
        city, state_name = m2.group(1).strip(), m2.group(2).strip()
        return f"{city}, {US_STATES.get(state_name, state_name)}"
    return None


def _fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell).strip()


def _parse_date(s: str) -> str | None:
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0).replace(",", ""), "%B %d %Y").date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(m.group(0), "%B %d, %Y").date().isoformat()
        except ValueError:
            return None


def _col_index(headers: list[str], *needles: str) -> int | None:
    for i, h in enumerate(headers):
        for n in needles:
            if n in h:
                return i
    return None


def scrape_list(url: str, phase: str) -> list[dict]:
    html = _fetch(url)
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    for table in soup.select("table.wikitable"):
        # Collect header row (first tr with all th)
        header_tr = table.find("tr")
        if not header_tr:
            continue
        headers = [_clean(th.get_text(" ")).lower() for th in header_tr.find_all(["th"])]
        if not headers or not any("date" in h for h in headers):
            continue

        i_date  = _col_index(headers, "date")
        i_city  = _col_index(headers, "city")
        i_state = _col_index(headers, "state")
        i_venue = _col_index(headers, "venue")
        # Some tables use a combined "Location" column
        i_loc   = _col_index(headers, "location")

        for tr in table.find_all("tr")[1:]:
            cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
            if not cells:
                continue

            def get(ix):
                return cells[ix] if ix is not None and ix < len(cells) else ""

            date_iso = _parse_date(get(i_date)) or _parse_date(" | ".join(cells))

            city = None
            if i_city is not None and i_state is not None:
                c = get(i_city)
                s = get(i_state)
                # Normalize state — may be full name or 2-letter code
                if s:
                    s_code = s if s in STATE_CODES else US_STATES.get(s) or STATE_NAME_ALT.get(s.lower(), s)
                    if c:
                        city = f"{c}, {s_code}"
            if city is None and i_loc is not None:
                city = _extract_city([get(i_loc)])
            if city is None:
                city = _extract_city(cells)

            venue = get(i_venue) if i_venue is not None else None
            if venue:
                venue = venue[:80]

            if not city or not date_iso:
                continue
            rows.append({
                "date": date_iso,
                "city": city,
                "venue": venue,
                "phase": phase,
                "type": "rally",
                "source": url,
            })
    return rows


# --------- Geocoding ---------


def _load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def geocode_one(place: str, cache: dict) -> tuple[float, float] | None:
    key = place.strip()
    if key in cache:
        v = cache[key]
        return (v["lat"], v["lng"]) if v else None

    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": key, "format": "json", "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": UA},
        timeout=30,
    )
    time.sleep(1.0)  # politeness
    if r.status_code != 200:
        cache[key] = None
        return None
    data = r.json()
    if not data:
        # Try without country filter
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": key, "format": "json", "limit": 1},
            headers={"User-Agent": UA},
            timeout=30,
        )
        time.sleep(1.0)
        data = r.json() if r.status_code == 200 else []
    if not data:
        cache[key] = None
        return None
    lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
    cache[key] = {"lat": lat, "lng": lng, "display": data[0].get("display_name", "")}
    return (lat, lng)


def geocode_all(rows: Iterable[dict]) -> list[dict]:
    cache = _load_cache()
    out: list[dict] = []
    for r in rows:
        city = r.get("city")
        if not city:
            continue
        coords = geocode_one(city, cache)
        if coords is None:
            continue
        lat, lng = coords
        out.append(dict(r, lat=lat, lng=lng, label=r.get("venue") or city))
    _save_cache(cache)
    return out


# --------- Main ---------


def main() -> int:
    all_rows: list[dict] = []
    for url, phase in LISTS:
        try:
            rows = scrape_list(url, phase)
            print(f"  {url.rsplit('/', 1)[-1]}  -> {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:  # noqa: BLE001
            print(f"  failed {url}: {e}", file=sys.stderr)

    # Deduplicate by (date, city)
    seen = set()
    dedup = []
    for r in all_rows:
        key = (r.get("date"), r.get("city"))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    print(f"\n  geocoding {len(dedup)} rally rows (cached where possible)...")
    stops = geocode_all(dedup)

    # Prepend home bases so they render as anchors
    for hb in HOME_BASES:
        stops.insert(0, {**hb, "label": hb["label"], "source": "fixed"})

    # Sort by date (None dates sink)
    stops.sort(key=lambda s: (s.get("date") or "9999"))

    payload = {
        "schema_version": 1,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "stops": stops,
        "notes": "Wikipedia-sourced rally lists + fixed home-base coordinates. "
                 "Geocoded via OSM Nominatim with 1 req/sec rate limit.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT} with {len(stops)} stops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
