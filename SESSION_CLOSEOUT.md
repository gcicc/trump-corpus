# Session Closeout — trump-corpus (Phase 1 + Phase 2)

**Date:** 2026-04-24
**Duration:** ~5 hours (scaffold + corpus + topics + site + map + voice + publish)

## Live URLs

- **Site:** https://gcicc.github.io/trump-corpus/
- **Source:** https://github.com/gcicc/trump-corpus

## Accomplished

### Phase 1 — Corpus
- **87,146 posts** ingested (Twitter 2009-2021: 54,306; Truth Social 2022→present: 32,789; POTUS45 partial: 51)
- **884 speeches** (UCSB American Presidency: 871; Miller Center + ryanmcdermott: 13)
- **18 curated themes** with multi-label assignment, including separate Good/Bad Nicknames bins covering 40+ targets
- **203,043 theme assignments** + **6,648 nickname mentions**
- MiniLM embeddings saved for later "find similar"
- Provenance + known gaps fully documented

### Phase 2 — Site
- **Quarto website** with presidential palette (navy/gold/cream)
- **18 per-topic pages** (color-coded, volume charts, top posts, recurring phrases)
- **18 per-year pages** (month-volume charts, post stream with period-appropriate portrait)
- **538-stop rally map** scraped from 4 Wikipedia rally lists + 5 home-base anchors (Trump Tower, White House, Mar-a-Lago, Bedminster), era-colored Leaflet pattern ported from dads80th
- **18 year-portraits** sourced from Wikimedia Commons (public domain only) with fallback-crops for years lacking PD photos
- **Sticky filter bar** per year page — click-to-solo, shift-click to hide topics
- **About page** with data provenance, AI-voice disclosure, and credits

### Phase 2 — Voice
- **Coqui XTTS-v2** installed in dedicated Python 3.11 venv
- **18-second reference clip** extracted from Trump's 2017 inaugural (public domain, US government work)
- **render_voice.py** batch renderer
- **~16+ posts pre-rendered** (background render continuing; will reach ~95 when complete)
- **Browser TTS fallback** for posts without a Trump clone

### Deployment
- Initial commit + Phase 2 commit pushed to `main`
- `gh-pages` branch created and populated with rendered site
- GitHub Pages enabled; site live with HTTPS

## Outstanding (next session)

- **Full-corpus voice render** — currently running in background (~95 posts). For coverage of the "top 500" eager pool, raise `--n 500` and run overnight (estimated 7-10 hrs on CPU).
- **@POTUS45 / @WhiteHouse45 Wayback hydration** — only 51/19,000 hydrated. Bump `hydrate_cap` in `potus_wayback.ingest` and run overnight.
- **Post-2022 @realDonaldTrump X** — nitter mirrors all 0 at build time; retry next quarter.
- **Background imagery** — hero backgrounds (Oval Office, Rose Garden) from whitehouse.gov not yet sourced; using solid navy gradient as placeholder.
- **Per-post vector search UI** — embeddings.npy exists; client-side cosine-similarity "find similar posts" UI not yet wired.
- **Filter bar on theme pages** — currently only year pages have it; theme pages could get a year-range slider.

## Next Action

Run an overnight voice render (`--n 500` + large Wayback hydration). Then rebuild site + republish.

## Blockers

- None. Everything below is opportunistic enhancement.

## Portfolio context

- `dads80th` Leaflet pattern adapted directly into `site/includes/trumpmap.html` — good pattern for future location-based projects.
- `sentence-transformers` + anchor-based multi-label is fully reusable for other topic-modeling projects that want curated taxonomy over unsupervised BERTopic output.
- Coqui XTTS-v2 Python 3.11 venv recipe is reusable for any local voice-cloning workflow.

## Refresh cadence

Quarterly. Run `scripts/refresh.py` → `scripts/build_topics.py` → `scripts/build_site.py` → `scripts/render_voice.py` → `quarto publish gh-pages`.
