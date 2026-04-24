"""@realDonaldTrump 2009-2021 tweets from MarkHershey/CompleteTrumpTweetsArchive.

Source: https://github.com/MarkHershey/CompleteTrumpTweetsArchive
Covers May 4, 2009 through Jan 8, 2021 (account suspension). Includes later-deleted
tweets. Two CSVs: before-office (pre-2017) and in-office (2017-2021).
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

from ..db import upsert_source
from ..util import download, dumps_compact, now_iso, sha256_file, to_iso_utc

_TWEET_ID_RE = re.compile(r"/status/(\d+)")

BASE = "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data"
FILES = {
    "before_office": f"{BASE}/realDonaldTrump_bf_office.csv",
    "in_office": f"{BASE}/realDonaldTrump_in_office.csv",
}

SOURCE_ID = "hershey_twitter_archive"
ACCOUNT = "realDonaldTrump"
PLATFORM = "twitter"


def _parse_csv(path: Path):
    """Yield normalized dicts from a Hershey CSV.

    Header in file is: "ID, Time, Tweet URL, Tweet Text" with leading spaces in
    all but the first column name. The "ID" column actually contains the
    handle (@realDonaldTrump); the numeric tweet id is embedded in the URL.
    We normalize keys by stripping whitespace.
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out = {}
            for k, v in row.items():
                key = (k or "").strip() if isinstance(k, str) else ""
                if isinstance(v, list):
                    # csv.DictReader puts excess fields under a None key as a list;
                    # rejoin so we don't lose text that contained stray commas.
                    v = ",".join(str(x) for x in v)
                elif v is None:
                    v = ""
                out[key] = str(v).strip()
            yield out


def ingest(conn: sqlite3.Connection, raw_dir: Path) -> int:
    ingested_at = now_iso()
    total = 0
    sha_parts: list[str] = []

    for label, url in FILES.items():
        dest = raw_dir / f"hershey_{label}.csv"
        download(url, dest)
        sha_parts.append(sha256_file(dest))

        rows = []
        skipped = 0
        for r in _parse_csv(dest):
            url_field = r.get("Tweet URL") or r.get("url") or ""
            m = _TWEET_ID_RE.search(url_field)
            tweet_id = m.group(1) if m else ""
            if not tweet_id:
                skipped += 1
                continue

            text = r.get("Tweet Text") or r.get("text") or ""
            ts_raw = r.get("Time") or r.get("Date") or ""
            try:
                ts = to_iso_utc(ts_raw) if ts_raw else None
            except Exception:  # noqa: BLE001
                ts = None
            if ts is None:
                skipped += 1
                continue

            rows.append(
                (
                    f"tw_{tweet_id}",
                    PLATFORM,
                    ACCOUNT,
                    ts,
                    text,
                    0,  # is_repost not flagged in this archive
                    1 if text.startswith("@") else 0,
                    None,
                    None,
                    url_field or None,
                    None,
                    dumps_compact(r),
                    ingested_at,
                )
            )
        if skipped:
            print(f"  [twitter_archive] {label}: skipped {skipped} rows (no id/timestamp)")

        conn.executemany(
            """
            INSERT INTO posts(id, platform, account, timestamp_utc, text,
                              is_repost, is_reply, reply_to, media_urls_json,
                              source_url, metrics_json, raw_json, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                timestamp_utc=excluded.timestamp_utc,
                source_url=excluded.source_url,
                raw_json=excluded.raw_json,
                ingested_at=excluded.ingested_at
            """,
            rows,
        )
        conn.commit()
        total += len(rows)

    upsert_source(
        conn,
        source_id=SOURCE_ID,
        name="MarkHershey/CompleteTrumpTweetsArchive",
        url="https://github.com/MarkHershey/CompleteTrumpTweetsArchive",
        last_fetched=ingested_at,
        record_count=total,
        sha256=",".join(sha_parts),
        notes="@realDonaldTrump 2009-05-04 to 2021-01-08. Includes later-deleted tweets.",
    )
    return total
