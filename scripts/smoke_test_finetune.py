"""Smoke-test the fine-tuned XTTS-v2 checkpoint on a few representative texts.

Generates four MP3s under data/voice_dataset/samples/ — one short Truth-Social-style
post, one rally-style line, one all-caps emphasis post, one nickname-laden line —
so we can A/B-listen against the existing zero-shot renders in site/audio/.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data" / "voice_dataset" / "run" / "training"
FT_DIR = RUN / "GPT_XTTS_FT-April-25-2026_09+34AM-f5ba92c"
BASE_DIR = RUN / "XTTS_v2.0_original_model_files"
REF_CLIP = ROOT / "data" / "raw" / "trump_reference.wav"
OUT = ROOT / "data" / "voice_dataset" / "samples"

CHECKPOINT = FT_DIR / "best_model_1617.pth"
CONFIG = FT_DIR / "config.json"
VOCAB = BASE_DIR / "vocab.json"

os.environ.setdefault("COQUI_TOS_AGREED", "1")

SAMPLES = [
    ("01_short_truth",
     "Tremendous news today. Our economy is the greatest in history. Sleepy Joe couldn't dream of these numbers."),
    ("02_rally_long",
     "We're going to bring back our jobs, we're going to bring back our manufacturing, "
     "we're going to bring back our military, and we're going to bring back our borders, "
     "and we're going to make America great again, greater than ever before."),
    ("03_caps_emphasis",
     "WITCH HUNT! The Fake News Media will not report the TRUTH. SAD!"),
    ("04_nicknames",
     "Crooked Hillary, Sleepy Joe, Crazy Nancy — they're all the same. Total disaster for our country."),
]


def find_ffmpeg() -> str | None:
    import shutil, glob

    found = shutil.which("ffmpeg")
    if found:
        return found
    cands = glob.glob(
        str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"),
        recursive=True,
    )
    return cands[0] if cands else None


def main() -> int:
    for path in (CHECKPOINT, CONFIG, VOCAB, REF_CLIP):
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 1

    OUT.mkdir(parents=True, exist_ok=True)

    print("loading fine-tuned XTTS-v2…")
    t0 = time.time()

    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

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
    print(f"  loaded in {time.time() - t0:.1f}s")

    print("extracting conditioning latents from reference clip…")
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[str(REF_CLIP)]
    )

    ffmpeg = find_ffmpeg()
    pydub_ok = False
    if ffmpeg:
        from pydub import AudioSegment

        AudioSegment.converter = ffmpeg
        AudioSegment.ffmpeg = ffmpeg
        AudioSegment.ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
        pydub_ok = True

    import numpy as np
    import soundfile as sf

    for tag, text in SAMPLES:
        wav_path = OUT / f"{tag}.wav"
        mp3_path = OUT / f"{tag}.mp3"
        print(f"\n[{tag}] {text[:80]}{'…' if len(text) > 80 else ''}")
        t1 = time.time()
        result = model.inference(
            text=text,
            language="en",
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
            length_penalty=1.0,
            repetition_penalty=2.0,
            top_k=50,
            top_p=0.85,
        )
        wav = np.asarray(result["wav"], dtype=np.float32)
        sf.write(wav_path, wav, 24000, subtype="PCM_16")
        dur = len(wav) / 24000
        rtf = (time.time() - t1) / dur
        print(f"  wrote {wav_path.name}  duration={dur:.2f}s  rtf={rtf:.2f}")

        if pydub_ok:
            seg = AudioSegment.from_wav(wav_path)
            seg.export(mp3_path, format="mp3", bitrate="64k")
            wav_path.unlink(missing_ok=True)
            print(f"  -> {mp3_path.name}")

    print(f"\ndone. samples in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
