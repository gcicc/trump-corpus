# Data Sources & Provenance

*Last regenerated: see `sources` table in `data/processed/corpus.sqlite`.*

| Source ID | Covers | Platform / Scope | Mutability | Notes |
|---|---|---|---|---|
| `hershey_twitter_archive` | `@realDonaldTrump` 2009-05-04 → 2021-01-08 | Twitter | Frozen | 54,316 tweets including later-deleted. From [MarkHershey/CompleteTrumpTweetsArchive](https://github.com/MarkHershey/CompleteTrumpTweetsArchive). Two CSVs (before-office, in-office). |
| `cnn_truth_social_archive` | `@realDonaldTrump` Truth Social, 2022-02 → now | Truth Social | Live (5-min cadence upstream) | 32,789+ posts. From [ix.cnn.io/data/truth-social/truth_archive.json](https://ix.cnn.io/data/truth-social/truth_archive.json) — CNN-hosted successor to the disabled [stiles/trump-truth-social-archive](https://github.com/stiles/trump-truth-social-archive). |
| `wayback_potus_whitehouse` | `@POTUS45` + `@WhiteHouse45`, 2017-01 → 2021-01 | Twitter (official) | Frozen | Best-effort hydration via Internet Archive Wayback CDX. Coverage is spotty; residual gap documented in the row's `notes` field. |
| `nitter_realdonaldtrump_post2022` | `@realDonaldTrump` 2022-11 → now | Twitter (reinstated) | Live | Mostly dormant account. Scraped via a rotating list of public nitter mirrors; mirror availability varies quarter to quarter. |
| `ucsb_american_presidency` | Trump speeches, remarks, statements, executive orders, proclamations | Speeches | Updating slowly | [UCSB American Presidency Project](https://www.presidency.ucsb.edu) — academic canonical source. |
| `ryanmcdermott_speeches` | Early-campaign speech snippets | Speeches | Frozen | [ryanmcdermott/trump-speeches](https://github.com/ryanmcdermott/trump-speeches). Small seed set; no dates attached. |
| `miller_center` | Presidential addresses | Speeches | Degraded | [Miller Center (UVA)](https://millercenter.org/the-presidency/presidential-speeches). JavaScript-rendered index limits scraping; only a handful of speeches extractable. |

## Known coverage gaps

- **Pre-Twitter statements** (press releases, interviews pre-2009): not in scope.
- **Private Trump Organization communications**: not in scope.
- **Physical rally transcripts before 2015**: partial only (via ryanmcdermott + UCSB).
- **@POTUS45 and @WhiteHouse45**: Wayback CDX captures a subset; images/video attachments are not recovered — text only.
- **Retweets & quote-tweets on Twitter pre-2021**: the Hershey archive is text-only — retweet context is not preserved.

## Refresh procedure (quarterly)

```bash
python scripts/refresh.py           # re-run all fetchers with upsert semantics
python scripts/build_topics.py       # re-assign themes to any new posts
```

The refresh logs a delta vs. the previous snapshot (posts added per source). If
an upstream source has gone dark (mirror died, repo deleted), the refresh logs
the failure in its row's `notes` field and does not drop existing data.

## How to cite

For academic or journalistic use, cite the underlying canonical source (the
Trump Twitter Archive, the CNN Truth Social mirror, UCSB, NARA, etc.) rather
than this derived corpus. This project is a convenience aggregation; it does
not originate any content.
