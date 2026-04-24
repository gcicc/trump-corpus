"""Multi-label topic assignment for the Trump corpus.

Approach:
- 18 **curated themes** (see THEMES below). Each theme has a set of "anchor"
  phrases — short sentences that exemplify what posts on that theme look like.
- We embed every post and every anchor with a sentence-transformer (local,
  no API). Each theme's centroid is the mean of its anchor embeddings.
- For each post, compute cosine similarity to every centroid. Take top-3
  themes whose similarity exceeds a threshold; one theme per post at minimum
  (fall back to `general` if nothing clears the bar).
- Nicknames themes are handled specially: regex hits from `nicknames.py`
  directly force inclusion of `nicknames-bad` and/or `nicknames-good`.
- BERTopic is run separately (optional, for later "find similar" UX) — we
  save its cluster labels + exemplars to `topic_clusters` table. Not required
  for the curated assignment.

Output tables:
  post_themes(post_id, theme, score, rank)   -- 1..3 rows per post
  theme_catalog(theme, label, description, color)

A post's primary topic = rank=1 row.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from . import nicknames

# ---------- Theme catalog ----------

@dataclass(frozen=True)
class Theme:
    slug: str
    label: str
    description: str
    color: str  # hex, presidential palette — muted, WCAG-AA vs cream #F4ECD8
    anchors: tuple[str, ...]


THEMES: tuple[Theme, ...] = (
    Theme(
        "economy", "Economy & Stock Market",
        "Markets, GDP, the Dow, Fed policy, inflation, economic growth.",
        "#2E6F40",
        (
            "The stock market is at an all-time high, the economy is booming.",
            "The Dow hit a record again today, best economy in history.",
            "GDP growth is the strongest we have ever seen.",
            "Jerome Powell and the Fed are killing our economy with high interest rates.",
            "Inflation is destroying the middle class.",
            "Record low unemployment for African Americans and Hispanic Americans.",
        ),
    ),
    Theme(
        "border", "Border & Immigration",
        "The wall, caravans, asylum, ICE, sanctuary cities, illegal immigration.",
        "#8C5E2A",
        (
            "We must build the wall to stop illegal immigration.",
            "The caravan is heading to our border, do not let them in.",
            "Catch and release must end. Send them back.",
            "Sanctuary cities are a disgrace and harbor criminals.",
            "ICE is doing a great job, tremendous respect.",
            "Biden opened our border to millions of illegals, a disaster.",
        ),
    ),
    Theme(
        "media", "Media",
        "Fake news, specific networks/reporters, press, enemy of the people.",
        "#3F5F7F",
        (
            "The Failing New York Times is fake news.",
            "CNN is the enemy of the people.",
            "MSNBC ratings are in free fall, fake news.",
            "The Lamestream Media will not report the truth.",
            "Fox News has gone to the dark side.",
            "The corrupt media never apologizes for their lies.",
        ),
    ),
    Theme(
        "elections", "Elections & Voting",
        "Campaigns, polling, voter fraud, mail-in ballots, election integrity.",
        "#6B3F72",
        (
            "The 2020 election was rigged and stolen from us.",
            "Mail-in ballots are a recipe for fraud.",
            "The polls are looking fantastic, we are winning big.",
            "Voter ID is common sense. Dead people should not vote.",
            "We need paper ballots, voter ID, and one-day voting.",
            "The Fake Polls are a disgrace, totally rigged.",
        ),
    ),
    Theme(
        "china", "China",
        "Xi, trade war, tariffs on China, COVID origins, Chinese currency.",
        "#A63D2A",
        (
            "China is ripping us off and we are fighting back with tariffs.",
            "President Xi is a friend but China has taken advantage for decades.",
            "The China virus was unleashed on the world.",
            "We will not let China win, the trade deal is great.",
            "China is paying billions in tariffs into our Treasury.",
        ),
    ),
    Theme(
        "military", "Military & Veterans",
        "Troops, generals, VA, military parades, defense spending.",
        "#4A5C3A",
        (
            "Our great military is the best equipped in the world.",
            "We are rebuilding our military, forty billion dollars.",
            "Our Vets deserve the best care and we are giving it to them.",
            "Choice for our veterans, they can see any doctor they want.",
            "Generals Mattis, Kelly, McMaster, tremendous warriors.",
        ),
    ),
    Theme(
        "energy", "Energy",
        "Oil, drilling, pipelines, coal, Green New Deal, gas prices.",
        "#B08030",
        (
            "Drill baby drill, energy independence is essential.",
            "The Green New Deal will destroy our country.",
            "Keystone XL pipeline approved, thousands of jobs.",
            "Clean coal is back, miners are going back to work.",
            "Gas prices are too high because of Biden's war on oil.",
        ),
    ),
    Theme(
        "courts", "Courts, Judges & Legal Cases",
        "Supreme Court, Mueller, impeachment, indictments, witch hunt.",
        "#5D3A5D",
        (
            "No collusion, no obstruction, total witch hunt.",
            "The Mueller report exonerated me completely.",
            "Another Deranged Jack Smith indictment, election interference.",
            "The Supreme Court ruled in my favor, total vindication.",
            "My judges are constitutionalists, the greatest appointments.",
            "Appeal the verdict, rigged case, no crime committed.",
        ),
    ),
    Theme(
        "jobs", "Jobs & Manufacturing",
        "Factory openings, jobs numbers, USMCA, American workers.",
        "#2F5F5F",
        (
            "Record jobs report, unemployment at fifty year low.",
            "Ford is bringing jobs back from Mexico, great news.",
            "American workers are finally winning again.",
            "USMCA is signed, the best trade deal ever for farmers and workers.",
            "Manufacturing is roaring back, three million jobs added.",
        ),
    ),
    Theme(
        "crime", "Crime & Law Enforcement",
        "Police, violence, gangs, chaos in Democrat cities, law and order.",
        "#7A3030",
        (
            "Law and order must be restored to our streets.",
            "Crime in Chicago is out of control, a disaster.",
            "MS-13 is a vicious gang, we are rounding them up.",
            "Our police are heroes, I back the blue.",
            "Democrat-run cities are crime-ridden hellholes.",
        ),
    ),
    Theme(
        "covid", "COVID / Health",
        "Pandemic, vaccines, Operation Warp Speed, Fauci, lockdowns.",
        "#4B6A88",
        (
            "Operation Warp Speed delivered vaccines in record time.",
            "Dr Fauci has been wrong on almost everything.",
            "We will defeat the invisible enemy, the Chinese virus.",
            "Reopen our country, the cure cannot be worse than the disease.",
            "Hydroxychloroquine shows promise, be smart.",
        ),
    ),
    Theme(
        "trade", "Trade & Tariffs",
        "Tariffs (beyond China), NAFTA, trade imbalances, WTO.",
        "#997A2E",
        (
            "Tariffs are making our country rich again.",
            "NAFTA was the worst trade deal ever signed.",
            "EU treats us very unfairly on trade, tariffs coming.",
            "Tariffs are a beautiful thing for American workers.",
            "Trade imbalances with Germany and Japan are a disgrace.",
        ),
    ),
    Theme(
        "foreign_policy", "Foreign Policy",
        "Russia, Ukraine, Israel, NATO, Iran, North Korea.",
        "#415B6F",
        (
            "NATO allies must pay their fair share, not the US.",
            "Israel is our greatest ally in the Middle East.",
            "The Iran deal was terrible, I canceled it.",
            "Russia and Ukraine need to make a deal, stop the killing.",
            "Abraham Accords, historic peace in the Middle East.",
        ),
    ),
    Theme(
        "personal_family", "Personal & Family",
        "Melania, Ivanka, Don Jr., Eric, Barron, Tiffany, family moments.",
        "#6E4C7A",
        (
            "Melania is doing an incredible job as First Lady.",
            "So proud of Ivanka and her work on women's empowerment.",
            "Don Jr. and Eric are running the business beautifully.",
            "Happy birthday to my beautiful wife Melania.",
            "Barron is doing great, so tall already.",
            "Tiffany just graduated, we are so proud.",
        ),
    ),
    Theme(
        "nicknames_bad", "Bad Nicknames",
        "Pejorative nicknames: Crooked Hillary, Sleepy Joe, Little Marco, etc.",
        "#8B1E3F",
        (
            "Crooked Hillary is a disaster for our country.",
            "Sleepy Joe Biden has no idea what he is doing.",
            "Cryin Chuck Schumer is an embarrassment.",
            "Shifty Schiff made up a fake transcript.",
            "Pocahontas is a total fraud.",
            "Lyin Ted Cruz cannot be trusted.",
            "Little Marco is a low-energy lightweight.",
            "Birdbrain Nikki Haley has no chance.",
            "Deranged Jack Smith is a political hack.",
        ),
    ),
    Theme(
        "nicknames_good", "Good Nicknames",
        "Affectionate or positive nicknames for allies and family.",
        "#C9A961",
        (
            "My beautiful wife Melania is the best.",
            "My Pillow guy Mike Lindell is fantastic.",
            "Diamond and Silk are tremendous supporters.",
            "The forgotten men and women will not be forgotten.",
            "The silent majority is with us, big time.",
            "Great patriots stood up for our country.",
        ),
    ),
    Theme(
        "rallies", "Rallies & Campaign",
        "Rally crowds, campaign travel, MAGA movement, 2024/2016 runs.",
        "#8B5E2A",
        (
            "Huge crowd in Pennsylvania tonight, biggest ever.",
            "Make America Great Again, the movement continues.",
            "We will see you at the rally in Michigan on Saturday.",
            "Thousands outside, cannot fit inside, tremendous energy.",
            "America First, put our country first always.",
        ),
    ),
    Theme(
        "lifestyle", "Golf, Mar-a-Lago & Lifestyle",
        "Golf courses, Mar-a-Lago events, properties, Trump Tower, leisure.",
        "#5E7A4C",
        (
            "Beautiful day at Trump National Doral, perfect greens.",
            "Mar-a-Lago is hosting a tremendous event tonight.",
            "Trump Tower in Manhattan, an incredible property.",
            "Played a round of golf with Tiger Woods, great guy.",
            "Bedminster is looking fantastic, a true paradise.",
        ),
    ),
)

GENERAL_THEME = Theme(
    "general", "General / Uncategorized",
    "Posts that did not confidently match any curated theme.",
    "#6B6B6B",
    (),
)


def theme_by_slug(slug: str) -> Theme:
    for t in THEMES:
        if t.slug == slug:
            return t
    if slug == GENERAL_THEME.slug:
        return GENERAL_THEME
    raise KeyError(slug)


# ---------- Schema ----------

TOPIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS theme_catalog (
    slug        TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    description TEXT,
    color       TEXT,
    anchor_count INTEGER
);

CREATE TABLE IF NOT EXISTS post_themes (
    post_id  TEXT NOT NULL,
    theme    TEXT NOT NULL,
    score    REAL NOT NULL,
    rank     INTEGER NOT NULL,
    PRIMARY KEY (post_id, theme),
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
CREATE INDEX IF NOT EXISTS idx_post_themes_theme ON post_themes(theme);
CREATE INDEX IF NOT EXISTS idx_post_themes_post  ON post_themes(post_id);

CREATE TABLE IF NOT EXISTS post_nicknames (
    post_id   TEXT NOT NULL,
    surface   TEXT NOT NULL,    -- nickname as it appeared in the text
    target    TEXT NOT NULL,    -- who it refers to
    sentiment TEXT NOT NULL,    -- 'bad' | 'good'
    PRIMARY KEY (post_id, surface, target, sentiment)
);
CREATE INDEX IF NOT EXISTS idx_nicknames_target    ON post_nicknames(target);
CREATE INDEX IF NOT EXISTS idx_nicknames_sentiment ON post_nicknames(sentiment);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(TOPIC_SCHEMA)
    conn.commit()


def write_theme_catalog(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO theme_catalog(slug, label, description, color, anchor_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            label=excluded.label,
            description=excluded.description,
            color=excluded.color,
            anchor_count=excluded.anchor_count
        """,
        [
            (t.slug, t.label, t.description, t.color, len(t.anchors))
            for t in (*THEMES, GENERAL_THEME)
        ],
    )
    conn.commit()


# ---------- Embedding + assignment ----------

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _load_model(model_name: str = DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _theme_centroids(model) -> tuple[list[str], np.ndarray]:
    slugs: list[str] = []
    vectors: list[np.ndarray] = []
    for t in THEMES:
        embs = model.encode(list(t.anchors), convert_to_numpy=True, show_progress_bar=False)
        centroid = embs.mean(axis=0)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
        slugs.append(t.slug)
        vectors.append(centroid)
    return slugs, np.vstack(vectors)


def _iter_posts(conn: sqlite3.Connection, batch: int = 2048) -> Iterable[list[tuple[str, str]]]:
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM posts WHERE text IS NOT NULL AND length(text) > 0")
    buf: list[tuple[str, str]] = []
    for row in cur:
        buf.append((row[0], row[1]))
        if len(buf) >= batch:
            yield buf
            buf = []
    if buf:
        yield buf


def assign_multilabel(
    conn: sqlite3.Connection,
    *,
    top_k: int = 3,
    threshold: float = 0.25,
    model_name: str = DEFAULT_MODEL,
    embeddings_out: Path | None = None,
) -> dict:
    """Compute multi-label theme assignments and write post_themes.

    Returns summary stats.
    """
    init_schema(conn)
    write_theme_catalog(conn)

    print(f"  [topics] loading model: {model_name}")
    model = _load_model(model_name)

    print("  [topics] computing theme centroids")
    theme_slugs, theme_vecs = _theme_centroids(model)

    # Wipe prior assignments for a clean run (idempotent reassignment)
    conn.execute("DELETE FROM post_themes")
    conn.execute("DELETE FROM post_nicknames")
    conn.commit()

    total_posts = conn.execute("SELECT COUNT(*) FROM posts WHERE text IS NOT NULL").fetchone()[0]
    print(f"  [topics] embedding {total_posts} posts (batch=2048)")

    all_embeddings: list[np.ndarray] = []
    all_ids: list[str] = []

    per_theme_counts: dict[str, int] = {s: 0 for s in theme_slugs}
    per_theme_counts[GENERAL_THEME.slug] = 0
    processed = 0

    for batch in _iter_posts(conn, batch=2048):
        ids, texts = zip(*batch)
        embs = model.encode(
            list(texts),
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
            batch_size=128,
        )
        # cosine similarity = dot product of normalized vectors
        sims = embs @ theme_vecs.T  # (N, T)

        theme_rows: list[tuple[str, str, float, int]] = []
        nickname_rows: list[tuple[str, str, str, str]] = []

        for i, pid in enumerate(ids):
            row_sims = sims[i].copy()
            # Nickname forced inclusions (regex is definitive)
            nk_hits = nicknames.find_hits(texts[i])
            forced: set[str] = set()
            for surface, target, sentiment in nk_hits:
                nickname_rows.append((pid, surface, target, sentiment))
                forced.add("nicknames_bad" if sentiment == "bad" else "nicknames_good")

            # Rank top-k above threshold
            order = np.argsort(-row_sims)
            picked: list[tuple[str, float]] = []
            for idx in order:
                slug = theme_slugs[idx]
                s = float(row_sims[idx])
                if s < threshold and slug not in forced:
                    continue
                picked.append((slug, s))
                if len(picked) >= top_k:
                    break

            # Ensure forced themes are present
            picked_slugs = {s for s, _ in picked}
            for f in forced:
                if f not in picked_slugs:
                    # inject at the end with its actual similarity
                    f_idx = theme_slugs.index(f)
                    picked.append((f, float(row_sims[f_idx])))

            # Cap at top_k, keeping highest scorers
            picked.sort(key=lambda x: -x[1])
            picked = picked[:top_k]

            if not picked:
                picked = [(GENERAL_THEME.slug, 0.0)]

            for rank, (slug, score) in enumerate(picked, start=1):
                theme_rows.append((pid, slug, score, rank))
                per_theme_counts[slug] = per_theme_counts.get(slug, 0) + (1 if rank == 1 else 0)

        conn.executemany(
            "INSERT OR REPLACE INTO post_themes(post_id, theme, score, rank) VALUES (?, ?, ?, ?)",
            theme_rows,
        )
        if nickname_rows:
            conn.executemany(
                """
                INSERT OR IGNORE INTO post_nicknames(post_id, surface, target, sentiment)
                VALUES (?, ?, ?, ?)
                """,
                nickname_rows,
            )
        conn.commit()

        if embeddings_out is not None:
            all_embeddings.append(embs)
            all_ids.extend(ids)

        processed += len(batch)
        if processed % 8192 == 0 or processed == total_posts:
            print(f"  [topics] embedded {processed}/{total_posts}")

    if embeddings_out is not None and all_embeddings:
        embeddings_out.parent.mkdir(parents=True, exist_ok=True)
        np.save(embeddings_out, np.vstack(all_embeddings))
        (embeddings_out.with_suffix(".ids.txt")).write_text(
            "\n".join(all_ids), encoding="utf-8"
        )
        print(f"  [topics] wrote embeddings -> {embeddings_out}")

    # Summary
    primary_counts = dict(
        conn.execute(
            "SELECT theme, COUNT(*) FROM post_themes WHERE rank=1 GROUP BY theme ORDER BY 2 DESC"
        ).fetchall()
    )
    return {"total": total_posts, "primary_counts": primary_counts}
