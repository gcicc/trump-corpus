"""Small utilities shared by fetchers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from dateutil import parser as dateparser

USER_AGENT = "trump-corpus/0.1 (personal research)"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_iso_utc(value: str | datetime | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = dateparser.parse(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat()


def download(url: str, dest: Path, *, chunk: int = 1 << 15) -> Path:
    """Download url to dest (streaming). Returns dest. Overwrites on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, headers={"User-Agent": USER_AGENT}, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for block in r.iter_content(chunk_size=chunk):
                if block:
                    f.write(block)
    tmp.replace(dest)
    return dest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dumps_compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
