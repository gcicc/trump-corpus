"""Trump speeches and public statements from the UCSB American Presidency Project.

Canonical academic archive. Each document has a clean URL like
`/documents/<slug>` and a structured detail page with date, title, and
full transcript text.

We crawl the Trump person page's paginated document index, then hydrate each
document. Cached under data/raw/ucsb/.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..db import upsert_source
from ..util import USER_AGENT, now_iso, to_iso_utc

BASE = "https://www.presidency.ucsb.edu"
# Trump's "documents archive" paginated listing. Person ID 200301 = Donald Trump.
LIST_URL = (
    f"{BASE}/advanced-search"
    "?field-keywords=&field-keywords2=&field-keywords3="
    "&from%5Bdate%5D=&to%5Bdate%5D=&person2=200301&items_per_page=100"
)
SOURCE_ID = "ucsb_american_presidency"


def _fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:  # noqa: BLE001
        return None


def _collect_document_links(max_pages: int, cache_dir: Path) -> list[tuple[str, str]]:
    """Walk paginated search pages; return list of (title, absolute_url)."""
    links: list[tuple[str, str]] = []
    for page in range(max_pages):
        url = f"{LIST_URL}&page={page}" if page else LIST_URL
        html = _fetch(url)
        if html is None:
            break
        (cache_dir / f"index_{page:03d}.html").write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        anchors = soup.select("td.views-field-title a, td a[href*='/documents/']")
        new = 0
        for a in anchors:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href.startswith("/documents/") or not title:
                continue
            abs_url = f"{BASE}{href}"
            if (title, abs_url) not in links:
                links.append((title, abs_url))
                new += 1
        if new == 0:
            break
        time.sleep(0.5)
    return links


_DATE_META_SELECTORS = [
    "meta[name='dcterms.date']",
    "meta[property='article:published_time']",
    "meta[name='citation_date']",
]


def _parse_document(html: str) -> tuple[str | None, str | None, str | None]:
    """Return (title, iso_date, body_text). None if unparseable."""
    soup = BeautifulSoup(html, "lxml")

    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

    date = None
    for sel in _DATE_META_SELECTORS:
        m = soup.select_one(sel)
        if m and m.get("content"):
            date = m["content"]
            break
    if not date:
        date_el = soup.select_one(".field-docs-start-date-time, .date-display-single")
        if date_el:
            date = date_el.get_text(strip=True)

    body_el = (
        soup.select_one(".field-docs-content")
        or soup.select_one("div.field-name-body")
        or soup.select_one("article .content")
    )
    if body_el is None:
        return title, to_iso_utc(date) if date else None, None
    body = body_el.get_text("\n", strip=True)
    return title, to_iso_utc(date) if date else None, body


_EVENT_TYPE_HINTS = [
    (re.compile(r"inaugural address", re.I), "presidential_address"),
    (re.compile(r"state of the union", re.I), "presidential_address"),
    (re.compile(r"address to the joint session", re.I), "presidential_address"),
    (re.compile(r"executive order", re.I), "executive_order"),
    (re.compile(r"proclamation", re.I), "proclamation"),
    (re.compile(r"press briefing|press conference", re.I), "press_briefing"),
    (re.compile(r"\brally\b|campaign rally", re.I), "rally"),
    (re.compile(r"remarks at|remarks on|remarks to|remarks in|remarks during", re.I), "remarks"),
    (re.compile(r"interview", re.I), "interview"),
    (re.compile(r"statement on|statement by|statement regarding", re.I), "statement"),
    (re.compile(r"debate", re.I), "debate"),
]


def _classify(title: str) -> str:
    for rx, label in _EVENT_TYPE_HINTS:
        if rx.search(title):
            return label
    return "other"


def ingest(conn: sqlite3.Connection, raw_dir: Path, *, max_pages: int = 30) -> int:
    cache_dir = raw_dir / "ucsb"
    cache_dir.mkdir(parents=True, exist_ok=True)

    links = _collect_document_links(max_pages, cache_dir)
    ingested_at = now_iso()
    rows = []

    for i, (title, url) in enumerate(links):
        slug = url.rsplit("/", 1)[-1]
        cache = cache_dir / f"doc_{slug}.html"
        if cache.exists():
            html = cache.read_text(encoding="utf-8", errors="replace")
        else:
            html = _fetch(url)
            if html is None:
                continue
            cache.write_text(html, encoding="utf-8")
            time.sleep(0.5)

        t, d, body = _parse_document(html)
        if not body or len(body) < 100:
            continue

        sid = "ucsb_" + hashlib.sha1(url.encode()).hexdigest()[:16]
        rows.append(
            (
                sid,
                d,
                _classify(t or title),
                t or title,
                None,
                body,
                SOURCE_ID,
                url,
                ingested_at,
            )
        )

        if (i + 1) % 50 == 0:
            print(f"  [ucsb] processed {i + 1}/{len(links)}")

    conn.executemany(
        """
        INSERT INTO speeches(id, event_date, event_type, title, location, text,
                             source, source_url, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text=excluded.text,
            title=excluded.title,
            event_date=excluded.event_date,
            event_type=excluded.event_type,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    conn.commit()

    upsert_source(
        conn,
        source_id=SOURCE_ID,
        name="UCSB American Presidency Project — Trump documents",
        url=LIST_URL,
        last_fetched=ingested_at,
        record_count=len(rows),
        sha256=None,
        notes=f"Indexed {len(links)} doc links across {max_pages} max pages; ingested {len(rows)}.",
    )
    return len(rows)
