"""Post-reinstatement @realDonaldTrump tweets via a public nitter mirror.

The account was reinstated in Nov 2022 but is mostly dormant — a few dozen posts
since. We scrape a nitter mirror (no auth, no API key) and normalize into the
posts table.

Nitter mirrors come and go. This fetcher tries a list in order and logs which
succeeded. Failures are recorded in `sources` rather than raising.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..db import upsert_source
from ..util import USER_AGENT, dumps_compact, now_iso, to_iso_utc

HANDLE = "realdonaldtrump"
PLATFORM = "twitter"
ACCOUNT = "realDonaldTrump"
SOURCE_ID = "nitter_realdonaldtrump_post2022"

MIRRORS = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
    "https://nitter.1d4.us",
    "https://nitter.catsarch.com",
]

_STATUS_RE = re.compile(r"/status/(\d+)")


def _try_mirror(base: str) -> str | None:
    try:
        r = requests.get(
            f"{base}/{HANDLE}",
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            allow_redirects=True,
        )
        if r.status_code == 200 and "Tweet" in r.text:
            return base
    except Exception:  # noqa: BLE001
        return None
    return None


def _find_working_mirror() -> str | None:
    for m in MIRRORS:
        ok = _try_mirror(m)
        if ok:
            return ok
    return None


def _parse_timeline(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for item in soup.select(".timeline-item"):
        a = item.select_one("a.tweet-link")
        if not a:
            continue
        href = a.get("href", "")
        m = _STATUS_RE.search(href)
        if not m:
            continue
        tid = m.group(1)

        content_el = item.select_one(".tweet-content")
        text = content_el.get_text(" ", strip=True) if content_el else ""

        date_el = item.select_one(".tweet-date a")
        date = date_el.get("title") if date_el else None

        stats_el = item.select_one(".tweet-stats")
        metrics = {}
        if stats_el:
            for stat in stats_el.select(".tweet-stat"):
                txt = stat.get_text(" ", strip=True)
                if txt:
                    metrics[stat.get("class", ["stat"])[0]] = txt

        out.append(
            {
                "id": tid,
                "text": text,
                "date": date,
                "href": href,
                "metrics": metrics,
                "is_repost": 1 if item.select_one(".retweet-header") else 0,
            }
        )
    return out


def ingest(conn: sqlite3.Connection, raw_dir: Path, *, max_pages: int = 20) -> int:
    mirror = _find_working_mirror()
    if mirror is None:
        upsert_source(
            conn,
            source_id=SOURCE_ID,
            name="nitter -> @realDonaldTrump post-2022",
            url="|".join(MIRRORS),
            last_fetched=now_iso(),
            record_count=0,
            sha256=None,
            notes="No working nitter mirror found at scrape time.",
        )
        return 0

    cache_dir = raw_dir / "nitter_realdonaldtrump"
    cache_dir.mkdir(parents=True, exist_ok=True)

    all_tweets: list[dict] = []
    cursor = None
    page = 0
    while page < max_pages:
        url = f"{mirror}/{HANDLE}"
        if cursor:
            url = f"{url}?cursor={cursor}"
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        except Exception:  # noqa: BLE001
            break
        if r.status_code != 200:
            break

        (cache_dir / f"page_{page:03d}.html").write_text(r.text, encoding="utf-8")
        tweets = _parse_timeline(r.text)
        if not tweets:
            break
        all_tweets.extend(tweets)

        # Find "Load more" cursor
        soup = BeautifulSoup(r.text, "lxml")
        next_a = soup.select_one(".show-more a")
        if not next_a or "cursor=" not in next_a.get("href", ""):
            break
        cursor = next_a.get("href").split("cursor=", 1)[1]
        page += 1
        time.sleep(1.0)

    ingested_at = now_iso()
    # Only keep post-Jan-2021 entries (the 2009-2021 archive already covers older)
    rows = []
    for t in all_tweets:
        iso_ts = to_iso_utc(t.get("date")) if t.get("date") else None
        if iso_ts is None or iso_ts < "2021-01-09":
            continue
        rows.append(
            (
                f"tw_{t['id']}",
                PLATFORM,
                ACCOUNT,
                iso_ts,
                t["text"],
                t["is_repost"],
                1 if t["text"].startswith("@") else 0,
                None,
                None,
                f"https://twitter.com{t['href']}",
                dumps_compact(t["metrics"]) if t["metrics"] else None,
                dumps_compact(t),
                ingested_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO posts(id, platform, account, timestamp_utc, text,
                          is_repost, is_reply, reply_to, media_urls_json,
                          source_url, metrics_json, raw_json, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text=excluded.text,
            is_repost=excluded.is_repost,
            source_url=excluded.source_url,
            metrics_json=excluded.metrics_json,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    conn.commit()

    upsert_source(
        conn,
        source_id=SOURCE_ID,
        name="nitter -> @realDonaldTrump post-2022",
        url=mirror,
        last_fetched=ingested_at,
        record_count=len(rows),
        sha256=None,
        notes=f"Scraped {page + 1} pages; kept {len(rows)} rows >= 2021-01-09.",
    )
    return len(rows)
