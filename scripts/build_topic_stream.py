"""Per-month post count per theme (rank=1) for the stream graph.

Output: site/data/topic_stream.json
  { months: ['YYYY-MM', ...], themes: ['border', ...], counts: { theme: [n_per_month, ...] } }
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data" / "topic_stream.json"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _parse_utc(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("T", " ").replace("Z", "")).replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    if not DB.exists():
        print(f"missing db: {DB}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)

    rows = conn.execute(
        """
        SELECT p.timestamp_utc, pt.theme
          FROM post_themes pt
          JOIN posts p ON p.id = pt.post_id
         WHERE pt.rank = 1 AND p.timestamp_utc IS NOT NULL
        """
    ).fetchall()
    conn.close()

    counts: dict[tuple[str, str], int] = defaultdict(int)  # (theme, ym) -> n
    months_set: set[str] = set()
    themes_set: set[str] = set()
    for ts, theme in rows:
        dt = _parse_utc(ts)
        if not dt:
            continue
        ym = dt.astimezone(ET).strftime("%Y-%m")
        counts[(theme, ym)] += 1
        months_set.add(ym)
        themes_set.add(theme)

    months = sorted(months_set)
    themes = sorted(themes_set)
    by_theme: dict[str, list[int]] = {
        t: [counts.get((t, m), 0) for m in months] for t in themes
    }

    payload = {
        "schema": "month-by-theme post counts (rank=1 only).",
        "months": months,
        "themes": themes,
        "counts": by_theme,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT}  months={len(months)}  themes={len(themes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
