"""Fine-tune XTTS-v2 on the Trump voice_dataset.

Prereqs:
  1. `scripts/build_voice_dataset.py` has produced:
       data/voice_dataset/wavs/*.wav
       data/voice_dataset/metadata.json
  2. CUDA-capable GPU with >= 8 GB VRAM.

What this script does:
  1. Reads metadata.json, drops bad clips, writes train.csv + eval.csv
     in Coqui formatter format (header: audio_file|text|speaker_name|emotion_name).
  2. Calls TTS.demos.xtts_ft_demo.utils.gpt_train.train_gpt().
     First run downloads XTTS-v2 base (~1.7 GB) + DVAE/mel-norm files.
  3. Saves checkpoints under data/voice_dataset/run/training/.

Notes:
  - For 8 GB VRAM (RTX 5060 Laptop): batch_size=3, grad_acumm=84.
  - Epochs: 6-10 is the usual range for ~1-2 hours of training audio.
  - Fine-tune preserves zero-shot capability; inference still conditions
    on a reference clip at runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "voice_dataset"
WAVS = DATASET / "wavs"
METADATA_JSON = DATASET / "metadata.json"
TRAIN_CSV = DATASET / "metadata_train.csv"
EVAL_CSV = DATASET / "metadata_eval.csv"

SPEAKER_NAME = "trump"
EMOTION = "neutral"

# Hershey rally CSPAN feed includes Pence warm-up (< 1300s) and CSPAN Washington
# Journal outro (> 5900s). Only keep the Trump portion.
RALLY_TRUMP_WINDOW = (1300.0, 5900.0)


def _is_trump_clip(c: dict) -> bool:
    if c.get("phase") != "rally":
        return True
    s = c.get("start_s", 0)
    return RALLY_TRUMP_WINDOW[0] <= s <= RALLY_TRUMP_WINDOW[1]


def split_manifest(eval_frac: float, seed: int) -> tuple[int, int]:
    clips = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    clips = [
        c for c in clips
        if c.get("text", "").strip()
        and (WAVS / c["file"]).exists()
        and _is_trump_clip(c)
    ]
    random.Random(seed).shuffle(clips)
    n_eval = max(1, int(len(clips) * eval_frac))
    eval_set, train_set = clips[:n_eval], clips[n_eval:]

    _write_csv(TRAIN_CSV, train_set)
    _write_csv(EVAL_CSV, eval_set)
    return len(train_set), len(eval_set)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="|")
        w.writerow(["audio_file", "text", "speaker_name", "emotion_name"])
        for c in rows:
            rel = f"wavs/{c['file']}"
            text = c["text"].strip().replace("|", " ")
            w.writerow([rel, text, SPEAKER_NAME, EMOTION])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--batch-size", type=int, default=3)
    p.add_argument("--grad-accum", type=int, default=84)
    p.add_argument("--eval-frac", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true", help="only build CSVs, no training")
    args = p.parse_args()

    if not METADATA_JSON.exists():
        print(f"ERROR: {METADATA_JSON} not found — run build_voice_dataset.py first")
        return 1

    n_train, n_eval = split_manifest(args.eval_frac, args.seed)
    print(f"train: {n_train}  eval: {n_eval}")
    print(f"  -> {TRAIN_CSV}")
    print(f"  -> {EVAL_CSV}")

    if args.dry_run:
        return 0

    from TTS.demos.xtts_ft_demo.utils.gpt_train import train_gpt

    out_path = DATASET
    cfg, ckpt, tok, run_dir, speaker_ref = train_gpt(
        language="en",
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        grad_acumm=args.grad_accum,
        train_csv=str(TRAIN_CSV),
        eval_csv=str(EVAL_CSV),
        output_path=str(out_path),
    )
    print("\nTraining complete.")
    print(f"  config:      {cfg}")
    print(f"  checkpoint:  {ckpt}")
    print(f"  tokenizer:   {tok}")
    print(f"  run dir:     {run_dir}")
    print(f"  speaker ref: {speaker_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
