"""edited.json と動画 → HuggingFace Dataset (train/eval) を生成する。

edit_tool で人間が修正した transcription を、Whisper LoRA 学習で直接使える
HF Dataset 形式に変換する。

入力:
    --edited: edit_tool の保存先である .edited.json
    --video:  1.0x 音声を含む動画ファイル
    --out:    出力先ディレクトリ

出力:
    {out}/audio_16khz.wav   : 全編の 16kHz mono WAV (チャンク音声のソース)
    {out}/train/            : HF Dataset (訓練用)
    {out}/eval/             : HF Dataset (評価用)

    各レコードのスキーマ:
        audio_path: str     WAV ファイルの絶対パス
        offset:    float    audio_path 内での開始秒
        duration:  float    チャンクの秒数
        text:      str      このチャンクに対応する教師テキスト

使い方:
    cd experiments/whisper_lora
    source .venv/bin/activate
    python prepare_dataset.py \
        --edited data/raw/20260129_生成AI….edited.json \
        --video /Users/naoki/myProject/TextffCut/videos/20260129_生成AI….mp4 \
        --out data/hf/20260129_生成AI
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from datasets import Dataset

# Whisper の最大入力長は 30 秒。安全マージンを取って 28 秒上限に詰め込む
MAX_CHUNK_SEC = 28.0


def group_segments(segments: list[dict], max_sec: float) -> list[dict]:
    """連続する segments を max_sec 以内のチャンクにまとめる。

    skip=true のセグメントは除外し、そこでチャンクも強制的に切る
    （skip を挟む = 連続性が壊れる → 無理に結合しない）。
    """
    chunks: list[dict] = []
    buf_start: float | None = None
    buf_end: float | None = None
    buf_texts: list[str] = []

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_texts
        if buf_texts and buf_start is not None and buf_end is not None:
            text = "".join(buf_texts).strip()
            if text:
                chunks.append({"start": buf_start, "end": buf_end, "text": text})
        buf_start = None
        buf_end = None
        buf_texts = []

    for seg in segments:
        if seg.get("skip"):
            flush()
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            # 空テキスト（編集で全消しされた等）はチャンクに含めない
            # が連続性は維持
            continue

        if buf_start is None:
            buf_start = seg["start"]

        if seg["end"] - buf_start > max_sec and buf_texts:
            flush()
            buf_start = seg["start"]

        buf_end = seg["end"]
        buf_texts.append(seg["text"])

    flush()
    return chunks


def extract_audio_16khz_mono(video_path: Path, out_path: Path) -> None:
    """動画から 16kHz mono の WAV を抽出。存在すればスキップ。"""
    if out_path.exists():
        print(f"  既存 WAV を利用: {out_path}")
        return
    print(f"  16kHz mono WAV 抽出中: {video_path.name}")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out_path),
        ],
        check=True, capture_output=True,
    )


def split_train_eval(
    chunks: list[dict],
    eval_seconds: float,
) -> tuple[list[dict], list[dict]]:
    """時間順で最後の eval_seconds を eval、残りを train にする。

    境界またぎのチャンクは train に寄せる（eval_start に end が掛かったら train 側）。
    """
    if not chunks:
        return [], []
    last_end = chunks[-1]["end"]
    eval_start = last_end - eval_seconds
    train: list[dict] = []
    eval_: list[dict] = []
    for c in chunks:
        if c["start"] >= eval_start:
            eval_.append(c)
        else:
            train.append(c)
    return train, eval_


def to_dataset(chunks: list[dict], wav_abs: str) -> Dataset:
    return Dataset.from_dict(
        {
            "audio_path": [wav_abs] * len(chunks),
            "offset": [c["start"] for c in chunks],
            "duration": [c["end"] - c["start"] for c in chunks],
            "text": [c["text"] for c in chunks],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edited", type=Path, required=True, help=".edited.json のパス")
    parser.add_argument("--video", type=Path, required=True, help="動画ファイル (1.0x)")
    parser.add_argument("--out", type=Path, required=True, help="出力ディレクトリ")
    parser.add_argument(
        "--eval-seconds", type=float, default=600,
        help="最後の何秒を eval にするか (default=600 = 10分)",
    )
    parser.add_argument(
        "--max-chunk-sec", type=float, default=MAX_CHUNK_SEC,
        help=f"チャンクの最大秒数 (default={MAX_CHUNK_SEC})",
    )
    args = parser.parse_args()

    if not args.edited.exists():
        print(f"edited.json が見つかりません: {args.edited}", file=sys.stderr)
        sys.exit(1)
    if not args.video.exists():
        print(f"動画が見つかりません: {args.video}", file=sys.stderr)
        sys.exit(1)

    print(f"[1/4] {args.edited.name} を読み込み ...")
    data = json.loads(args.edited.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    total_segs = len(segments)
    kept = sum(1 for s in segments if not s.get("skip"))
    print(f"     総セグメント: {total_segs}, 学習対象 (Skip以外): {kept}")

    print(f"[2/4] チャンク化 (max {args.max_chunk_sec}秒) ...")
    chunks = group_segments(segments, max_sec=args.max_chunk_sec)
    total_dur = sum(c["end"] - c["start"] for c in chunks)
    avg_dur = total_dur / len(chunks) if chunks else 0
    print(f"     チャンク数: {len(chunks)}, 総音声長: {total_dur/60:.1f}分, 平均長: {avg_dur:.1f}秒")

    train_chunks, eval_chunks = split_train_eval(chunks, args.eval_seconds)
    train_dur = sum(c["end"] - c["start"] for c in train_chunks)
    eval_dur = sum(c["end"] - c["start"] for c in eval_chunks)
    print(f"     train: {len(train_chunks)} chunks = {train_dur/60:.1f}分")
    print(f"     eval:  {len(eval_chunks)} chunks = {eval_dur/60:.1f}分")

    print("[3/4] 音声抽出 ...")
    args.out.mkdir(parents=True, exist_ok=True)
    wav_path = args.out / "audio_16khz.wav"
    extract_audio_16khz_mono(args.video, wav_path)
    wav_abs = str(wav_path.resolve())

    print("[4/4] HF Dataset 書き出し ...")
    train_ds = to_dataset(train_chunks, wav_abs)
    eval_ds = to_dataset(eval_chunks, wav_abs)
    train_ds.save_to_disk(str(args.out / "train"))
    eval_ds.save_to_disk(str(args.out / "eval"))
    print(f"     -> {args.out / 'train'}  ({len(train_ds)} records)")
    print(f"     -> {args.out / 'eval'}   ({len(eval_ds)} records)")

    # メタデータも残しておく（後から再現できるように）
    meta = {
        "source_edited": str(args.edited.resolve()),
        "source_video": str(args.video.resolve()),
        "audio_wav": wav_abs,
        "max_chunk_sec": args.max_chunk_sec,
        "eval_seconds": args.eval_seconds,
        "stats": {
            "total_segments": total_segs,
            "kept_segments": kept,
            "total_chunks": len(chunks),
            "train_chunks": len(train_chunks),
            "eval_chunks": len(eval_chunks),
            "train_minutes": round(train_dur / 60, 2),
            "eval_minutes": round(eval_dur / 60, 2),
        },
    }
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone. 次は train_lora.py で学習してください。")


if __name__ == "__main__":
    main()
