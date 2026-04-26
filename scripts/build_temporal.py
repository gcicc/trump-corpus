"""Pre-compute temporal analytics JSON for site/analytics.qmd.

Outputs:
  site/data/temporal.json   — hour-of-day (ET) x day-of-week post counts
                              + a few sample post ids per cell for click-to-expand
  site/data/storm_days.json — per-day post counts and z-score-within-year,
                              flag z>3 as 'storm', annotate top theme of the day

Notes:
  - Timestamps in posts.timestamp_utc are ISO-8601 UTC (e.g. 2018-01-27 19:55:34).
  - Converted to America/New_York (ET) for human-natural reading. DST handled
    automatically by zoneinfo (stdlib).
  - 'top theme of day' uses post_themes rank=1 (the dominant theme per post).
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data"
TEMPORAL = OUT / "temporal.json"
STORMS = OUT / "storm_days.json"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SAMPLES_PER_CELL = 3
RNG = random.Random(0)


def _parse_utc(s: str) -> datetime | None:
    if not s:
        return None
    try:
        s = s.replace("T", " ").replace("Z", "")
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        return None


def build_temporal(conn: sqlite3.Connection) -> dict:
    """Hour-of-day (0-23) x day-of-week (0=Mon..6=Sun) heatmap, ET."""
    rows = conn.execute(
        "SELECT id, timestamp_utc FROM posts WHERE timestamp_utc IS NOT NULL"
    ).fetchall()

    counts: list[list[int]] = [[0] * 24 for _ in range(7)]
    samples: dict[str, list[str]] = defaultdict(list)  # "dow,hour" -> [post_id, ...]

    for pid, ts in rows:
        dt = _parse_utc(ts)
        if not dt:
            continue
        local = dt.astimezone(ET)
        dow = local.weekday()  # Mon=0
        hour = local.hour
        counts[dow][hour] += 1
        key = f"{dow},{hour}"
        bucket = samples[key]
        # Reservoir-sample SAMPLES_PER_CELL ids
        if len(bucket) < SAMPLES_PER_CELL:
            bucket.append(pid)
        else:
            i = RNG.randint(0, counts[dow][hour] - 1)
            if i < SAMPLES_PER_CELL:
                bucket[i] = pid

    # Materialize sample post text + timestamp for inline display
    sample_ids = [pid for ids in samples.values() for pid in ids]
    sample_meta: dict[str, dict] = {}
    if sample_ids:
        placeholders = ",".join("?" * len(sample_ids))
        for r in conn.execute(
            f"SELECT id, text, timestamp_utc, platform FROM posts WHERE id IN ({placeholders})",
            sample_ids,
        ):
            sample_meta[r[0]] = {
                "text": (r[1] or "")[:240],
                "ts": r[2],
                "platform": r[3],
            }

    return {
        "schema": "counts[dow][hour] = post count (Mon=0); ET timezone",
        "dow_names": DOW_NAMES,
        "hours": list(range(24)),
        "counts": counts,
        "samples": dict(samples),
        "sample_meta": sample_meta,
        "total": sum(sum(row) for row in counts),
    }


def build_storms(conn: sqlite3.Connection) -> dict:
    """Per-day post counts + z-score within calendar year. Flag z>3 as storm."""
    rows = conn.execute(
        "SELECT id, timestamp_utc FROM posts WHERE timestamp_utc IS NOT NULL"
    ).fetchall()

    by_day: dict[str, list[str]] = defaultdict(list)  # 'YYYY-MM-DD' -> [post_id]
    for pid, ts in rows:
        dt = _parse_utc(ts)
        if not dt:
            continue
        local = dt.astimezone(ET)
        by_day[local.strftime("%Y-%m-%d")].append(pid)

    # Group by year for z-score normalization
    by_year: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for day, ids in by_day.items():
        by_year[day[:4]].append((day, len(ids)))

    days_payload: list[dict] = []
    storm_post_ids: list[str] = []
    for year, day_counts in by_year.items():
        counts_only = [c for _, c in day_counts]
        n = len(counts_only)
        mean = sum(counts_only) / n
        var = sum((c - mean) ** 2 for c in counts_only) / n
        sd = math.sqrt(var) if var > 0 else 1.0
        for day, c in day_counts:
            z = (c - mean) / sd
            entry = {"day": day, "count": c, "z": round(z, 2)}
            if z > 3.0:
                entry["storm"] = True
                storm_post_ids.extend(by_day[day][:5])  # cap per storm
            days_payload.append(entry)

    days_payload.sort(key=lambda d: d["day"])

    # For each storm day, find the dominant theme (post_themes rank=1 mode)
    storm_days = [d for d in days_payload if d.get("storm")]
    if storm_days:
        # Pull all rank=1 themes for posts on storm days
        all_storm_pids = [pid for d in storm_days for pid in by_day[d["day"]]]
        placeholders = ",".join("?" * len(all_storm_pids))
        theme_rows = conn.execute(
            f"SELECT post_id, theme FROM post_themes "
            f"WHERE rank=1 AND post_id IN ({placeholders})",
            all_storm_pids,
        ).fetchall()
        pid_to_theme = {pid: th for pid, th in theme_rows}
        for d in storm_days:
            themes = [pid_to_theme.get(pid) for pid in by_day[d["day"]]]
            themes = [t for t in themes if t]
            if themes:
                d["top_theme"] = Counter(themes).most_common(1)[0][0]

    return {
        "schema": "per-day post counts and z-score within calendar year (ET); storm = z>3",
        "days": days_payload,
        "storm_count": sum(1 for d in days_payload if d.get("storm")),
    }


def main() -> int:
    if not DB.exists():
        print(f"missing db: {DB}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)

    t = build_temporal(conn)
    TEMPORAL.write_text(json.dumps(t), encoding="utf-8")
    print(f"wrote {TEMPORAL}  total_posts={t['total']}")

    s = build_storms(conn)
    STORMS.write_text(json.dumps(s), encoding="utf-8")
    print(f"wrote {STORMS}  storm_days={s['storm_count']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
