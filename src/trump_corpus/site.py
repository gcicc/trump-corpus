"""Generate the Quarto site's data-driven pages from SQLite.

Writes:
  site/_themes_grid.qmd         -- cards linking to every theme page
  site/_timeline_ribbon.qmd     -- year ribbon for timeline.qmd
  site/_timeline_volume.qmd     -- year-by-year volume chart
  site/themes/<slug>.qmd        -- per-theme feed + stats
  site/timeline/<year>.qmd      -- per-year monthly drill-down
  site/data/posts_index.json    -- compact lookup for JS search/filter
  site/data/topics.json         -- theme palette for JS
  site/data/audio_manifest.json -- which posts have pre-rendered audio (stub)

All pages are self-contained HTML snippets so the Quarto output is static.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .topics import GENERAL_THEME, THEMES, Theme, theme_by_slug

SITE_DIR = Path(__file__).resolve().parents[2] / "site"

# ---------- helpers ----------


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _fmt_ts(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y  %H:%M")
    except Exception:  # noqa: BLE001
        return iso[:16]


def _platform_label(platform: str) -> str:
    return {"twitter": "Twitter", "truth_social": "Truth Social"}.get(platform, platform)


def _post_card_html(
    post: dict,
    primary_theme: str,
    secondary_themes: list[tuple[str, float]],
    *,
    with_avatar_year: int | None = None,
) -> str:
    t = theme_by_slug(primary_theme)
    text = _esc(post["text"])
    ts = _fmt_ts(post.get("timestamp_utc"))
    handle = _esc(post.get("account") or "")
    platform = _platform_label(post.get("platform") or "")
    url = post.get("source_url") or ""

    chips = []
    for slug, _score in secondary_themes:
        try:
            th = theme_by_slug(slug)
        except KeyError:
            continue
        chips.append(
            f'<span class="chip" style="--chip-color: {th.color}">{_esc(th.label)}</span>'
        )
    chip_html = f'<div class="chips">{"".join(chips)}</div>' if chips else ""

    avatar_html = ""
    if with_avatar_year is not None:
        avatar_html = (
            f'<div class="avatar" '
            f'style="background-image:url(../assets/avatars/{with_avatar_year}.jpg)"></div>'
        )

    audio_btn = (
        f'<button class="read-aloud" data-post-id="{_esc(post["id"])}" disabled>'
        f'Read aloud</button>'
    )

    permalink = f'<a href="{_esc(url)}" target="_blank" rel="noopener">permalink</a>' if url else ""

    return f"""
<article class="post-card" style="--theme-color: {t.color}" data-theme="{primary_theme}" data-year="{(post.get("timestamp_utc") or "")[:4]}">
  {avatar_html}
  <div class="meta">
    <span><span class="handle">@{handle}</span> &middot; {ts}</span>
    <span class="platform">{platform}</span>
  </div>
  <div class="text">{text}</div>
  {chip_html}
  <div class="meta" style="margin-top:0.5em;">
    <span>{audio_btn}</span>
    <span>{permalink}</span>
  </div>
</article>
"""


# ---------- data loaders ----------


def _load_posts_by_theme(
    conn: sqlite3.Connection, theme: str, limit: int = 20
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.id, p.platform, p.account, p.timestamp_utc, p.text, p.source_url,
               pt.score
          FROM post_themes pt
          JOIN posts p ON p.id = pt.post_id
         WHERE pt.theme = ? AND pt.rank = 1
         ORDER BY pt.score DESC
         LIMIT ?
        """,
        (theme, limit),
    ).fetchall()
    cols = ["id", "platform", "account", "timestamp_utc", "text", "source_url", "score"]
    return [dict(zip(cols, r)) for r in rows]


def _all_themes_for_post(conn: sqlite3.Connection, post_ids: list[str]) -> dict[str, list[tuple[str, float]]]:
    """Return {post_id: [(theme, score), ...] sorted by rank}."""
    if not post_ids:
        return {}
    placeholders = ",".join(["?"] * len(post_ids))
    rows = conn.execute(
        f"""
        SELECT post_id, theme, score, rank
          FROM post_themes
         WHERE post_id IN ({placeholders})
         ORDER BY post_id, rank
        """,
        post_ids,
    ).fetchall()
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for pid, theme, score, _rank in rows:
        out[pid].append((theme, score))
    return out


def _theme_volume_by_year(conn: sqlite3.Connection, theme: str) -> list[tuple[str, int]]:
    return conn.execute(
        """
        SELECT substr(p.timestamp_utc, 1, 4) y, COUNT(*) c
          FROM post_themes pt
          JOIN posts p ON p.id = pt.post_id
         WHERE pt.theme = ? AND pt.rank = 1 AND p.timestamp_utc IS NOT NULL
         GROUP BY y ORDER BY y
        """,
        (theme,),
    ).fetchall()


def _theme_top_phrases(conn: sqlite3.Connection, theme: str, n: int = 20) -> list[tuple[str, int]]:
    """Cheap top-phrase extraction: counts of bigrams in posts with this primary theme.

    Deliberately simple: lowercases, strips punctuation, drops ultra-common bigrams.
    """
    import re

    rows = conn.execute(
        """
        SELECT p.text FROM post_themes pt
          JOIN posts p ON p.id = pt.post_id
         WHERE pt.theme = ? AND pt.rank = 1
         LIMIT 5000
        """,
        (theme,),
    ).fetchall()

    stop = set(
        "the a an and or but if then so of in on at to for from by with as is are was were be been being have has had do does did this that these those i you he she we they me him her us them my your his our their its it not no yes very just also into about over under".split()
    )
    counter: Counter[str] = Counter()
    word_re = re.compile(r"[a-zA-Z][a-zA-Z']+")
    for (text,) in rows:
        words = [w.lower() for w in word_re.findall(text or "") if w.lower() not in stop and len(w) > 2]
        for a, b in zip(words, words[1:]):
            counter[f"{a} {b}"] += 1
    return counter.most_common(n)


# ---------- renderers ----------


def render_themes_grid(conn: sqlite3.Connection) -> None:
    counts = dict(
        conn.execute(
            "SELECT theme, COUNT(*) FROM post_themes WHERE rank=1 GROUP BY theme"
        ).fetchall()
    )

    parts = ['<div class="theme-grid">']
    for t in THEMES:
        n = counts.get(t.slug, 0)
        parts.append(
            f"""
<a class="theme-card" href="themes/{t.slug}.html" style="--theme-color: {t.color}">
  <h3>{_esc(t.label)}</h3>
  <div class="n">{n:,} posts</div>
  <div class="desc">{_esc(t.description)}</div>
</a>
"""
        )
    parts.append("</div>")

    # Also include general bucket + stats
    n_general = counts.get(GENERAL_THEME.slug, 0)
    total = sum(counts.values())
    parts.append(
        f'<p class="muted">Uncategorized: {n_general:,} posts. Total assigned: {total:,}.</p>'
    )

    (SITE_DIR / "_themes_grid.qmd").write_text("\n".join(parts), encoding="utf-8")


def render_theme_page(conn: sqlite3.Connection, theme: Theme, limit: int = 40) -> None:
    posts = _load_posts_by_theme(conn, theme.slug, limit=limit)
    post_ids = [p["id"] for p in posts]
    theme_map = _all_themes_for_post(conn, post_ids)

    volume = _theme_volume_by_year(conn, theme.slug)
    top_phrases = _theme_top_phrases(conn, theme.slug)
    total = conn.execute(
        "SELECT COUNT(*) FROM post_themes WHERE theme=? AND rank=1", (theme.slug,)
    ).fetchone()[0]

    cards_html = []
    for p in posts:
        all_themes = theme_map.get(p["id"], [])
        secondary = [(s, sc) for (s, sc) in all_themes if s != theme.slug][:2]
        year = int(p["timestamp_utc"][:4]) if p.get("timestamp_utc") else None
        cards_html.append(_post_card_html(p, theme.slug, secondary, with_avatar_year=year))

    # Plotly volume chart
    years = [y for y, _ in volume]
    counts = [c for _, c in volume]
    volume_html = f"""
<div id="theme-volume" class="volume-chart"></div>
<script>
  (function () {{
    var d = [{{ x: {json.dumps(years)}, y: {json.dumps(counts)},
                type: "bar", marker: {{ color: "{theme.color}" }} }}];
    var l = {{
      margin: {{ t: 10, r: 10, b: 35, l: 40 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: {{ tickfont: {{ family: "Libre Franklin" }} }},
      yaxis: {{ tickfont: {{ family: "Libre Franklin" }} }},
      height: 260, showlegend: false
    }};
    Plotly.newPlot("theme-volume", d, l, {{displayModeBar: false, responsive: true}});
  }})();
</script>
"""

    phrases_html = ""
    if top_phrases:
        phrases_html = (
            '<p class="small-caps">Recurring phrases</p>\n'
            + ", ".join(f"<span class='chip' style='--chip-color:{theme.color}'>{_esc(p)}</span>"
                        for p, _ in top_phrases[:15])
            + "\n"
        )

    body = f"""---
title: "{_esc(theme.label)}"
subtitle: "{total:,} posts where this was the primary topic."
---

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>

<style>
  h1 {{ border-bottom-color: {theme.color} !important; }}
</style>

{volume_html}

{phrases_html}

::: {{.muted}}
Showing the top {len(cards_html)} posts ranked by how clearly they match this theme. Other secondary themes for each post are shown as chips.
:::

<div class="post-stream">
{''.join(cards_html)}
</div>

::: {{.seal-divider}}
![](../assets/seal.svg){{width=60}}
:::

[← Back to all topics](../themes.qmd){{.small-caps}}
"""

    (SITE_DIR / "themes" / f"{theme.slug}.qmd").write_text(body, encoding="utf-8")


def render_timeline_ribbon(conn: sqlite3.Connection) -> None:
    years = [
        y for (y,) in conn.execute(
            "SELECT DISTINCT substr(timestamp_utc,1,4) y FROM posts WHERE timestamp_utc IS NOT NULL ORDER BY y"
        )
    ]
    parts = ['<div class="year-ribbon">']
    for y in years:
        parts.append(f'<a href="timeline/{y}.html">{y}</a>')
    parts.append("</div>")
    (SITE_DIR / "_timeline_ribbon.qmd").write_text("\n".join(parts), encoding="utf-8")


def render_timeline_volume(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT substr(timestamp_utc,1,4) y, COUNT(*) c
          FROM posts WHERE timestamp_utc IS NOT NULL GROUP BY y ORDER BY y
        """
    ).fetchall()
    years = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    html_ = f"""
<div id="timeline-volume" class="volume-chart"></div>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
  (function () {{
    var d = [{{ x: {json.dumps(years)}, y: {json.dumps(counts)},
                type: "bar", marker: {{ color: "#0A2540" }} }}];
    var l = {{
      margin: {{ t: 10, r: 10, b: 35, l: 50 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      title: {{ text: "Posts per year", font: {{ family: "Libre Franklin", size: 14 }} }},
      height: 300, showlegend: false
    }};
    Plotly.newPlot("timeline-volume", d, l, {{displayModeBar: false, responsive: true}});
  }})();
</script>
"""
    (SITE_DIR / "_timeline_volume.qmd").write_text(html_, encoding="utf-8")


def render_year_page(conn: sqlite3.Connection, year: str, limit: int = 300) -> None:
    rows = conn.execute(
        """
        SELECT p.id, p.platform, p.account, p.timestamp_utc, p.text, p.source_url
          FROM posts p
         WHERE substr(p.timestamp_utc,1,4) = ?
         ORDER BY p.timestamp_utc
         LIMIT ?
        """,
        (year, limit),
    ).fetchall()
    cols = ["id", "platform", "account", "timestamp_utc", "text", "source_url"]
    posts = [dict(zip(cols, r)) for r in rows]
    post_ids = [p["id"] for p in posts]
    theme_map = _all_themes_for_post(conn, post_ids)

    # Monthly counts
    month_rows = conn.execute(
        """
        SELECT substr(timestamp_utc, 1, 7) ym, COUNT(*)
          FROM posts WHERE substr(timestamp_utc,1,4) = ?
         GROUP BY ym ORDER BY ym
        """,
        (year,),
    ).fetchall()
    months = [r[0][5:] for r in month_rows]
    mcounts = [r[1] for r in month_rows]

    cards_html = []
    for p in posts:
        themes_for_p = theme_map.get(p["id"], [])
        primary = themes_for_p[0][0] if themes_for_p else GENERAL_THEME.slug
        secondary = [(s, sc) for (s, sc) in themes_for_p[1:]][:2]
        cards_html.append(_post_card_html(p, primary, secondary, with_avatar_year=int(year)))

    total_year = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE substr(timestamp_utc,1,4) = ?", (year,)
    ).fetchone()[0]

    # Filter-bar chips: every theme present in this year
    present_themes = [
        t for (t,) in conn.execute(
            """
            SELECT DISTINCT pt.theme FROM post_themes pt
              JOIN posts p ON p.id = pt.post_id
             WHERE pt.rank = 1 AND substr(p.timestamp_utc,1,4) = ?
            """,
            (year,),
        )
    ]
    chip_html = []
    for slug in present_themes:
        try:
            t = theme_by_slug(slug)
        except KeyError:
            continue
        chip_html.append(
            f'<span class="chip on" style="--chip-color: {t.color}" data-theme="{slug}">{_esc(t.label)}</span>'
        )

    body = f"""---
title: "{year}"
subtitle: "{total_year:,} posts this year. Showing first {len(cards_html)}."
---

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>

<div id="year-months" class="volume-chart"></div>
<script>
  (function () {{
    var d = [{{ x: {json.dumps(months)}, y: {json.dumps(mcounts)},
                type: "bar", marker: {{ color: "#0A2540" }} }}];
    var l = {{
      margin: {{ t: 10, r: 10, b: 30, l: 40 }},
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      height: 210, showlegend: false
    }};
    Plotly.newPlot("year-months", d, l, {{displayModeBar: false, responsive: true}});
  }})();
</script>

<div class="filter-bar">
  <div class="chips">{' '.join(chip_html)}</div>
  <div class="actions">
    <a onclick="window.trumpFilter.solo()">Show all</a>
    <a onclick="window.trumpFilter.none()">Hide all</a>
    <span class="muted">click a chip to solo &middot; shift-click to hide</span>
  </div>
</div>

<div class="post-stream" id="stream-{year}">
{''.join(cards_html)}
</div>

<script src="../assets/filter.js"></script>

[← Back to all years](../timeline.qmd){{.small-caps}}
"""
    (SITE_DIR / "timeline" / f"{year}.qmd").write_text(body, encoding="utf-8")


def render_topics_json(conn: sqlite3.Connection) -> None:
    catalog = {
        t.slug: {"label": t.label, "color": t.color, "description": t.description}
        for t in THEMES
    }
    catalog[GENERAL_THEME.slug] = {
        "label": GENERAL_THEME.label,
        "color": GENERAL_THEME.color,
        "description": GENERAL_THEME.description,
    }
    (SITE_DIR / "data" / "topics.json").write_text(
        json.dumps(catalog, indent=2), encoding="utf-8"
    )


def render_audio_manifest_stub() -> None:
    path = SITE_DIR / "data" / "audio_manifest.json"
    if not path.exists():
        path.write_text(
            json.dumps({"schema": "post_id -> audio_url", "entries": {}}, indent=2),
            encoding="utf-8",
        )


def render_filter_js() -> None:
    """Client-side chip filter — solo a topic, shift-click to hide."""
    (SITE_DIR / "assets" / "filter.js").write_text(
        """
window.trumpFilter = (function () {
  function apply(hide) {
    document.querySelectorAll(".post-card").forEach(function (el) {
      var t = el.dataset.theme;
      el.style.display = hide.has(t) ? "none" : "";
    });
  }
  function refresh() {
    var chips = document.querySelectorAll(".filter-bar .chip");
    var hidden = new Set();
    chips.forEach(function (c) { if (!c.classList.contains("on")) hidden.add(c.dataset.theme); });
    apply(hidden);
  }
  document.addEventListener("click", function (e) {
    var chip = e.target.closest(".filter-bar .chip");
    if (!chip) return;
    e.preventDefault();
    if (e.shiftKey) {
      chip.classList.toggle("on");
    } else {
      // solo: turn all off, this one on (or if already solo, restore all)
      var chips = document.querySelectorAll(".filter-bar .chip");
      var soloing = Array.from(chips).every(function (c) {
        return c === chip ? c.classList.contains("on") : !c.classList.contains("on");
      });
      chips.forEach(function (c) {
        if (soloing) c.classList.add("on");
        else c.classList.toggle("on", c === chip);
      });
    }
    refresh();
  });
  return {
    solo: function () { document.querySelectorAll(".filter-bar .chip").forEach(function (c) { c.classList.add("on"); }); refresh(); },
    none: function () { document.querySelectorAll(".filter-bar .chip").forEach(function (c) { c.classList.remove("on"); }); refresh(); }
  };
})();
""".strip(),
        encoding="utf-8",
    )


def render_all(conn: sqlite3.Connection) -> None:
    (SITE_DIR / "themes").mkdir(exist_ok=True)
    (SITE_DIR / "timeline").mkdir(exist_ok=True)
    (SITE_DIR / "data").mkdir(exist_ok=True)

    render_themes_grid(conn)
    render_timeline_ribbon(conn)
    render_timeline_volume(conn)
    render_topics_json(conn)
    render_audio_manifest_stub()
    render_filter_js()

    for t in THEMES:
        render_theme_page(conn, t, limit=40)

    years = [
        y for (y,) in conn.execute(
            "SELECT DISTINCT substr(timestamp_utc,1,4) FROM posts WHERE timestamp_utc IS NOT NULL ORDER BY 1"
        )
    ]
    for y in years:
        render_year_page(conn, y, limit=300)
