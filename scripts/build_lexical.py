"""Compute lexical-style indices per month: CAPS-shouting and exclamation density.

CAPS index per post = (# words that are 3+ chars and ALL upper) / (# words 3+ chars)
Exclamation density per post = count of '!' divided by post length / 100 (so it's a
'! per 100 chars' rate — comparable across post lengths).

Aggregated to monthly mean and 90th-percentile (the spike line) per platform group.

Output: site/data/lexical.json
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data" / "lexical.json"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

WORD_RE = re.compile(r"[A-Za-z][A-Za-z']+")


def _parse_utc(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("T", " ").replace("Z", "")).replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        return None


def caps_ratio(text: str) -> float:
    words = [w for w in WORD_RE.findall(text or "") if len(w) >= 3]
    if not words:
        return 0.0
    caps = sum(1 for w in words if w.isupper())
    return caps / len(words)


def excl_rate(text: str) -> float:
    if not text:
        return 0.0
    return text.count("!") / max(1, len(text)) * 100.0  # per 100 chars


def main() -> int:
    if not DB.exists():
        print(f"missing db: {DB}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT timestamp_utc, text, platform FROM posts "
        "WHERE timestamp_utc IS NOT NULL AND text IS NOT NULL"
    ).fetchall()

    by_month_caps: dict[str, list[float]] = defaultdict(list)
    by_month_excl: dict[str, list[float]] = defaultdict(list)
    counts_by_month: dict[str, int] = defaultdict(int)

    for ts, text, platform in rows:
        dt = _parse_utc(ts)
        if not dt or not text or len(text) < 10:
            continue
        ym = dt.astimezone(ET).strftime("%Y-%m")
        by_month_caps[ym].append(caps_ratio(text))
        by_month_excl[ym].append(excl_rate(text))
        counts_by_month[ym] += 1

    months = sorted(by_month_caps.keys())
    series = []
    for ym in months:
        caps = by_month_caps[ym]
        excl = by_month_excl[ym]
        # Skip thin months
        if len(caps) < 5:
            continue
        series.append({
            "month": ym,
            "n": counts_by_month[ym],
            "caps_mean": round(statistics.mean(caps), 4),
            "caps_p90": round(statistics.quantiles(caps, n=10)[8] if len(caps) >= 10 else max(caps), 4),
            "excl_mean": round(statistics.mean(excl), 4),
            "excl_p90": round(statistics.quantiles(excl, n=10)[8] if len(excl) >= 10 else max(excl), 4),
        })

    payload = {
        "schema": "monthly mean + p90 of CAPS ratio (caps_*) and exclamation density per 100 chars (excl_*)",
        "months": series,
        "totals": {"posts_scored": sum(counts_by_month.values()), "months": len(series)},
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT}  months={len(series)}  posts_scored={sum(counts_by_month.values())}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
