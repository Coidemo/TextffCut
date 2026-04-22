"""LoRA 適用 Whisper Large-v3 で動画を文字起こしし、TextffCut のキャッシュ形式で保存する。

その後 `textffcut clip video.mp4` を普通に実行すると、このキャッシュを
ベース版の代わりに使って SRT/FCPXML を生成するので、LoRA の効果を
実運用フローで確認できる。

使い方:
    /Users/naoki/.pyenv/shims/python3 \
      experiments/whisper_lora/run_with_lora.py \
        --video /path/to/video.mp4 \
        --adapter experiments/whisper_lora/outputs/20260129_phase_a/final

処理の流れ:
    1. HF transformers + PEFT で LoRA 適用 Whisper をロード
    2. HF pipeline (chunk_length_s=30, return_timestamps=True) で文字起こし
    3. mlx-forced-aligner で word/char-level timestamps を付与
    4. TextffCut 既定のキャッシュパスに書き出す
       (videos/{stem}_TextffCut/transcriptions/large-v3_v2.json)
       既存ファイルは {name}.base.json としてバックアップ
    5. この状態で textffcut clip を叩けば、この JSON が素材として使われる

依存:
    pyenv Python 3.12 に torch, transformers, peft, mlx-whisper, mlx-forced-aligner,
    librosa がインストール済みであること
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import librosa
import torch
from peft import PeftModel
from transformers import WhisperForConditionalGeneration, WhisperProcessor, pipeline

MODEL_ID = "openai/whisper-large-v3"
SAMPLE_RATE = 16000
CACHE_DIRNAME = "transcriptions"
CACHE_FILENAME = "large-v3_v2.json"  # TextffCut が拾う規約ファイル名


def load_lora_model(
    adapter_path: Path, device: torch.device
) -> tuple[WhisperForConditionalGeneration, WhisperProcessor]:
    print(f"[model] Loading base {MODEL_ID} (fp16) ...")
    t0 = time.time()
    processor = WhisperProcessor.from_pretrained(MODEL_ID, language="japanese", task="transcribe")
    base = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
    print(f"[model] base loaded ({time.time() - t0:.1f}s). Applying LoRA: {adapter_path}")
    model = PeftModel.from_pretrained(base, str(adapter_path))
    model = model.to(device)
    model.eval()
    print(f"[model] ready on {device}")
    return model, processor


def transcribe_with_lora(
    video_path: Path,
    model: WhisperForConditionalGeneration,
    processor: WhisperProcessor,
    device: torch.device,
) -> list[dict]:
    """HF pipeline で 30 秒チャンクずつ文字起こし、segment 単位のリストを返す。"""
    print(f"[asr] {video_path.name} を文字起こし中 ...")
    # librosa で音声 (16kHz, mono) にロード
    t0 = time.time()
    audio, _ = librosa.load(str(video_path), sr=SAMPLE_RATE, mono=True)
    print(f"[asr] audio loaded: {len(audio)/SAMPLE_RATE/60:.1f}min ({time.time() - t0:.1f}s)")

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=30,
        batch_size=1,
        return_timestamps=True,
        device=device,
        torch_dtype=torch.float16,
    )
    t0 = time.time()
    result = pipe(
        {"array": audio, "sampling_rate": SAMPLE_RATE},
        generate_kwargs={"language": "japanese", "task": "transcribe"},
    )
    print(f"[asr] 完了 ({time.time() - t0:.1f}s)")

    segments: list[dict] = []
    for chunk in result["chunks"]:
        ts = chunk.get("timestamp")
        start, end = (ts[0], ts[1]) if ts else (0.0, 0.0)
        if start is None:
            start = 0.0
        if end is None:
            end = float(len(audio)) / SAMPLE_RATE
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        segments.append({"start": float(start), "end": float(end), "text": text})
    print(f"[asr] segments: {len(segments)}")
    return segments


def run_forced_alignment(video_path: Path, segments: list[dict]) -> list[dict]:
    from mlx_forced_aligner import ForcedAligner

    print("[align] mlx-forced-aligner で word/char-level timestamps 付与 ...")
    t0 = time.time()
    aligner = ForcedAligner()
    segs_for_align = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in segments
        if s["text"].strip()
    ]
    align_result = aligner.align(str(video_path), "", segments=segs_for_align)

    aligned: list[dict] = []
    for seg in align_result.segments:
        aligned.append(
            {
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg["text"],
                "words": seg.get("words") or [],
                "chars": seg.get("chars") or [],
            }
        )
    print(f"[align] 完了 ({time.time() - t0:.1f}s), segments: {len(aligned)}")
    return aligned


def write_textffcut_cache(video_path: Path, segments: list[dict], adapter_path: Path) -> Path:
    """TextffCut が参照するキャッシュディレクトリに JSON を書き出す。

    既存のベース版 (large-v3_v2.json) があればバックアップしてから上書きする。
    """
    cache_dir = video_path.parent / f"{video_path.stem}_TextffCut" / CACHE_DIRNAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / CACHE_FILENAME

    if cache_path.exists():
        backup = cache_path.with_suffix(".base.json")
        if not backup.exists():
            print(f"[cache] 既存キャッシュをバックアップ: {backup.name}")
            subprocess.run(["cp", str(cache_path), str(backup)], check=True)
        else:
            print(f"[cache] バックアップ {backup.name} は既に存在 — スキップ")

    payload = {
        "language": "ja",
        "model": MODEL_ID,
        "speed": 1.0,
        "source": str(video_path.resolve()),
        "lora_adapter": str(adapter_path.resolve()),
        "note": f"Whisper large-v3 + LoRA adapter. 元の base 版は {cache_path.stem}.base.json",
        "segments": segments,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[cache] 書き出し完了: {cache_path}")
    return cache_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True, help="train_lora.py の出力 final/ ディレクトリ")
    args = parser.parse_args()

    if not args.video.exists():
        print(f"動画が見つかりません: {args.video}", file=sys.stderr)
        sys.exit(1)
    if not args.adapter.exists():
        print(f"LoRA アダプタが見つかりません: {args.adapter}", file=sys.stderr)
        sys.exit(1)

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"[device] {device}")

    model, processor = load_lora_model(args.adapter, device)
    segments = transcribe_with_lora(args.video, model, processor, device)
    segments = run_forced_alignment(args.video, segments)
    cache_path = write_textffcut_cache(args.video, segments, args.adapter)

    print()
    print("=" * 64)
    print("完了")
    print("=" * 64)
    print(f"  cache: {cache_path}")
    print(f"  次のステップ: textffcut clip {args.video}")
    print(f"    → この cache が拾われ、LoRA ベースの SRT/FCPXML が生成されます")
    print(f"  元に戻したい場合: mv {cache_path.with_suffix('.base.json')} {cache_path}")


if __name__ == "__main__":
    main()
