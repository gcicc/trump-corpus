"""Curated catalog of Donald Trump's nicknames.

Each entry: (pattern, target, sentiment) where
  pattern   is a regex matched case-insensitively against post text
  target    is the person/group the nickname refers to
  sentiment is 'bad' (pejorative) or 'good' (affectionate / positive)

This is intentionally conservative — we err on the side of precision over
recall. Weak matches (e.g. "Joe" alone, "Hillary" alone) are NOT listed.
A post can match multiple entries; we keep all distinct (target, sentiment)
hits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Nickname:
    pattern: re.Pattern
    target: str
    sentiment: str  # 'bad' | 'good'

    @classmethod
    def of(cls, pat: str, target: str, sentiment: str) -> "Nickname":
        return cls(re.compile(pat, re.IGNORECASE), target, sentiment)


# ---------- BAD nicknames (pejorative) ----------
_BAD: list[Nickname] = [
    # Hillary Clinton
    Nickname.of(r"\bcrooked hillary\b", "Hillary Clinton", "bad"),
    Nickname.of(r"\bcrooked h\b", "Hillary Clinton", "bad"),
    # Joe Biden
    Nickname.of(r"\bsleepy joe\b", "Joe Biden", "bad"),
    Nickname.of(r"\bcrooked joe\b", "Joe Biden", "bad"),
    Nickname.of(r"\bcrazy joe\b", "Joe Biden", "bad"),
    Nickname.of(r"\bquid pro joe\b", "Joe Biden", "bad"),
    Nickname.of(r"\b1 percent joe\b", "Joe Biden", "bad"),
    Nickname.of(r"\b(?:slow|basement) joe\b", "Joe Biden", "bad"),
    # Ted Cruz
    Nickname.of(r"\blyin[' ]?ted\b", "Ted Cruz", "bad"),
    # Marco Rubio
    Nickname.of(r"\blittle marco\b", "Marco Rubio", "bad"),
    # Chuck Schumer
    Nickname.of(r"\bcryin[' ]?chuck\b", "Chuck Schumer", "bad"),
    Nickname.of(r"\bcrying chuck\b", "Chuck Schumer", "bad"),
    # Nancy Pelosi
    Nickname.of(r"\bcrazy nancy\b", "Nancy Pelosi", "bad"),
    Nickname.of(r"\bnervous nancy\b", "Nancy Pelosi", "bad"),
    # Adam Schiff
    Nickname.of(r"\bshifty schiff\b", "Adam Schiff", "bad"),
    Nickname.of(r"\bliddle['’ ]? adam schiff\b", "Adam Schiff", "bad"),
    Nickname.of(r"\bpencil[- ]neck\b", "Adam Schiff", "bad"),
    # Elizabeth Warren
    Nickname.of(r"\bpocahontas\b", "Elizabeth Warren", "bad"),
    Nickname.of(r"\bgoofy elizabeth warren\b", "Elizabeth Warren", "bad"),
    # Jeb Bush
    Nickname.of(r"\blow energy jeb\b", "Jeb Bush", "bad"),
    # Bernie Sanders
    Nickname.of(r"\bcrazy bernie\b", "Bernie Sanders", "bad"),
    # Kim Jong Un
    Nickname.of(r"\blittle rocket man\b", "Kim Jong Un", "bad"),
    Nickname.of(r"\brocket man\b", "Kim Jong Un", "bad"),
    # Nikki Haley
    Nickname.of(r"\bbirdbrain\b", "Nikki Haley", "bad"),
    Nickname.of(r"\bnimbra\b", "Nikki Haley", "bad"),
    # Ron DeSantis
    Nickname.of(r"\bmeatball ron\b", "Ron DeSantis", "bad"),
    Nickname.of(r"\bron de[- ]?sanctimonious\b", "Ron DeSantis", "bad"),
    # Jack Smith
    Nickname.of(r"\bderanged jack smith\b", "Jack Smith", "bad"),
    # James Comey
    Nickname.of(r"\bleakin[' ]?jim(?:es)? comey\b", "James Comey", "bad"),
    Nickname.of(r"\bslippery james comey\b", "James Comey", "bad"),
    # Bob Corker
    Nickname.of(r"\bliddle['’ ]?bob corker\b", "Bob Corker", "bad"),
    # Jacky Rosen
    Nickname.of(r"\bwacky jacky\b", "Jacky Rosen", "bad"),
    # Mitt Romney
    Nickname.of(r"\bmitt the coward\b", "Mitt Romney", "bad"),
    # Michael Bloomberg
    Nickname.of(r"\bmini (?:mike|michael)\b", "Michael Bloomberg", "bad"),
    # Robert Mueller
    Nickname.of(r"\bbob mueller\b.*\b(?:conflicted|angry|witch hunt)\b", "Robert Mueller", "bad"),
    # Jerry Nadler
    Nickname.of(r"\bfat jerry\b", "Jerry Nadler", "bad"),
    # Bret Baier
    Nickname.of(r"\bshady bret baier\b", "Bret Baier", "bad"),
    # Elaine Chao
    Nickname.of(r"\bcoco chow\b", "Elaine Chao", "bad"),
    # Mitch McConnell
    Nickname.of(r"\bold crow\b", "Mitch McConnell", "bad"),
    # Chris Christie
    Nickname.of(r"\bsloppy chris christie\b", "Chris Christie", "bad"),
    # Collective / groups
    Nickname.of(r"\bdo[- ]?nothing democrats?\b", "Democratic Party", "bad"),
    Nickname.of(r"\brinos?\b", "Establishment Republicans", "bad"),
    Nickname.of(r"\bradical left\b", "Progressives", "bad"),
    Nickname.of(r"\bthe squad\b", "Progressive Democrats", "bad"),
    Nickname.of(r"\bfake news\b", "Media", "bad"),
    Nickname.of(r"\benemy of the people\b", "Media", "bad"),
    Nickname.of(r"\bdemocrat party\b(?!.*great)", "Democratic Party", "bad"),
    # Kamala Harris
    Nickname.of(r"\bkamabla\b", "Kamala Harris", "bad"),
    Nickname.of(r"\blaffin[' ]?kamala\b", "Kamala Harris", "bad"),
    Nickname.of(r"\bcomrade kamala\b", "Kamala Harris", "bad"),
    # Tim Walz
    Nickname.of(r"\btampon tim\b", "Tim Walz", "bad"),
    # Andrew Cuomo
    Nickname.of(r"\bfredo\b", "Chris/Andrew Cuomo", "bad"),
    # Alvin Bragg
    Nickname.of(r"\bfat alvin\b", "Alvin Bragg", "bad"),
    # Letitia James
    Nickname.of(r"\bpeekaboo\b", "Letitia James", "bad"),
    Nickname.of(r"\bracist letitia\b", "Letitia James", "bad"),
    # General pejoratives
    Nickname.of(r"\bsad!\b", "general insult", "bad"),
    Nickname.of(r"\blosers?!\b", "general insult", "bad"),
    Nickname.of(r"\bvery nasty\b", "general insult", "bad"),
]


# ---------- GOOD nicknames (affectionate / positive) ----------
_GOOD: list[Nickname] = [
    # Himself, positive framing
    Nickname.of(r"\bbig don\b", "Donald Trump (self)", "good"),
    Nickname.of(r"\bstable genius\b", "Donald Trump (self)", "good"),
    Nickname.of(r"\bthe chosen one\b", "Donald Trump (self)", "good"),
    # Family
    Nickname.of(r"\bmy beautiful wife\b", "Melania Trump", "good"),
    Nickname.of(r"\bmy beautiful (?:daughter )?ivanka\b", "Ivanka Trump", "good"),
    Nickname.of(r"\b(?:big |my son )barron\b", "Barron Trump", "good"),
    # Allies / surrogates
    Nickname.of(r"\bmy pillow guy\b", "Mike Lindell", "good"),
    Nickname.of(r"\bdiamond and silk\b", "Lynette Hardaway & Rochelle Richardson", "good"),
    # Foreign leaders — warm
    Nickname.of(r"\b(?:my friend )?chairman kim\b", "Kim Jong Un", "good"),
    # Supporters
    Nickname.of(r"\bforgotten (?:men and women|americans?)\b", "Trump base", "good"),
    Nickname.of(r"\bthe silent majority\b", "Trump base", "good"),
    Nickname.of(r"\bgreat patriots?\b", "supporters", "good"),
    # MAGA self-refs
    Nickname.of(r"\bmake america great again\b", "MAGA", "good"),
    Nickname.of(r"\bamerica first\b", "MAGA", "good"),
]

ALL: list[Nickname] = _BAD + _GOOD


def find_hits(text: str) -> list[tuple[str, str, str]]:
    """Return list of (nickname_surface, target, sentiment) for every match in text.

    Deduplicates on (target, sentiment) pair so a single post counted once per
    target even if Trump repeats the nickname in the text.
    """
    seen: set[tuple[str, str]] = set()
    hits: list[tuple[str, str, str]] = []
    for nk in ALL:
        m = nk.pattern.search(text)
        if m:
            key = (nk.target, nk.sentiment)
            if key not in seen:
                seen.add(key)
                hits.append((m.group(0), nk.target, nk.sentiment))
    return hits


def sentiment_for_post(text: str) -> set[str]:
    """Return {'bad'}, {'good'}, {'bad','good'}, or set() based on any hits."""
    hits = find_hits(text)
    return {s for _, _, s in hits}
