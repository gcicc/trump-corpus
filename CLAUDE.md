---
tier: Full
project: trump-corpus
---

# CLAUDE.md — trump-corpus

## Purpose

Build and maintain a unified, text-minable corpus of Donald Trump's public
messaging across Twitter / X / Truth Social / speeches, for downstream
analysis (sentiment, topic modeling, style, timeline work).

## Working conventions

- Language: Python 3.11+. Ruff for formatting.
- Storage: SQLite for canonical, Parquet for analytics, CSV/JSON for raw dumps.
- Never mutate files in `data/raw/` — they are provenance.
- All fetchers must be idempotent and re-runnable (quarterly refresh is the norm).
- Each fetcher writes a row to the `sources` table recording what it pulled.

## Non-goals

- No real-time streaming. Quarterly batch refresh is sufficient.
- No LLM-in-the-loop processing unless explicitly scoped with cost analysis.
- No commentary, framing, or editorial transformations on the text itself.
  Store text as-delivered; derive features in a separate layer.

## Known gaps (maintain in sources.md)

- `@POTUS45` / `@WhiteHouse45`: NARA archives them but offers no bulk download.
  Best-effort via Wayback CDX or community dumps. Document what's in and out.
- Post-2022 `@realDonaldTrump` X activity: low volume, may require manual touch.

## Refresh cadence

Quarterly. Next refresh target: 2026-07-24 (one quarter from 2026-04-24 build).
