"""Score every voice_dataset/wavs/*.wav for similarity to a known-Trump anchor.

Uses Resemblyzer (a small 256-d speaker-embedding model). Anchor = the
2017 inaugural reference clip in data/raw/trump_reference.wav, which is
provably pure Trump.

Outputs:
  - data/voice_dataset/speaker_scores.json
        { clip_tag: similarity_in_[0,1] }
  - prints histogram so we can pick a threshold
  - prints the top-K longest contiguous high-similarity rally segment
        (used to build a rally-style inference reference clip)

Optional:
  --build-rally-ref  concatenate the top rally clips into
                     data/raw/trump_rally_reference.wav (~15 s)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "voice_dataset"
WAVS = DATASET / "wavs"
META = DATASET / "metadata.json"
ANCHOR = ROOT / "data" / "raw" / "trump_reference.wav"
SCORES_OUT = DATASET / "speaker_scores.json"
RALLY_REF_OUT = ROOT / "data" / "raw" / "trump_rally_reference.wav"


def embed_clip(encoder, path: Path) -> np.ndarray | None:
    from resemblyzer import preprocess_wav

    try:
        wav = preprocess_wav(str(path))
        if len(wav) < 16000:  # < 1 s of usable audio post-VAD
            return None
        return encoder.embed_utterance(wav)
    except Exception as e:  # noqa: BLE001
        print(f"  [embed] {path.name}: {type(e).__name__}: {e}")
        return None


def score_all(encoder, anchor_emb: np.ndarray) -> dict[str, float]:
    scores: dict[str, float] = {}
    files = sorted(WAVS.glob("*.wav"))
    print(f"scoring {len(files)} clips…")
    for i, f in enumerate(files, start=1):
        emb = embed_clip(encoder, f)
        if emb is None:
            continue
        sim = float(np.dot(anchor_emb, emb))
        scores[f.stem] = sim
        if i % 100 == 0:
            print(f"  {i}/{len(files)}")
    return scores


def histogram(scores: dict[str, float]) -> None:
    bins = np.arange(0.0, 1.01, 0.05)
    vals = np.array(list(scores.values()))
    counts, edges = np.histogram(vals, bins=bins)
    print("\nsimilarity histogram (anchor = inaugural):")
    for c, lo, hi in zip(counts, edges[:-1], edges[1:]):
        bar = "#" * min(c, 60)
        print(f"  {lo:.2f}-{hi:.2f}  {c:4d}  {bar}")
    print(f"  median={np.median(vals):.3f}  mean={np.mean(vals):.3f}  "
          f"p25={np.quantile(vals,0.25):.3f}  p75={np.quantile(vals,0.75):.3f}")


def per_phase_stats(scores: dict[str, float], clips: list[dict]) -> None:
    by_phase: dict[str, list[float]] = {"wh_oval": [], "rally": []}
    by_clip = {c["tag"]: c for c in clips}
    for tag, sim in scores.items():
        c = by_clip.get(tag)
        if c:
            by_phase.setdefault(c["phase"], []).append(sim)
    print("\nper-phase similarity:")
    for phase, vals in by_phase.items():
        if not vals:
            continue
        a = np.array(vals)
        print(f"  {phase:10s}  n={len(a):4d}  median={np.median(a):.3f}  "
              f"p25={np.quantile(a,0.25):.3f}  p75={np.quantile(a,0.75):.3f}")


def pick_rally_reference(scores: dict[str, float], clips: list[dict],
                         target_dur: float = 15.0,
                         min_clip_dur: float = 4.0,
                         min_sim: float = 0.85) -> list[dict]:
    """Pick high-similarity rally clips that together hit ~target_dur."""
    by_clip = {c["tag"]: c for c in clips}
    rally = []
    for tag, sim in scores.items():
        c = by_clip.get(tag)
        if not c or c["phase"] != "rally":
            continue
        if c["duration"] < min_clip_dur or sim < min_sim:
            continue
        rally.append({**c, "sim": sim})
    rally.sort(key=lambda c: (-c["sim"], -c["duration"]))

    chosen: list[dict] = []
    total = 0.0
    for c in rally:
        if total >= target_dur:
            break
        chosen.append(c)
        total += c["duration"]
    return chosen


def build_rally_ref(chosen: list[dict]) -> None:
    import soundfile as sf

    if not chosen:
        print("  [rally-ref] no clips picked; lower --min-sim?")
        return
    bufs = []
    sr = None
    for c in chosen:
        wav, csr = sf.read(WAVS / f"{c['tag']}.wav")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr is None:
            sr = csr
        bufs.append(wav.astype(np.float32))
        # 0.15s gap between clips so XTTS sees a natural pause
        bufs.append(np.zeros(int(0.15 * sr), dtype=np.float32))
    out = np.concatenate(bufs)
    RALLY_REF_OUT.parent.mkdir(parents=True, exist_ok=True)
    sf.write(RALLY_REF_OUT, out, sr, subtype="PCM_16")
    dur = len(out) / sr
    print(f"\n  [rally-ref] wrote {RALLY_REF_OUT}  duration={dur:.1f}s  "
          f"using {len(chosen)} clips, avg sim={np.mean([c['sim'] for c in chosen]):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="re-score even if speaker_scores.json exists")
    ap.add_argument("--build-rally-ref", action="store_true",
                    help="concatenate top rally clips into trump_rally_reference.wav")
    ap.add_argument("--min-sim", type=float, default=0.85,
                    help="similarity floor for rally-ref selection (default 0.85)")
    ap.add_argument("--target-dur", type=float, default=15.0,
                    help="target duration for rally reference clip (default 15s)")
    args = ap.parse_args()

    if not ANCHOR.exists():
        print(f"missing anchor clip: {ANCHOR}")
        return 1

    if SCORES_OUT.exists() and not args.rebuild:
        print(f"loading cached scores from {SCORES_OUT}")
        scores = json.loads(SCORES_OUT.read_text(encoding="utf-8"))
    else:
        from resemblyzer import VoiceEncoder, preprocess_wav

        encoder = VoiceEncoder()
        print("computing anchor embedding…")
        anchor_wav = preprocess_wav(str(ANCHOR))
        anchor_emb = encoder.embed_utterance(anchor_wav)

        scores = score_all(encoder, anchor_emb)
        SCORES_OUT.write_text(json.dumps(scores, indent=2), encoding="utf-8")
        print(f"\nwrote {SCORES_OUT}")

    clips = json.loads(META.read_text(encoding="utf-8"))
    histogram(scores)
    per_phase_stats(scores, clips)

    chosen = pick_rally_reference(
        scores, clips, target_dur=args.target_dur, min_sim=args.min_sim
    )
    print(f"\nrally-ref candidates (sim >= {args.min_sim}, dur >= 4s, "
          f"target ~{args.target_dur}s):")
    for c in chosen:
        print(f"  {c['tag']}  sim={c['sim']:.3f}  dur={c['duration']:.1f}s  "
              f"text={c.get('text','')[:60]!r}")

    if args.build_rally_ref:
        build_rally_ref(chosen)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
