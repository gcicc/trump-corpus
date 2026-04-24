"""Emit a human-readable summary of the corpus to data/processed/summary.md.

Run after build_corpus.py (and optionally build_topics.py) to get a snapshot
of: sources, counts by platform/account/year, nickname leaderboard, theme
distribution, and known gaps.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "data" / "processed" / "summary.md"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def main() -> int:
    if not DB.exists():
        print(f"No db at {DB}; run build_corpus.py first", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    lines: list[str] = []

    lines.append("# Trump Corpus — Summary")
    lines.append("")
    lines.append(f"*Generated {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}*")
    lines.append("")

    # ---- Posts ----
    posts_total = cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    speeches_total = cur.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
    lines.append(f"## Totals\n\n- **Posts:** {posts_total:,}\n- **Speeches/transcripts:** {speeches_total:,}\n")

    # ---- By platform + account ----
    lines.append("## Posts by platform and account\n")
    lines.append("| Platform | Account | Count | Earliest | Latest |")
    lines.append("|---|---|---:|---|---|")
    for row in cur.execute(
        """
        SELECT platform, account, COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc)
          FROM posts
         GROUP BY platform, account
         ORDER BY platform, account
        """
    ):
        platform, account, n, mn, mx = row
        lines.append(f"| {platform} | {account} | {n:,} | {mn[:10] if mn else '—'} | {mx[:10] if mx else '—'} |")
    lines.append("")

    # ---- By year ----
    lines.append("## Posts by year\n")
    lines.append("| Year | Count |")
    lines.append("|---|---:|")
    for year, n in cur.execute(
        "SELECT substr(timestamp_utc,1,4) y, COUNT(*) FROM posts GROUP BY y ORDER BY y"
    ):
        if year:
            lines.append(f"| {year} | {n:,} |")
    lines.append("")

    # ---- Sources ----
    lines.append("## Sources\n")
    lines.append("| Source | Records | Last fetched | Notes |")
    lines.append("|---|---:|---|---|")
    for sid, name, n, last, notes in cur.execute(
        "SELECT source_id, name, record_count, last_fetched, notes FROM sources ORDER BY record_count DESC"
    ):
        note = (notes or "").replace("\n", " ")
        if len(note) > 120:
            note = note[:117] + "..."
        lines.append(f"| `{sid}` | {n:,} | {last[:10] if last else '—'} | {note} |")
    lines.append("")

    # ---- Themes (if present) ----
    if _table_exists(conn, "post_themes"):
        # Pre-load the catalog so we don't run nested queries on `cur`.
        catalog: dict[str, str] = {}
        if _table_exists(conn, "theme_catalog"):
            catalog = dict(conn.execute("SELECT slug, label FROM theme_catalog").fetchall())

        total_labeled = (
            conn.execute("SELECT COUNT(DISTINCT post_id) FROM post_themes").fetchone()[0]
            or 1
        )
        rows = conn.execute(
            """
            SELECT theme, COUNT(*)
              FROM post_themes
             WHERE rank = 1
             GROUP BY theme
             ORDER BY 2 DESC
            """
        ).fetchall()

        lines.append("## Theme distribution (primary label)\n")
        lines.append("| Theme | Posts | Share |")
        lines.append("|---|---:|---:|")
        for theme, n in rows:
            label = catalog.get(theme, theme)
            lines.append(f"| {label} | {n:,} | {100 * n / total_labeled:.1f}% |")
        lines.append("")

        # ---- Multi-label density ----
        avg = conn.execute(
            "SELECT AVG(c) FROM (SELECT post_id, COUNT(*) c FROM post_themes GROUP BY post_id)"
        ).fetchone()[0]
        lines.append(f"Average themes per post (multi-label): **{avg:.2f}**\n")

    # ---- Nicknames (if present) ----
    if _table_exists(conn, "post_nicknames"):
        lines.append("## Nicknames — top 20 targets\n")
        lines.append("| Target | Sentiment | Posts |")
        lines.append("|---|---|---:|")
        for target, sentiment, n in cur.execute(
            """
            SELECT target, sentiment, COUNT(DISTINCT post_id)
              FROM post_nicknames
             GROUP BY target, sentiment
             ORDER BY 3 DESC
             LIMIT 20
            """
        ):
            lines.append(f"| {target} | {sentiment} | {n:,} |")
        lines.append("")

    # ---- Schema hints ----
    lines.append("## Schema\n")
    lines.append("Key tables:")
    lines.append("")
    lines.append("- `posts(id, platform, account, timestamp_utc, text, is_repost, is_reply, reply_to, media_urls_json, source_url, metrics_json, raw_json, ingested_at)`")
    lines.append("- `speeches(id, event_date, event_type, title, location, text, source, source_url, ingested_at)`")
    lines.append("- `sources(source_id, name, url, last_fetched, record_count, sha256, notes)`")
    if _table_exists(conn, "post_themes"):
        lines.append("- `theme_catalog(slug, label, description, color, anchor_count)`")
        lines.append("- `post_themes(post_id, theme, score, rank)`  — 1..3 rows per post")
        lines.append("- `post_nicknames(post_id, surface, target, sentiment)`")
    lines.append("")
    lines.append("Parquet exports (regenerate with `python scripts/export_parquet.py`):")
    lines.append("`posts.parquet`, `speeches.parquet`, `sources.parquet`.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
