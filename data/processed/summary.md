# Trump Corpus — Summary

*Generated 2026-04-24T13:57:56+00:00*

## Totals

- **Posts:** 87,146
- **Speeches/transcripts:** 884

## Posts by platform and account

| Platform | Account | Count | Earliest | Latest |
|---|---|---:|---|---|
| truth_social | realDonaldTrump | 32,789 | 2022-02-14 | 2026-04-24 |
| twitter | POTUS45 | 51 | 2017-02-01 | 2022-04-28 |
| twitter | realDonaldTrump | 54,306 | 2009-05-04 | 2021-01-08 |

## Posts by year

| Year | Count |
|---|---:|
| 2009 | 56 |
| 2010 | 143 |
| 2011 | 869 |
| 2012 | 4,193 |
| 2013 | 8,199 |
| 2014 | 6,001 |
| 2015 | 7,707 |
| 2016 | 3,943 |
| 2017 | 2,572 |
| 2018 | 3,563 |
| 2019 | 7,246 |
| 2020 | 9,674 |
| 2021 | 181 |
| 2022 | 3,899 |
| 2023 | 9,905 |
| 2024 | 10,587 |
| 2025 | 6,229 |
| 2026 | 2,179 |

## Sources

| Source | Records | Last fetched | Notes |
|---|---:|---|---|
| `hershey_twitter_archive` | 54,316 | 2026-04-24 | @realDonaldTrump 2009-05-04 to 2021-01-08. Includes later-deleted tweets. |
| `cnn_truth_social_archive` | 32,789 | 2026-04-24 | Feb 2022 → present. Updated every ~5 min. HTML in content field stripped. |
| `ucsb_american_presidency` | 871 | 2026-04-24 | Indexed 900 doc links across 9 max pages; ingested 871. |
| `wayback_potus_whitehouse` | 51 | 2026-04-24 | POTUS45: 1300 captures -> 851 unique tweets | POTUS45: hydrated 51 / net-fetched 100 / skipped 350 | WhiteHouse45: CD... |
| `ryanmcdermott_speeches` | 9 | 2026-04-24 | Early-campaign speech snippets. No dates attached. |
| `miller_center` | 4 | 2026-04-24 | Formal presidential addresses. Scraped from index + transcript pages. |
| `potus_whitehouse_gap` | 0 | 2026-04-24 | Official-capacity accounts archived by NARA but no bulk export. Path forward options: (a) Wayback CDX scrape of twitt... |
| `nitter_realdonaldtrump_post2022` | 0 | 2026-04-24 | No working nitter mirror found at scrape time. |

## Theme distribution (primary label)

| Theme | Posts | Share |
|---|---:|---:|
| Bad Nicknames | 15,262 | 18.8% |
| Personal & Family | 11,388 | 14.0% |
| General / Uncategorized | 9,727 | 12.0% |
| Media | 7,494 | 9.2% |
| Rallies & Campaign | 5,843 | 7.2% |
| Golf, Mar-a-Lago & Lifestyle | 5,837 | 7.2% |
| Courts, Judges & Legal Cases | 5,154 | 6.3% |
| Elections & Voting | 4,000 | 4.9% |
| Border & Immigration | 2,382 | 2.9% |
| Foreign Policy | 2,108 | 2.6% |
| Economy & Stock Market | 1,994 | 2.5% |
| Crime & Law Enforcement | 1,664 | 2.0% |
| Jobs & Manufacturing | 1,620 | 2.0% |
| Military & Veterans | 1,504 | 1.9% |
| Energy | 1,433 | 1.8% |
| COVID / Health | 1,257 | 1.5% |
| China | 1,136 | 1.4% |
| Trade & Tariffs | 810 | 1.0% |
| Good Nicknames | 587 | 0.7% |

Average themes per post (multi-label): **2.50**

## Nicknames — top 20 targets

| Target | Sentiment | Posts |
|---|---|---:|
| MAGA | good | 1,920 |
| Media | bad | 1,037 |
| Joe Biden | bad | 1,003 |
| Progressives | bad | 900 |
| Establishment Republicans | bad | 308 |
| Hillary Clinton | bad | 294 |
| Democratic Party | bad | 175 |
| Ron DeSantis | bad | 156 |
| Jack Smith | bad | 144 |
| Kamala Harris | bad | 123 |
| Nancy Pelosi | bad | 87 |
| Nikki Haley | bad | 60 |
| supporters | good | 60 |
| Letitia James | bad | 59 |
| Michael Bloomberg | bad | 46 |
| Elizabeth Warren | bad | 44 |
| Trump base | good | 30 |
| Chris Christie | bad | 29 |
| Adam Schiff | bad | 28 |
| Bernie Sanders | bad | 28 |

## Schema

Key tables:

- `posts(id, platform, account, timestamp_utc, text, is_repost, is_reply, reply_to, media_urls_json, source_url, metrics_json, raw_json, ingested_at)`
- `speeches(id, event_date, event_type, title, location, text, source, source_url, ingested_at)`
- `sources(source_id, name, url, last_fetched, record_count, sha256, notes)`
- `theme_catalog(slug, label, description, color, anchor_count)`
- `post_themes(post_id, theme, score, rank)`  — 1..3 rows per post
- `post_nicknames(post_id, surface, target, sentiment)`

Parquet exports (regenerate with `python scripts/export_parquet.py`):
`posts.parquet`, `speeches.parquet`, `sources.parquet`.
