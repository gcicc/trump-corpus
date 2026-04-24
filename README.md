# trump-corpus

Unified, text-minable corpus of Donald Trump's public messaging for
sentiment / topic / timeline / style analysis.

## What's inside

- **87,146 social posts**
  - `@realDonaldTrump` Twitter, 2009-05 → 2021-01 (54,306, incl. later-deleted)
  - `@realDonaldTrump` Truth Social, 2022-02 → present (32,789, auto-refreshing upstream)
  - `@POTUS45` official-capacity, 2017-2022 (51 — partial, Wayback-hydrated)
- **884 speeches / statements / executive orders / proclamations**
  - UCSB American Presidency Project (871)
  - ryanmcdermott early-campaign speeches (9)
  - Miller Center (4, degraded scraper)
- **18 curated themes** with multi-label assignment (up to 3 themes per post)
  including separate "Bad Nicknames" and "Good Nicknames" bins.
- **6,648 nickname mentions** mapped to specific targets + sentiment.

See `data/processed/summary.md` for the live snapshot.
See `data/sources.md` for provenance, known gaps, and citation guidance.

## Storage

- `data/processed/corpus.sqlite` — canonical store. Tables: `posts`,
  `speeches`, `sources`, `theme_catalog`, `post_themes`, `post_nicknames`.
- `data/processed/*.parquet` — analytic exports (regenerate any time).
- `data/processed/embeddings.npy` — normalized MiniLM embeddings of all posts,
  for vector search / find-similar (87,146 × 384 floats).
- `data/raw/` — original downloaded artifacts. Never mutated.

## Schema at a glance

```
posts(id, platform, account, timestamp_utc, text, is_repost, is_reply,
      reply_to, media_urls_json, source_url, metrics_json, raw_json, ingested_at)

speeches(id, event_date, event_type, title, location, text,
         source, source_url, ingested_at)

theme_catalog(slug, label, description, color, anchor_count)

post_themes(post_id, theme, score, rank)      -- 1..3 rows per post
post_nicknames(post_id, surface, target, sentiment)
sources(source_id, name, url, last_fetched, record_count, sha256, notes)
```

A post's **primary theme** = `post_themes.rank = 1`.

## Setup

```bash
# venv lives outside Dropbox (Windows file-lock workaround)
python -m venv C:\Users\gcicc\.venvs\trump-corpus
C:\Users\gcicc\.venvs\trump-corpus\Scripts\python.exe -m pip install -e .
```

## Build (one-shot)

```bash
python scripts/build_corpus.py              # pull all sources
python scripts/build_topics.py              # assign themes + nicknames
python scripts/export_parquet.py            # regenerate parquet
python scripts/generate_summary.py          # regenerate summary.md
```

Total session time with in-session caps: ~25 min (mostly UCSB scraping and
topic embedding).

## Quarterly refresh

```bash
python scripts/refresh.py                   # re-runs all fetchers (upserts)
python scripts/build_topics.py              # re-assigns themes
python scripts/export_parquet.py
python scripts/generate_summary.py
```

For a **deep** refresh that catches up on the @POTUS45 / @WhiteHouse45 gap,
raise the Wayback hydration cap in `potus_wayback.ingest(hydrate_cap=...)`
and run overnight — ~1300 POTUS45 captures and ~18k WhiteHouse45 captures
exist upstream; each capture takes 6-12 sec to hydrate.

## Topic taxonomy (18 themes)

Colors are from the presidential palette (see `topics.py`).

```
economy, border, media, elections, china, military, energy, courts, jobs,
crime, covid, trade, foreign_policy, personal_family,
nicknames_bad, nicknames_good,
rallies, lifestyle
+ general (catch-all for low-confidence posts)
```

Multi-label: each post gets its top 3 matching themes above a cosine-similarity
threshold (0.25). Nickname regex hits force inclusion of `nicknames_bad` /
`nicknames_good` regardless of embedding similarity, so "Sleepy Joe" always
ends up under Bad Nicknames even if the sentence is otherwise about jobs.

## Known gaps (see data/sources.md)

- **@POTUS45 / @WhiteHouse45**: only 51 tweets so far (session cap). Full
  Wayback hydration is a quarterly overnight job.
- **@realDonaldTrump post-2022 X**: nitter mirrors returned 0 at build time.
  Account is mostly dormant; retry next refresh.
- **Miller Center speeches**: JS-rendered index limits scraping. Using UCSB
  as the primary speeches source instead.

## Coming next (tracked in ACTION-ITEMS.md)

Quarto-rendered site for a family reader, with two-axis browsing
(year/month/day × topic), presidential styling, Trump-voice read-aloud
(local XTTS-v2), and a dads80th-style rally map. See
`C:\Users\gcicc\.claude\plans\swirling-zooming-hammock.md` for the approved
plan.
