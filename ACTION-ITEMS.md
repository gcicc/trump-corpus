# Action Items — trump-corpus

**Last updated:** 2026-04-24

## Blockers (human-only)
- None

## To Do
- [ ] Next session: build Quarto site per approved plan (themes grid, timeline drill-down, dads80th-style map, XTTS-v2 Trump-voice read-aloud, presidential styling, year-portrait imagery) — see `C:\Users\gcicc\.claude\plans\swirling-zooming-hammock.md`
- [ ] Next session: source presidential/family imagery (Wikimedia Commons PD, whitehouse.gov PD) — one representative portrait per year 2009-2026
- [ ] Next session: clone Trump voice from a clean public-domain speech clip with Coqui XTTS-v2; pre-render top-500 posts
- [ ] Quarterly-refresh-only: overnight Wayback hydration of remaining POTUS45 (~1250 more) + WhiteHouse45 (~18k) tweets — bump `hydrate_cap` in `potus_wayback.ingest` and run unattended
- [ ] Quarterly-refresh-only: rerun UCSB with `max_pages=30` to pick up 2025+ documents we didn't fetch this session (cap was 9 to finish in-session)
- [ ] Investigate a working nitter mirror for post-2022 @realDonaldTrump tweets; defer to quarterly if still blocked
- [ ] BERTopic discovery pass to seed "find similar posts" feature (separate from the curated 18-theme assignment)

## Done
- [x] Scaffolded project: pyproject, venv outside Dropbox, SQLite schema, raw/processed layout (completed 2026-04-24)
- [x] Ingested @realDonaldTrump 2009-2021 Twitter archive (54,306 rows) (completed 2026-04-24)
- [x] Ingested Truth Social archive (32,789 rows) (completed 2026-04-24)
- [x] Wayback CDX fetcher for @POTUS45 / @WhiteHouse45 built; 51 POTUS45 rows this session (completed 2026-04-24)
- [x] Nitter fetcher built for post-2022 @realDonaldTrump; 0 rows (mirrors unreachable at scrape time) (completed 2026-04-24)
- [x] UCSB American Presidency Project scraper built; 871 speeches/statements/EOs (completed 2026-04-24)
- [x] Miller Center + ryanmcdermott seed speech sources (13 rows) (completed 2026-04-24)
- [x] Installed BERTopic + sentence-transformers + plotly (completed 2026-04-24)
- [x] Built 18-theme curated taxonomy with separate Good/Bad Nicknames bins (completed 2026-04-24)
- [x] Compiled nickname regex catalog (~60 patterns across 40+ targets) (completed 2026-04-24)
- [x] Multi-label topic assignment with top-3 + threshold; 203,043 assignments across 87k posts (completed 2026-04-24)
- [x] Saved MiniLM embeddings to `data/processed/embeddings.npy` for later vector search (completed 2026-04-24)
- [x] Parquet exports + `summary.md` + `sources.md` provenance doc (completed 2026-04-24)
