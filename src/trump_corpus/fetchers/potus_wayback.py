"""@POTUS45 / @WhiteHouse45 tweets via the Internet Archive Wayback CDX.

Strategy:
1. Query the CDX API for all captured URLs matching `twitter.com/<handle>/status/*`.
2. Deduplicate by tweet id (taking the earliest capture as canonical).
3. For each unique tweet id, fetch the Wayback capture HTML and extract the
   tweet text + timestamp from Twitter's old page markup. We are polite — rate
   limit, small concurrency, cache.

This is a best-effort fetcher. Wayback coverage is spotty; we document what's
captured vs. missing in the `sources` table.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..db import upsert_source
from ..util import USER_AGENT, dumps_compact, now_iso, to_iso_utc

CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"

HANDLES = {
    "POTUS45": "POTUS45",
    "WhiteHouse45": "WhiteHouse45",
}

_TWEET_ID_RE = re.compile(r"/status/(\d+)")
_SOURCE_ID = "wayback_potus_whitehouse"


def _cdx_query(handle: str, max_rows: int = 50000) -> list[tuple]:
    """Return a list of (timestamp, original_url) tuples for status captures."""
    params = {
        "url": f"twitter.com/{handle}/status/*",
        "output": "json",
        "fl": "timestamp,original",
        "collapse": "urlkey",
        "limit": str(max_rows),
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(CDX_URL, params=params, headers=headers, timeout=180)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return []
    # First row is the header
    header = rows[0]
    idx_ts = header.index("timestamp")
    idx_url = header.index("original")
    return [(row[idx_ts], row[idx_url]) for row in rows[1:]]


def _earliest_by_id(rows: list[tuple]) -> dict[str, tuple[str, str]]:
    """Collapse to {tweet_id: (earliest_timestamp, original_url)}."""
    out: dict[str, tuple[str, str]] = {}
    for ts, url in rows:
        m = _TWEET_ID_RE.search(url)
        if not m:
            continue
        tid = m.group(1)
        cur = out.get(tid)
        if cur is None or ts < cur[0]:
            out[tid] = (ts, url)
    return out


def _fetch_capture(ts: str, original_url: str) -> str | None:
    """Fetch a Wayback capture. Returns HTML or None."""
    url = f"{WAYBACK_BASE}/{ts}id_/{original_url}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:  # noqa: BLE001
        return None


def _parse_tweet_html(html: str) -> tuple[str | None, str | None]:
    """Extract (text, iso_timestamp) from an old Twitter permalink page.

    Pre-redesign Twitter pages (2015-2020) embed a JSON-LD block with text +
    dateCreated. We look for that first; fall back to meta tags.
    """
    soup = BeautifulSoup(html, "lxml")

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "{}")
        except Exception:  # noqa: BLE001
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("articleBody") or item.get("text") or item.get("description")
            date = item.get("datePublished") or item.get("dateCreated")
            if text and date:
                return str(text), str(date)

    # Fallback: og:description + time tag
    og = soup.find("meta", property="og:description")
    time_el = soup.find("time")
    text = og["content"] if og and og.get("content") else None
    date = time_el.get("datetime") if time_el else None
    if text:
        return text, date
    return None, None


def ingest(
    conn: sqlite3.Connection,
    raw_dir: Path,
    *,
    max_per_handle: int = 50000,
    hydrate_cap: dict[str, int] | None = None,
    sleep_between: float = 0.3,
) -> int:
    """Populate posts table with POTUS45 and WhiteHouse45 tweets from Wayback.

    Hydration is the slow step — we throttle by ``sleep_between`` seconds and
    cache captures under data/raw/wayback_<handle>/<id>.html so re-runs are
    cheap. ``hydrate_cap`` limits how many unique tweet ids we hydrate per
    handle in one pass; cached files count toward the limit as free. Defaults
    are tuned so an in-session build completes in ~15 minutes.
    """
    if hydrate_cap is None:
        # Defaults sized for an in-session build. Wayback responds at ~6-12s per
        # capture fetch in practice, so per-handle caps translate to minutes.
        # Quarterly refresh is expected to raise these and run overnight.
        hydrate_cap = {"POTUS45": 100, "WhiteHouse45": 100}

    total_inserted = 0
    notes: list[str] = []

    for account, handle in HANDLES.items():
        cache_dir = raw_dir / f"wayback_{handle}"
        cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            cdx_rows = _cdx_query(handle, max_rows=max_per_handle)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{handle}: CDX query failed ({type(e).__name__})")
            continue

        # Write index for auditability
        (cache_dir / "cdx_index.json").write_text(
            dumps_compact([{"ts": t, "url": u} for t, u in cdx_rows]),
            encoding="utf-8",
        )

        collapsed = _earliest_by_id(cdx_rows)
        notes.append(f"{handle}: {len(cdx_rows)} captures -> {len(collapsed)} unique tweets")

        rows_to_insert = []
        hydrated = 0
        skipped = 0
        cap = hydrate_cap.get(handle, 2000)
        net_fetches = 0
        ingested_at = now_iso()

        for i, (tid, (ts, original)) in enumerate(collapsed.items()):
            cache_path = cache_dir / f"{tid}.html"
            if cache_path.exists():
                html = cache_path.read_text(encoding="utf-8", errors="replace")
            else:
                if net_fetches >= cap:
                    break  # respect per-handle cap on uncached fetches
                html = _fetch_capture(ts, original)
                if html is None:
                    skipped += 1
                    continue
                cache_path.write_text(html, encoding="utf-8")
                net_fetches += 1
                time.sleep(sleep_between)

            text, date = _parse_tweet_html(html)
            if not text:
                skipped += 1
                continue

            iso_ts = to_iso_utc(date) if date else None
            if iso_ts is None:
                # Fall back to CDX capture timestamp (less accurate; beats nothing)
                try:
                    from datetime import datetime, timezone

                    iso_ts = (
                        datetime.strptime(ts, "%Y%m%d%H%M%S")
                        .replace(tzinfo=timezone.utc)
                        .isoformat()
                    )
                except Exception:  # noqa: BLE001
                    skipped += 1
                    continue

            rows_to_insert.append(
                (
                    f"tw_{tid}",
                    "twitter",
                    account,
                    iso_ts,
                    text,
                    0,
                    1 if text.startswith("@") else 0,
                    None,
                    None,
                    original,
                    None,
                    dumps_compact({"wayback_ts": ts, "wayback_url": original}),
                    ingested_at,
                )
            )
            hydrated += 1

            if (i + 1) % 250 == 0:
                print(f"  [wayback/{handle}] processed {i + 1} / hydrated {hydrated} / net fetches {net_fetches}")

        conn.executemany(
            """
            INSERT INTO posts(id, platform, account, timestamp_utc, text,
                              is_repost, is_reply, reply_to, media_urls_json,
                              source_url, metrics_json, raw_json, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                account=excluded.account,
                text=excluded.text,
                timestamp_utc=COALESCE(posts.timestamp_utc, excluded.timestamp_utc),
                source_url=excluded.source_url,
                ingested_at=excluded.ingested_at
            """,
            rows_to_insert,
        )
        conn.commit()
        total_inserted += len(rows_to_insert)
        notes.append(
            f"{handle}: hydrated {hydrated} / net-fetched {net_fetches} / skipped {skipped}"
        )

    upsert_source(
        conn,
        source_id=_SOURCE_ID,
        name="Wayback CDX -> POTUS45 / WhiteHouse45 tweets",
        url="https://web.archive.org/cdx/search/cdx",
        last_fetched=now_iso(),
        record_count=total_inserted,
        sha256=None,
        notes=" | ".join(notes) or "no captures found",
    )
    return total_inserted
