"""Export SQLite tables to Parquet for analytic workloads."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "data" / "processed"


def export_table(conn: sqlite3.Connection, name: str) -> int:
    df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False)
    return len(df)


def main() -> int:
    if not DB.exists():
        print(f"No db at {DB}; run build_corpus.py first", file=sys.stderr)
        return 1
    conn = sqlite3.connect(DB)
    tables = ["posts", "speeches", "sources"]
    # Include topic tables if they exist (built by build_topics.py)
    for extra in ("theme_catalog", "post_themes", "post_nicknames"):
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (extra,)
        ).fetchone()
        if exists:
            tables.append(extra)
    for t in tables:
        n = export_table(conn, t)
        print(f"  wrote {t}.parquet  {n} rows")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
