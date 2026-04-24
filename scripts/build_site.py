"""Generate all data-driven Quarto pages and JSON assets.

Run after build_topics.py. Safe to rerun — overwrites generated pages but does
not touch hand-edited ones (index.qmd, about.qmd, etc.).
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trump_corpus.site import render_all  # noqa: E402


def main() -> int:
    db = ROOT / "data" / "processed" / "corpus.sqlite"
    if not db.exists():
        print(f"No db at {db}; run build_corpus.py + build_topics.py first", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db)
    t0 = time.time()
    render_all(conn)
    print(f"rendered site pages in {time.time() - t0:.1f}s")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
