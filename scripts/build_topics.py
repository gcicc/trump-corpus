"""Run multi-label topic assignment on the corpus.

Usage:
    python scripts/build_topics.py [--threshold 0.25] [--top-k 3]

Reads from `posts`, writes `theme_catalog`, `post_themes`, `post_nicknames`.
Optionally dumps normalized embeddings to data/processed/embeddings.npy for
later vector-search / "find similar" features.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trump_corpus.db import connect  # noqa: E402
from trump_corpus.topics import assign_multilabel  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=0.25)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--save-embeddings", action="store_true")
    p.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="sentence-transformers model id (default is fast, 384-dim)",
    )
    args = p.parse_args()

    db_path = ROOT / "data" / "processed" / "corpus.sqlite"
    embeddings_out = ROOT / "data" / "processed" / "embeddings.npy" if args.save_embeddings else None

    conn = connect(db_path)

    t0 = time.time()
    stats = assign_multilabel(
        conn,
        top_k=args.top_k,
        threshold=args.threshold,
        model_name=args.model,
        embeddings_out=embeddings_out,
    )
    dt = time.time() - t0
    print(f"\ncompleted in {dt / 60:.1f} min")
    print(f"posts labeled: {stats['total']}")
    print("primary-theme distribution:")
    for theme, n in sorted(stats["primary_counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {theme:24s} {n:>7d}")

    # Also report nickname hit counts
    hit_counts = dict(
        conn.execute(
            "SELECT sentiment, COUNT(DISTINCT post_id) FROM post_nicknames GROUP BY sentiment"
        ).fetchall()
    )
    print("\nnickname hits:")
    for s, n in hit_counts.items():
        print(f"  {s:>6s}: {n} posts")
    top_targets = conn.execute(
        "SELECT target, COUNT(*) c FROM post_nicknames GROUP BY target ORDER BY c DESC LIMIT 15"
    ).fetchall()
    print("\ntop nickname targets:")
    for target, n in top_targets:
        print(f"  {target:30s} {n}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
