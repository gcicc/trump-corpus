"""Pre-compute nickname-factory JSON for site/analytics.qmd.

Outputs site/data/nicknames.json with:
  - targets: top 30 targets by mention count, with sentiment + total
  - surfaces: per-target list of distinctive nickname surface forms with counts
  - samples: per-target up to 5 short example posts (id, text, ts)
  - bySentiment: top-target list filtered to sentiment in {good, bad}
  - shared_surfaces: surface forms used for >1 target (e.g. "Crooked" -> Hillary, James, Comey)
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
OUT = ROOT / "site" / "data" / "nicknames.json"

TOP_N_TARGETS = 30
SAMPLES_PER_TARGET = 5
TOP_SURFACES_PER_TARGET = 6


def main() -> int:
    if not DB.exists():
        print(f"missing db: {DB}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)

    rows = conn.execute(
        "SELECT post_id, surface, target, sentiment FROM post_nicknames"
    ).fetchall()

    # Aggregate by target
    target_counts: Counter[str] = Counter()
    target_sentiment: dict[str, str] = {}  # majority sentiment per target
    target_surfaces: dict[str, Counter[str]] = defaultdict(Counter)
    target_post_ids: dict[str, list[str]] = defaultdict(list)
    surface_to_targets: dict[str, set[str]] = defaultdict(set)
    target_sentiment_votes: dict[str, Counter[str]] = defaultdict(Counter)

    for pid, surface, target, sentiment in rows:
        target_counts[target] += 1
        target_surfaces[target][surface] += 1
        target_sentiment_votes[target][sentiment] += 1
        if len(target_post_ids[target]) < SAMPLES_PER_TARGET * 4:  # over-pull, dedup later
            target_post_ids[target].append(pid)
        surface_to_targets[surface].add(target)

    for target, votes in target_sentiment_votes.items():
        target_sentiment[target] = votes.most_common(1)[0][0]

    top_targets = [t for t, _ in target_counts.most_common(TOP_N_TARGETS)]

    # Pull post text for samples
    all_pids = list({pid for t in top_targets for pid in target_post_ids[t][:SAMPLES_PER_TARGET]})
    post_meta: dict[str, dict] = {}
    if all_pids:
        placeholders = ",".join("?" * len(all_pids))
        for r in conn.execute(
            f"SELECT id, text, timestamp_utc, platform FROM posts WHERE id IN ({placeholders})",
            all_pids,
        ):
            post_meta[r[0]] = {
                "text": (r[1] or "")[:240],
                "ts": r[2],
                "platform": r[3],
            }

    targets_payload = []
    for t in top_targets:
        surfaces = [
            {"surface": s, "count": c}
            for s, c in target_surfaces[t].most_common(TOP_SURFACES_PER_TARGET)
        ]
        sample_ids = list(dict.fromkeys(target_post_ids[t]))[:SAMPLES_PER_TARGET]
        samples = [post_meta[pid] | {"id": pid} for pid in sample_ids if pid in post_meta]
        targets_payload.append({
            "target": t,
            "count": target_counts[t],
            "sentiment": target_sentiment[t],
            "surfaces": surfaces,
            "samples": samples,
        })

    # Shared surfaces (interesting cross-target reuse)
    shared = []
    for surface, targets in surface_to_targets.items():
        if len(targets) > 1:
            total = sum(target_surfaces[t][surface] for t in targets)
            shared.append({
                "surface": surface,
                "targets": sorted(targets),
                "total": total,
            })
    shared.sort(key=lambda s: -s["total"])
    shared = shared[:20]

    payload = {
        "schema": "nickname-factory data: top targets w/ surfaces + cross-target shared surfaces",
        "targets": targets_payload,
        "shared_surfaces": shared,
        "totals": {
            "mentions": len(rows),
            "unique_targets": len(target_counts),
            "unique_surfaces": len(surface_to_targets),
        },
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT}  targets={len(targets_payload)}  "
          f"shared_surfaces={len(shared)}  mentions={len(rows)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
