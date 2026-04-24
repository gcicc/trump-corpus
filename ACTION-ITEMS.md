# Action Items — trump-corpus

**Last updated:** 2026-04-24

## Live
- Site: https://gcicc.github.io/trump-corpus/
- Repo: https://github.com/gcicc/trump-corpus

## Blockers (human-only)
- None

## To Do
- [ ] Overnight: render top-500 Trump-voice MP3s (`python scripts/render_voice.py --n 500`) — currently partial (~95 queued, running when session closed)
- [ ] Overnight: bump Wayback hydration cap for POTUS45 / WhiteHouse45 (~19k captures remain)
- [ ] Fetch hero background photos from whitehouse.gov (Oval Office, Rose Garden) — public domain US government works
- [ ] Wire client-side vector search ("find similar posts") using existing `data/processed/embeddings.npy`
- [ ] Add year-range slider + keyword search on theme pages
- [ ] Retry nitter scrape for post-2022 @realDonaldTrump (mirrors were 0 at build time)
- [ ] Consider fetching `@POTUS` (current admin) tweets via Wayback for the 2025+ era
- [ ] Scrape ryanmcdermott + Miller Center alternative sources for missing pre-2015 speeches
- [ ] BERTopic discovery pass for "you might also like" carousel
- [ ] Add sitemap.xml pings and og:image previews to each page
- [ ] Consider a `/search` page with faceted filter (topic × year × platform × keyword)

## Done (this session, 2026-04-24)
- [x] Scaffolded project: pyproject, SQLite/Parquet, venv outside Dropbox
- [x] Ingested 54,306 @realDonaldTrump tweets (2009-2021)
- [x] Ingested 32,789 Truth Social posts (2022-present)
- [x] Wayback CDX hydration of 51 POTUS45 tweets (session cap)
- [x] UCSB American Presidency scraper: 871 speeches/statements/EOs
- [x] BERTopic + sentence-transformers installed
- [x] 18-theme curated taxonomy with Good/Bad Nicknames bins
- [x] 60+ nickname regex patterns across 40+ targets
- [x] Multi-label topic assignment (203k assignments, 6,648 nickname hits)
- [x] Saved MiniLM embeddings to data/processed/embeddings.npy
- [x] Parquet exports + summary.md + sources.md
- [x] Initial GitHub push (main)
- [x] Quarto site scaffold (presidential palette, 18 theme pages, 18 year pages)
- [x] 18 year-portraits fetched from Wikimedia Commons (PD only)
- [x] 538 rally stops scraped + geocoded from 4 Wikipedia lists
- [x] dads80th-style map with era-colored markers + Play Journey animation
- [x] Coqui XTTS-v2 installed (dedicated Python 3.11 venv)
- [x] 18-second Trump reference clip from 2017 inaugural (public domain)
- [x] Voice rendering pipeline end-to-end (WAV → MP3 via ffmpeg)
- [x] Browser TTS fallback for posts lacking a clone
- [x] gh-pages branch + GitHub Pages enabled → site live
