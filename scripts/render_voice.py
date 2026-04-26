"""Pre-render top-N posts as Trump-voice MP3s using fine-tuned XTTS-v2.

Requires the `trump-voice` venv (Python 3.11 with coqui-tts + Resemblyzer
trained checkpoint at data/voice_dataset/run/training/.../best_model_*.pth).

Selection of the top-N posts:
  - Highest-scoring post per theme (breadth)
  - Most recent posts (topicality)
  - Long-form posts that read well

Production settings (locked in after smoke-test A/B):
  - Reference: rally clip (Hershey 0489+0525 concatenated, sim 0.84)
  - Temperature 0.85, repetition_penalty 2.0, top_p 0.85

Output:
  site/audio/<post_id>.mp3
  site/data/audio_manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "corpus.sqlite"
SITE = ROOT / "site"
AUDIO_DIR = SITE / "audio"
MANIFEST = SITE / "data" / "audio_manifest.json"
DEFAULT_REF = ROOT / "data" / "raw" / "trump_rally_reference.wav"

RUN_BASE = ROOT / "data" / "voice_dataset" / "run" / "training"
FT_DIR = RUN_BASE / "GPT_XTTS_FT-April-25-2026_09+34AM-f5ba92c"
BASE_DIR = RUN_BASE / "XTTS_v2.0_original_model_files"
CHECKPOINT = FT_DIR / "best_model_1617.pth"
CONFIG = FT_DIR / "config.json"
VOCAB = BASE_DIR / "vocab.json"

# XTTS-v2 license auto-accept (Coqui Public Model License — personal use OK)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

# Locate ffmpeg.exe so pydub can find it (Windows winget install path varies)
def _find_ffmpeg() -> str | None:
    import shutil as _sh

    found = _sh.which("ffmpeg")
    if found:
        return found
    import glob as _glob

    candidates = _glob.glob(
        str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"),
        recursive=True,
    )
    return candidates[0] if candidates else None


_FFMPEG = _find_ffmpeg()
if _FFMPEG:
    os.environ["PATH"] = str(Path(_FFMPEG).parent) + os.pathsep + os.environ.get("PATH", "")


def _clean_text(s: str) -> str:
    """Strip URLs, stray markup, extra whitespace. Keep Trump-style CAPS."""
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def select_posts(conn: sqlite3.Connection, n: int) -> list[dict]:
    """Spread across themes + time, prefer longer readable posts."""
    # Top post per theme by score, up to k themes
    rows = conn.execute(
        """
        WITH ranked AS (
          SELECT pt.theme, p.id, p.text, p.timestamp_utc, pt.score,
                 length(p.text) AS L,
                 ROW_NUMBER() OVER (PARTITION BY pt.theme ORDER BY pt.score DESC) AS rn
            FROM post_themes pt
            JOIN posts p ON p.id = pt.post_id
           WHERE pt.rank = 1 AND length(p.text) BETWEEN 40 AND 280
        )
        SELECT id, text, timestamp_utc, theme, score
          FROM ranked
         WHERE rn <= ?
         ORDER BY theme, score DESC
        """,
        (max(1, n // 20),),
    ).fetchall()
    cols = ["id", "text", "timestamp_utc", "theme", "score"]
    picks = [dict(zip(cols, r)) for r in rows]

    # Fill the rest with recent Truth Social posts
    remaining = n - len(picks)
    if remaining > 0:
        more = conn.execute(
            """
            SELECT p.id, p.text, p.timestamp_utc, pt.theme, pt.score
              FROM posts p LEFT JOIN post_themes pt ON pt.post_id = p.id AND pt.rank = 1
             WHERE p.platform = 'truth_social'
               AND length(p.text) BETWEEN 40 AND 280
               AND p.id NOT IN (SELECT id FROM (VALUES %s))
             ORDER BY p.timestamp_utc DESC
             LIMIT ?
            """.replace("%s", ",".join(["(?)"] * len(picks)) or "('__none__')"),
            [p["id"] for p in picks] + [remaining],
        ).fetchall()
        picks.extend(dict(zip(cols, r)) for r in more)

    return picks[:n]


def render_one(model, latents, text: str, out_wav: Path, *,
               temperature: float, rep_penalty: float, top_p: float) -> bool:
    import numpy as np
    import soundfile as sf

    gpt_cond_latent, speaker_embedding = latents
    try:
        result = model.inference(
            text=text,
            language="en",
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=temperature,
            length_penalty=1.0,
            repetition_penalty=rep_penalty,
            top_k=50,
            top_p=top_p,
        )
        wav = np.asarray(result["wav"], dtype=np.float32)
        sf.write(out_wav, wav, 24000, subtype="PCM_16")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [render] FAIL {out_wav.name}: {type(e).__name__}: {e}")
        return False


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """Encode wav -> mp3 via pydub (requires ffmpeg)."""
    try:
        from pydub import AudioSegment

        if _FFMPEG:
            AudioSegment.converter = _FFMPEG
            AudioSegment.ffmpeg = _FFMPEG
            AudioSegment.ffprobe = _FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")

        seg = AudioSegment.from_wav(wav_path)
        seg.export(mp3_path, format="mp3", bitrate="64k")
        if mp3_path.stat().st_size == 0:
            mp3_path.unlink(missing_ok=True)
            print(f"  [mp3] empty output, deleted")
            return False
        wav_path.unlink(missing_ok=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [mp3] FAIL: {e}")
        if mp3_path.exists() and mp3_path.stat().st_size == 0:
            mp3_path.unlink(missing_ok=True)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500, help="how many posts to render (default 500)")
    p.add_argument("--dry-run", action="store_true", help="select posts but don't render audio")
    p.add_argument("--ref", type=Path, default=DEFAULT_REF,
                   help=f"speaker reference clip (default: {DEFAULT_REF.name})")
    p.add_argument("--temperature", type=float, default=0.85)
    p.add_argument("--rep-penalty", type=float, default=2.0)
    p.add_argument("--top-p", type=float, default=0.85)
    p.add_argument("--force", action="store_true",
                   help="re-render even if MP3 already exists (use after model swap)")
    args = p.parse_args()

    if not DB.exists():
        print(f"No db at {DB}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB)
    picks = select_posts(conn, args.n)
    conn.close()
    print(f"selected {len(picks)} posts across {len({p['theme'] for p in picks})} themes")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        preview = SITE / "data" / "audio_selection_preview.json"
        preview.write_text(json.dumps(picks, indent=2, default=str), encoding="utf-8")
        print(f"dry run -> {preview}")
        return 0

    REF_CLIP = args.ref
    for path in (REF_CLIP, CHECKPOINT, CONFIG, VOCAB):
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2

    # Lazy imports so --dry-run doesn't require TTS / torch
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    print(f"loading fine-tuned XTTS-v2 from {CHECKPOINT.name}…")
    config = XttsConfig()
    config.load_json(str(CONFIG))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(
        config,
        checkpoint_path=str(CHECKPOINT),
        vocab_path=str(VOCAB),
        use_deepspeed=False,
    )
    if torch.cuda.is_available():
        model.cuda()

    print(f"extracting conditioning latents from {REF_CLIP.name}…")
    latents = model.get_conditioning_latents(audio_path=[str(REF_CLIP)])

    manifest: dict = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8")).get("entries", {})
        except Exception:  # noqa: BLE001
            manifest = {}

    rendered = 0
    skipped = 0
    for i, post in enumerate(picks, start=1):
        pid = post["id"]
        mp3 = AUDIO_DIR / f"{pid}.mp3"
        if mp3.exists() and mp3.stat().st_size > 0 and not args.force:
            skipped += 1
            continue

        text = _clean_text(post["text"])
        if not text:
            continue

        wav = AUDIO_DIR / f"{pid}.wav"
        ok = render_one(model, latents, text, wav,
                        temperature=args.temperature,
                        rep_penalty=args.rep_penalty,
                        top_p=args.top_p)
        if not ok:
            continue
        if not wav_to_mp3(wav, mp3):
            continue

        manifest[pid] = {"file": f"audio/{pid}.mp3", "len": len(text)}
        rendered += 1

        if i % 10 == 0:
            print(f"  rendered {rendered}/{i}  (skipped already-done: {skipped})")
            MANIFEST.write_text(
                json.dumps({"schema": "post_id -> {file, len}", "entries": manifest}, indent=2),
                encoding="utf-8",
            )

    MANIFEST.write_text(
        json.dumps({"schema": "post_id -> {file, len}", "entries": manifest}, indent=2),
        encoding="utf-8",
    )
    print(f"\ndone. rendered {rendered}, pre-existing {skipped}, total in manifest {len(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
