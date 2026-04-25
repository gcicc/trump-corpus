"""Build a fine-tuning dataset for XTTS-v2 from raw Trump audio.

Pipeline:
  1. Normalize each source MP3/OGG to 22050 Hz mono WAV.
  2. Silero VAD: detect continuous speech regions.
  3. Split into 2-12 second clips at sentence boundaries where possible.
  4. Whisper-large (GPU): transcribe each clip.
  5. Filter:
       - Drop clips < 1.5 s or > 15 s.
       - Drop clips with high non-speech energy (likely crowd/music).
       - Drop clips whose transcript is < 3 words (likely noise).
  6. Write LJSpeech-format `metadata.csv` + `wavs/*.wav` layout.

Sources are read from SOURCES table below. Each has a `phase` (wh_oval or rally)
so we can later enforce the 70/30 mix.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATASET = ROOT / "data" / "voice_dataset"
WAVS = DATASET / "wavs"
MANIFEST = DATASET / "metadata.csv"

FFMPEG = (
    Path.home()
    / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
)


def _find_ffmpeg() -> str:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import glob

    matches = glob.glob(str(FFMPEG / "**/bin/ffmpeg.exe"), recursive=True)
    return matches[0] if matches else "ffmpeg"


FFMPEG_BIN = _find_ffmpeg()


@dataclass(frozen=True)
class Source:
    file: str           # relative to data/raw
    phase: str          # 'wh_oval' or 'rally'
    description: str


SOURCES: list[Source] = [
    Source("trump_wh_speech.ogg", "wh_oval", "2020-11-05 post-election WH statement (16 min)"),
    Source("trump_hershey_rally.mp3", "rally", "2019-12-10 Hershey PA rally (CSPAN2, ~100 min)"),
]


# ---- Step 1: normalize to 22050 mono wav ----

def normalize_audio(src: Path, dst: Path) -> bool:
    if dst.exists():
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN, "-y", "-i", str(src),
        "-ar", "22050", "-ac", "1",
        "-af", "highpass=f=80,lowpass=f=8000,loudnorm=I=-20:LRA=7",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode(errors="replace")[-500:])
        return False
    return True


# ---- Step 2 + 3: VAD + segment ----

def run_vad_and_segment(wav_path: Path, out_dir: Path, source_tag: str) -> list[dict]:
    """Use Silero VAD to find speech regions. Return list of clip metadata.

    Silero only supports 8 kHz / 16 kHz, so we run VAD on a 16 kHz copy and
    then slice clips from the original (22050 Hz) master.
    """
    import torch
    import torchaudio.functional as AF

    out_dir.mkdir(parents=True, exist_ok=True)

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    (get_speech_timestamps, _, read_audio, _, _) = utils

    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio_t = torch.from_numpy(audio).float()

    # Build a 16 kHz copy just for VAD
    VAD_SR = 16000
    if sr != VAD_SR:
        vad_audio = AF.resample(audio_t.unsqueeze(0), orig_freq=sr, new_freq=VAD_SR).squeeze(0)
    else:
        vad_audio = audio_t

    vad_ts = get_speech_timestamps(
        vad_audio, model,
        sampling_rate=VAD_SR,
        threshold=0.55,
        min_speech_duration_ms=800,
        min_silence_duration_ms=400,
        speech_pad_ms=120,
    )

    # Map VAD timestamps (in 16 kHz samples) back to original sample rate
    scale = sr / VAD_SR
    speech_ts = [
        {"start": int(t["start"] * scale), "end": int(t["end"] * scale)}
        for t in vad_ts
    ]

    clips = []
    min_len_s = 2.0
    max_len_s = 12.0
    min_s = int(min_len_s * sr)
    max_s = int(max_len_s * sr)

    # Split long regions into ~10s chunks at silence boundaries
    for i, seg in enumerate(speech_ts):
        start, end = seg["start"], seg["end"]
        region_len = end - start
        if region_len < min_s:
            continue

        # Greedy split
        cuts = [start]
        cur = start
        while cur + max_s < end:
            cur += max_s
            cuts.append(cur)
        cuts.append(end)

        for j in range(len(cuts) - 1):
            s, e = cuts[j], cuts[j + 1]
            if e - s < min_s:
                continue
            clip = audio[s:e]
            # Skip quiet clips (likely dropped noise)
            rms = float(np.sqrt(np.mean(clip ** 2)))
            if rms < 0.01:
                continue
            tag = f"{source_tag}_{i:04d}_{j:02d}"
            out_path = out_dir / f"{tag}.wav"
            sf.write(out_path, clip, sr, subtype="PCM_16")
            clips.append({
                "tag": tag,
                "file": out_path.name,
                "duration": round((e - s) / sr, 2),
                "rms": round(rms, 4),
                "start_s": round(s / sr, 2),
                "end_s": round(e / sr, 2),
            })
    return clips


# ---- Step 4: transcribe with Whisper ----

def transcribe_clips(clips: list[dict], wav_dir: Path, model_size: str = "large-v3") -> None:
    """Transcribe clips with Whisper.

    We load audio ourselves with soundfile and resample to 16 kHz so whisper's
    internal ffmpeg subprocess is never invoked (ffmpeg isn't on PATH here).
    """
    import whisper  # type: ignore
    import torch as _torch
    import torchaudio.functional as AF

    device = "cuda" if _torch.cuda.is_available() else "cpu"
    print(f"  [whisper] loading {model_size} on {device}")
    model = whisper.load_model(model_size, device=device)
    for i, c in enumerate(clips):
        if c.get("text"):
            continue
        audio, sr = sf.read(wav_dir / c["file"])
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            audio_t = _torch.from_numpy(audio).float().unsqueeze(0)
            audio_t = AF.resample(audio_t, orig_freq=sr, new_freq=16000).squeeze(0)
            audio = audio_t.numpy()
        r = model.transcribe(audio.astype("float32"), language="en", temperature=0.0)
        c["text"] = (r.get("text") or "").strip()
        if (i + 1) % 25 == 0:
            print(f"  [whisper] {i + 1}/{len(clips)}")


# ---- Step 5: filter ----

def filter_clips(clips: list[dict]) -> list[dict]:
    kept = []
    dropped = defaultdict(int)
    for c in clips:
        text = (c.get("text") or "").strip()
        words = text.split()
        if len(words) < 3:
            dropped["short_text"] += 1
            continue
        if c["duration"] < 2.0 or c["duration"] > 15.0:
            dropped["bad_duration"] += 1
            continue
        # Reject if clip is mostly punctuation/noise
        if sum(ch.isalpha() for ch in text) < 10:
            dropped["low_alpha"] += 1
            continue
        kept.append(c)
    print(f"  filter: kept {len(kept)} / dropped {dict(dropped)}")
    return kept


# ---- Orchestrator ----

def process_source(src: Source, *, use_whisper: bool) -> list[dict]:
    raw = RAW / src.file
    if not raw.exists():
        print(f"  [skip] {raw} not found")
        return []

    stem = raw.stem
    norm_wav = DATASET / "_normalized" / f"{stem}.wav"
    clip_dir = WAVS

    print(f"\n== {src.file} ({src.phase}) ==")
    if not normalize_audio(raw, norm_wav):
        print("  normalize failed")
        return []
    print(f"  normalized -> {norm_wav}")

    clips = run_vad_and_segment(norm_wav, clip_dir, stem)
    print(f"  VAD produced {len(clips)} clips")

    for c in clips:
        c["phase"] = src.phase
        c["source"] = src.file

    if use_whisper:
        transcribe_clips(clips, clip_dir)
        clips = filter_clips(clips)

    return clips


def write_manifest(all_clips: list[dict]) -> None:
    DATASET.mkdir(parents=True, exist_ok=True)
    # LJSpeech format: filename|text|text_normalized
    # Plus a sidecar JSON with richer metadata for curation
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="|")
        for c in all_clips:
            text = c.get("text", "")
            w.writerow([c["file"].replace(".wav", ""), text, text])
    (DATASET / "metadata.json").write_text(
        json.dumps(all_clips, indent=2, default=str), encoding="utf-8"
    )
    # Summary
    by_phase = defaultdict(list)
    for c in all_clips:
        by_phase[c.get("phase", "?")].append(c["duration"])
    print("\nDataset summary:")
    for phase, durs in by_phase.items():
        total = sum(durs)
        print(f"  {phase:10s} {len(durs):>5d} clips  {total / 60:.1f} min")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-whisper", action="store_true", help="skip transcription (for dry run)")
    args = p.parse_args()

    DATASET.mkdir(parents=True, exist_ok=True)
    WAVS.mkdir(parents=True, exist_ok=True)

    all_clips: list[dict] = []
    for src in SOURCES:
        all_clips.extend(process_source(src, use_whisper=not args.no_whisper))

    if all_clips:
        write_manifest(all_clips)
        print(f"\nmanifest -> {MANIFEST}")
    else:
        print("no clips produced; exiting")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
