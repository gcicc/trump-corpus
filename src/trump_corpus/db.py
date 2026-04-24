"""SQLite schema + connection helpers for the unified Trump corpus."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id              TEXT PRIMARY KEY,   -- platform-prefixed: tw_<id>, ts_<id>
    platform        TEXT NOT NULL,      -- 'twitter' | 'truth_social'
    account         TEXT NOT NULL,      -- 'realDonaldTrump', 'POTUS45', 'WhiteHouse45'
    timestamp_utc   TEXT NOT NULL,      -- ISO 8601 UTC
    text            TEXT NOT NULL,
    is_repost       INTEGER NOT NULL DEFAULT 0,
    is_reply        INTEGER NOT NULL DEFAULT 0,
    reply_to        TEXT,
    media_urls_json TEXT,               -- JSON array of URLs
    source_url      TEXT,               -- permalink if known
    metrics_json    TEXT,               -- JSON: {likes, reposts, replies, ...}
    raw_json        TEXT,               -- original record, verbatim
    ingested_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_posts_platform  ON posts(platform);
CREATE INDEX IF NOT EXISTS idx_posts_account   ON posts(account);

CREATE TABLE IF NOT EXISTS speeches (
    id           TEXT PRIMARY KEY,
    event_date   TEXT,                  -- ISO date (may be partial/unknown)
    event_type   TEXT,                  -- 'rally', 'press_briefing', 'interview', 'address', ...
    title        TEXT,
    location     TEXT,
    text         TEXT NOT NULL,
    source       TEXT NOT NULL,         -- 'miller_center', 'kaggle_rallies', ...
    source_url   TEXT,
    ingested_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(event_date);
CREATE INDEX IF NOT EXISTS idx_speeches_type ON speeches(event_type);

CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,    -- stable key, e.g. 'hershey_twitter_archive'
    name           TEXT NOT NULL,
    url            TEXT,
    last_fetched   TEXT,
    record_count   INTEGER,
    sha256         TEXT,                -- of the raw artifact, when applicable
    notes          TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    name: str,
    url: str | None,
    last_fetched: str,
    record_count: int,
    sha256: str | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO sources(source_id, name, url, last_fetched, record_count, sha256, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            name=excluded.name,
            url=excluded.url,
            last_fetched=excluded.last_fetched,
            record_count=excluded.record_count,
            sha256=excluded.sha256,
            notes=excluded.notes
        """,
        (source_id, name, url, last_fetched, record_count, sha256, notes),
    )
    conn.commit()
