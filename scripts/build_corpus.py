"""One-shot full build of the Trump corpus.

Usage (from project root with venv activated):
    python scripts/build_corpus.py

Idempotent. Safe to re-run: upserts by ID.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trump_corpus.db import connect  # noqa: E402
from trump_corpus.fetchers import (  # noqa: E402
    nitter,
    potus_wayback,
    speeches,
    truth_social,
    twitter_archive,
    ucsb_presidency,
)

RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "processed" / "corpus.sqlite"


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect(DB_PATH)

    steps = [
        ("Twitter archive (@realDonaldTrump 2009-2021)", twitter_archive.ingest),
        ("Truth Social (ix.cnn.io)", truth_social.ingest),
        ("@POTUS45 / @WhiteHouse45 via Wayback CDX", potus_wayback.ingest),
        ("@realDonaldTrump post-2022 via nitter", nitter.ingest),
        ("UCSB American Presidency Project (speeches)", ucsb_presidency.ingest),
        ("Speeches (ryanmcdermott + Miller Center)", speeches.ingest),
    ]

    results: list[tuple[str, int, float, str | None]] = []
    for label, fn in steps:
        t0 = time.time()
        try:
            n = fn(conn, RAW_DIR)
            err = None
        except Exception as e:  # noqa: BLE001
            n = 0
            err = f"{type(e).__name__}: {e}"
            print(f"[WARN] {label} failed: {err}", file=sys.stderr)
        dt = time.time() - t0
        results.append((label, n, dt, err))
        status = "OK" if err is None else "ERR"
        print(f"  [{status}] {label:55s} {n:>7d} rows  {dt:6.1f}s")

    # Summary
    cur = conn.cursor()
    posts_total = cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    speeches_total = cur.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
    by_platform = cur.execute(
        "SELECT platform, account, COUNT(*) FROM posts GROUP BY platform, account ORDER BY platform, account"
    ).fetchall()

    print()
    print(f"posts    total: {posts_total}")
    for platform, account, n in by_platform:
        print(f"  {platform:14s} {account:20s} {n:>7d}")
    print(f"speeches total: {speeches_total}")

    conn.close()
    return 0 if all(err is None for *_, err in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
