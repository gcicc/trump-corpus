"""Quarterly refresh entrypoint.

For the mutable sources (Truth Social, post-2022 X) this just re-runs the full
build — the upsert semantics handle change. For the frozen sources (2009-2021
Twitter archive, early speeches) the SHA is recorded in `sources`; we re-pull
anyway because the cost is trivial and it lets us detect upstream changes.

Print a delta summary vs. the previous run.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"


def _snapshot(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    return {
        "posts": cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        "speeches": cur.execute("SELECT COUNT(*) FROM speeches").fetchone()[0],
        "sources": dict(
            cur.execute("SELECT source_id, record_count FROM sources").fetchall()
        ),
    }


def main() -> int:
    before = _snapshot(sqlite3.connect(DB)) if DB.exists() else {"posts": 0, "speeches": 0, "sources": {}}

    # Delegate to build_corpus (upsert-safe).
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_corpus", ROOT / "scripts" / "build_corpus.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    rc = mod.main()

    after = _snapshot(sqlite3.connect(DB))

    print()
    print("delta:")
    print(f"  posts:    {before['posts']:>7d} -> {after['posts']:>7d}   (+{after['posts'] - before['posts']})")
    print(f"  speeches: {before['speeches']:>7d} -> {after['speeches']:>7d}   (+{after['speeches'] - before['speeches']})")
    all_keys = sorted(set(before["sources"]) | set(after["sources"]))
    for k in all_keys:
        b = before["sources"].get(k, 0)
        a = after["sources"].get(k, 0)
        print(f"  {k:40s} {b:>7d} -> {a:>7d}   (+{a - b})")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
