"""Compute VADER compound sentiment per post, aggregate to theme x month.

VADER is lexicon-based, deterministic, and CPU-only — runs on 87k posts in
under a minute. Compound score is in [-1, +1].

Output: site/data/sentiment.json
  - by_theme: { theme: [{month, mean, n}, ...] }  (3-month rolling mean built client-side)
  - overall:  [{month, mean, n}, ...]
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data" / "sentiment.json"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _parse_utc(s: str) -> datetime | None:
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

    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()

    conn = sqlite3.connect(DB)

    # Pull (post_id, ts, text) and a join map (post_id -> rank=1 theme)
    print("loading posts…")
    posts = conn.execute(
        "SELECT id, timestamp_utc, text FROM posts "
        "WHERE timestamp_utc IS NOT NULL AND text IS NOT NULL"
    ).fetchall()
    print(f"  {len(posts)} posts")

    print("loading rank=1 themes…")
    theme_map: dict[str, str] = {}
    for pid, theme in conn.execute("SELECT post_id, theme FROM post_themes WHERE rank=1"):
        theme_map[pid] = theme
    print(f"  {len(theme_map)} posts have a primary theme")
    conn.close()

    # Score and aggregate
    by_overall: dict[str, list[float]] = defaultdict(list)
    by_theme_month: dict[tuple[str, str], list[float]] = defaultdict(list)

    print("scoring with VADER…")
    for i, (pid, ts, text) in enumerate(posts):
        dt = _parse_utc(ts)
        if not dt or not text or len(text) < 10:
            continue
        ym = dt.astimezone(ET).strftime("%Y-%m")
        s = sia.polarity_scores(text)["compound"]
        by_overall[ym].append(s)
        theme = theme_map.get(pid)
        if theme:
            by_theme_month[(theme, ym)].append(s)
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1}/{len(posts)}")

    # Aggregate overall
    months_sorted = sorted(by_overall.keys())
    overall = []
    for ym in months_sorted:
        v = by_overall[ym]
        if len(v) < 5:
            continue
        overall.append({"month": ym, "mean": round(statistics.mean(v), 4), "n": len(v)})

    # Aggregate per theme
    by_theme: dict[str, list[dict]] = defaultdict(list)
    seen_pairs = sorted(by_theme_month.keys())
    for theme, ym in seen_pairs:
        v = by_theme_month[(theme, ym)]
        if len(v) < 5:  # skip thin theme-month buckets
            continue
        by_theme[theme].append({"month": ym, "mean": round(statistics.mean(v), 4), "n": len(v)})

    payload = {
        "schema": "VADER compound score per post, monthly mean (compound in [-1,+1]).",
        "overall": overall,
        "by_theme": dict(by_theme),
        "totals": {
            "posts_scored": sum(len(v) for v in by_overall.values()),
            "themes": len(by_theme),
            "months": len(months_sorted),
        },
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT}  themes={len(by_theme)}  months={len(months_sorted)}  "
          f"posts_scored={payload['totals']['posts_scored']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
