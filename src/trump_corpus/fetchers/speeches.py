"""Speeches / rally transcripts / formal addresses.

Sources (best-effort; separate table from social posts):
- Miller Center presidential speeches (UVA) — formal addresses, 2017-2021 + 2025-.
- ryanmcdermott/trump-speeches (GitHub) — small early-campaign archive.

Factba.se (Roll Call) has the richest transcript set but requires scraping their
search interface and is rate-limited. We defer it to a dedicated pass — see
ACTION-ITEMS.md.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup

from ..db import upsert_source
from ..util import download, now_iso, sha256_file, to_iso_utc

# ---------- ryanmcdermott/trump-speeches ----------

RMCD_URL = (
    "https://raw.githubusercontent.com/ryanmcdermott/trump-speeches/master/speeches.txt"
)
RMCD_SOURCE_ID = "ryanmcdermott_speeches"


def _ingest_ryanmcdermott(conn: sqlite3.Connection, raw_dir: Path) -> int:
    dest = raw_dir / "ryanmcdermott_speeches.txt"
    download(RMCD_URL, dest)
    sha = sha256_file(dest)

    text = dest.read_text(encoding="utf-8", errors="replace")
    # File delimits speeches with "SPEECH <n>" headers.
    chunks = []
    current_title = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip().upper().startswith("SPEECH "):
            if current_title and buf:
                chunks.append((current_title, "\n".join(buf).strip()))
            current_title = line.strip()
            buf = []
        else:
            buf.append(line)
    if current_title and buf:
        chunks.append((current_title, "\n".join(buf).strip()))

    rows = []
    ingested_at = now_iso()
    for title, body in chunks:
        if not body:
            continue
        sid = "rmcd_" + hashlib.sha1(title.encode() + body[:200].encode()).hexdigest()[:16]
        rows.append(
            (
                sid,
                None,                       # event_date unknown in this file
                "campaign_speech",
                title,
                None,
                body,
                RMCD_SOURCE_ID,
                "https://github.com/ryanmcdermott/trump-speeches",
                ingested_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO speeches(id, event_date, event_type, title, location, text,
                             source, source_url, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text=excluded.text,
            title=excluded.title,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    conn.commit()

    upsert_source(
        conn,
        source_id=RMCD_SOURCE_ID,
        name="ryanmcdermott/trump-speeches",
        url="https://github.com/ryanmcdermott/trump-speeches",
        last_fetched=ingested_at,
        record_count=len(rows),
        sha256=sha,
        notes="Early-campaign speech snippets. No dates attached.",
    )
    return len(rows)


# ---------- Miller Center ----------

MILLER_INDEX = "https://millercenter.org/the-presidency/presidential-speeches?field_president_target_id%5B116730%5D=116730"
MILLER_SOURCE_ID = "miller_center"


def _ingest_miller_center(conn: sqlite3.Connection, raw_dir: Path) -> int:
    """Scrape Miller Center's Trump presidential-speeches index, then each transcript.

    Polite: single-threaded, short timeouts, UA identifies us. If the index page
    structure changes this will degrade cleanly (returns 0, source row records 0).
    """
    import requests

    from ..util import USER_AGENT

    headers = {"User-Agent": USER_AGENT}
    try:
        index_html = requests.get(MILLER_INDEX, headers=headers, timeout=60).text
    except Exception as e:  # noqa: BLE001
        upsert_source(
            conn,
            source_id=MILLER_SOURCE_ID,
            name="Miller Center (UVA) — Trump speeches",
            url=MILLER_INDEX,
            last_fetched=now_iso(),
            record_count=0,
            sha256=None,
            notes=f"Fetch failed: {e!r}",
        )
        return 0

    (raw_dir / "miller_center_index.html").write_text(index_html, encoding="utf-8")
    soup = BeautifulSoup(index_html, "lxml")

    speech_links: list[tuple[str, str, str | None]] = []  # (title, url, date)
    for a in soup.select("a[href*='/the-presidency/presidential-speeches/']"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or href.endswith("presidential-speeches"):
            continue
        full = href if href.startswith("http") else f"https://millercenter.org{href}"
        # Look for a nearby date
        date_el = a.find_parent().find(class_="date") if a.find_parent() else None
        date = date_el.get_text(strip=True) if date_el else None
        speech_links.append((title, full, date))

    # Dedupe by URL
    seen = set()
    unique: list[tuple[str, str, str | None]] = []
    for t, u, d in speech_links:
        if u in seen:
            continue
        seen.add(u)
        unique.append((t, u, d))

    rows = []
    ingested_at = now_iso()
    for title, url, date in unique:
        try:
            page_html = requests.get(url, headers=headers, timeout=60).text
        except Exception:  # noqa: BLE001
            continue
        page = BeautifulSoup(page_html, "lxml")
        # Miller Center transcripts usually sit in div.transcript or article body
        body_el = page.select_one("div.transcript") or page.select_one("article")
        if body_el is None:
            continue
        text = body_el.get_text("\n", strip=True)
        if len(text) < 200:
            continue  # filter out stubs
        sid = "mc_" + hashlib.sha1(url.encode()).hexdigest()[:16]
        rows.append(
            (
                sid,
                to_iso_utc(date) if date else None,
                "presidential_address",
                title,
                None,
                text,
                MILLER_SOURCE_ID,
                url,
                ingested_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO speeches(id, event_date, event_type, title, location, text,
                             source, source_url, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text=excluded.text,
            title=excluded.title,
            event_date=excluded.event_date,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    conn.commit()

    upsert_source(
        conn,
        source_id=MILLER_SOURCE_ID,
        name="Miller Center (UVA) — Trump speeches",
        url=MILLER_INDEX,
        last_fetched=ingested_at,
        record_count=len(rows),
        sha256=None,
        notes="Formal presidential addresses. Scraped from index + transcript pages.",
    )
    return len(rows)


def ingest(conn: sqlite3.Connection, raw_dir: Path) -> int:
    total = 0
    total += _ingest_ryanmcdermott(conn, raw_dir)
    total += _ingest_miller_center(conn, raw_dir)
    return total
