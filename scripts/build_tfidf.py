"""Distinctive vocabulary per year via TF-IDF.

For each calendar year we treat all that year's posts as a single document, then
score unigrams and bigrams by TF-IDF against the across-years corpus. The top
terms by TF-IDF score are the words that make that year *that year*.

Output: site/data/tfidf.json
  { years: ['2009', ...], by_year: { year: [{term, score, count}, ...] } }
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data" / "tfidf.json"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

URL_RE = re.compile(r"https?://\S+")

# Domain stopwords to suppress noise (keep CAPS-style emphasis tokens though)
EXTRA_STOP = {
    "rt", "amp", "com", "gov", "http", "https", "thanks", "thank",
    "please", "tonight", "today", "tomorrow", "yesterday", "morning",
    "twitter", "donald", "trump", "realdonaldtrump",
}


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

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT timestamp_utc, text FROM posts "
        "WHERE timestamp_utc IS NOT NULL AND text IS NOT NULL"
    ).fetchall()

    by_year_text: dict[str, list[str]] = defaultdict(list)
    for ts, text in rows:
        dt = _parse_utc(ts)
        if not dt or not text:
            continue
        clean = URL_RE.sub("", text)
        by_year_text[dt.astimezone(ET).strftime("%Y")].append(clean)

    years = sorted(y for y, lst in by_year_text.items() if len(lst) >= 50)
    docs = [" ".join(by_year_text[y]) for y in years]

    stop = list(ENGLISH_STOP_WORDS) + list(EXTRA_STOP)
    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words=stop,
        max_df=0.85,        # filter ubiquitous tokens
        min_df=2,
        token_pattern=r"(?u)\b[A-Za-z][A-Za-z']{2,}\b",
        lowercase=True,
        max_features=80000,
        sublinear_tf=True,
    )
    print(f"fitting TF-IDF over {len(years)} years…")
    X = vec.fit_transform(docs)
    feats = vec.get_feature_names_out()

    by_year: dict[str, list[dict]] = {}
    for i, year in enumerate(years):
        row = X[i].toarray().ravel()
        # Top 15 by score (a 1-d vector of size n_features)
        top_idx = row.argsort()[::-1][:15]
        by_year[year] = [
            {"term": str(feats[j]), "score": round(float(row[j]), 4)}
            for j in top_idx if row[j] > 0.0
        ]

    payload = {
        "schema": "TF-IDF top distinctive unigrams+bigrams per year (corpus = all years).",
        "years": years,
        "by_year": by_year,
        "totals": {"years": len(years), "vocab": int(X.shape[1])},
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT}  years={len(years)}  vocab={X.shape[1]}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
