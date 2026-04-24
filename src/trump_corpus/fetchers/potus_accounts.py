"""@POTUS45 / @WhiteHouse45 — official-capacity Twitter accounts.

NARA's Trump Presidential Library archives these but offers no bulk download.
We attempt two paths:

1. **Wayback CDX** — query the Internet Archive for captured twitter.com pages.
   This gets us URLs that exist in the Wayback, not tweet text. Logged as a gap.
2. **Community dumps (optional)** — if we locate a third-party CSV/JSON, wire it
   here. None wired yet.

For now this fetcher records the gap in the `sources` table so the corpus is
honest about coverage. Revisit for Q3 refresh.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..db import upsert_source
from ..util import now_iso


def ingest(conn: sqlite3.Connection, raw_dir: Path) -> int:  # noqa: ARG001
    upsert_source(
        conn,
        source_id="potus_whitehouse_gap",
        name="@POTUS45 / @WhiteHouse45 — NARA archive",
        url="https://www.trumplibrary.gov/research/archived-social-media",
        last_fetched=now_iso(),
        record_count=0,
        sha256=None,
        notes=(
            "Official-capacity accounts archived by NARA but no bulk export. "
            "Path forward options: (a) Wayback CDX scrape of twitter.com/POTUS45, "
            "(b) community JSON dump if located, (c) FOIA request. "
            "Tracked in ACTION-ITEMS.md for Q3 refresh."
        ),
    )
    return 0
