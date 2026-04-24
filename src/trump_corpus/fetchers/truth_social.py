"""Truth Social archive via CNN-hosted mirror.

Source: https://ix.cnn.io/data/truth-social/truth_archive.json
Updated every ~5 minutes. Successor to the stiles/trump-truth-social-archive
GitHub Action that was disabled 2025-10-26.

Also available as .csv and .parquet at the same path. We pull JSON for maximum
fidelity and store raw per record.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..db import upsert_source
from ..util import download, dumps_compact, now_iso, sha256_file, to_iso_utc

URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"
SOURCE_ID = "cnn_truth_social_archive"
ACCOUNT = "realDonaldTrump"
PLATFORM = "truth_social"


def _extract_records(payload) -> list[dict]:
    """The CNN feed is expected to be a list of Truth records. Handle either shape."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "truths", "posts", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"Unexpected Truth Social payload shape: {type(payload)}")


def _normalize(rec: dict) -> tuple | None:
    # Common Mastodon/Truth Social fields
    tid = str(rec.get("id") or rec.get("status_id") or "").strip()
    if not tid:
        return None

    created = rec.get("created_at") or rec.get("timestamp") or rec.get("date")
    ts = to_iso_utc(created)

    # Text may be in 'content' (HTML), 'text' (plain), or 'body'
    text = rec.get("text") or rec.get("content") or rec.get("body") or ""
    # Strip basic HTML tags if content was delivered as HTML
    if "<" in text and ">" in text:
        import re

        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    reblog = rec.get("reblog") or rec.get("reposted")
    is_repost = 1 if reblog else 0
    in_reply_to = rec.get("in_reply_to_id") or rec.get("reply_to") or None
    is_reply = 1 if in_reply_to else 0

    media_attachments = rec.get("media_attachments") or rec.get("media") or []
    media_urls = []
    if isinstance(media_attachments, list):
        for m in media_attachments:
            if isinstance(m, dict):
                u = m.get("url") or m.get("preview_url") or m.get("remote_url")
                if u:
                    media_urls.append(u)
            elif isinstance(m, str):
                media_urls.append(m)

    metrics = {
        k: rec.get(k)
        for k in ("favourites_count", "reblogs_count", "replies_count", "favorites", "reposts")
        if rec.get(k) is not None
    }

    source_url = rec.get("url") or rec.get("uri") or None

    return (
        f"ts_{tid}",
        PLATFORM,
        ACCOUNT,
        ts,
        text,
        is_repost,
        is_reply,
        str(in_reply_to) if in_reply_to else None,
        dumps_compact(media_urls) if media_urls else None,
        source_url,
        dumps_compact(metrics) if metrics else None,
        dumps_compact(rec),
        now_iso(),
    )


def ingest(conn: sqlite3.Connection, raw_dir: Path) -> int:
    dest = raw_dir / "truth_archive.json"
    download(URL, dest)
    sha = sha256_file(dest)

    with dest.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    records = _extract_records(payload)

    rows = [r for r in (_normalize(rec) for rec in records) if r is not None]

    conn.executemany(
        """
        INSERT INTO posts(id, platform, account, timestamp_utc, text,
                          is_repost, is_reply, reply_to, media_urls_json,
                          source_url, metrics_json, raw_json, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text=excluded.text,
            timestamp_utc=excluded.timestamp_utc,
            is_repost=excluded.is_repost,
            is_reply=excluded.is_reply,
            media_urls_json=excluded.media_urls_json,
            source_url=excluded.source_url,
            metrics_json=excluded.metrics_json,
            raw_json=excluded.raw_json,
            ingested_at=excluded.ingested_at
        """,
        rows,
    )
    conn.commit()

    upsert_source(
        conn,
        source_id=SOURCE_ID,
        name="CNN Truth Social archive (ix.cnn.io)",
        url=URL,
        last_fetched=now_iso(),
        record_count=len(rows),
        sha256=sha,
        notes="Feb 2022 → present. Updated every ~5 min. HTML in content field stripped.",
    )
    return len(rows)
