"""Whisper Large-v3 で 1.0x 音声を文字起こしし、LoRA 学習用の素材 JSON + SRT を出力する。

用途:
    手動修正の叩き台になる transcription を作る。
    出力 SRT を Subtitle Edit 等で開いてフィラーを追記 → 人間による正解ラベル化。

入力:
    動画ファイル (.mp4 等)。1.0x speed で処理される。

出力:
    data/raw/{stem}.json : TextffCut cache 互換フォーマット (segments with words/chars)
    data/raw/{stem}.srt  : Subtitle Edit 等で開いて手動修正しやすい SRT

使用モデル:
    mlx-community/whisper-large-v3 (mlx_whisper 経由)
    mlx-forced-aligner で word/char-level timestamps を付与

実行:
    python transcribe_for_lora.py /path/to/video.mp4

    (experiments/whisper_lora/.venv ではなく、pyenv の Python 3.12.3 で実行する。
     mlx-whisper と mlx-forced-aligner は本体プロジェクトの依存なので pyenv 側にある。)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mlx_whisper
from mlx_forced_aligner import ForcedAligner

INITIAL_PROMPT_JA = (
    "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに書き起こしてください。"
    "例: えーっと、えー、あのー、あの、うーん、うーんと、なんか、なんかその、"
    "まあ、まぁ、んー、あー、そうですね"
)

MODEL_ID = "mlx-community/whisper-large-v3-mlx"


def format_srt_time(seconds: float) -> str:
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def export_srt(segments: list[dict], path: Path) -> None:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{format_srt_time(seg['start'])} --> {format_srt_time(seg['end'])}")
        lines.append(seg["text"].strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_alignment(video_path: Path, whisper_segments: list[dict]) -> list[dict]:
    """mlx-forced-aligner で word/char-level timestamps を付与。"""
    aligner = ForcedAligner()
    segs_for_align = [
        {"start": s["start"], "end": s["end"], "text": s.get("text", "").strip()}
        for s in whisper_segments
        if s.get("text", "").strip()
    ]
    align_result = aligner.align(str(video_path), "", segments=segs_for_align)

    # mlx-forced-aligner は segments を dict のリストで返す
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
    return aligned


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="入力動画（1.0x 音声として扱う）")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "data" / "raw")
    parser.add_argument(
        "--skip-align",
        action="store_true",
        help="forced alignment をスキップ（segment-level のみ）",
    )
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"動画が見つかりません: {args.video}")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] Whisper large-v3 で文字起こし中: {args.video.name}")
    t0 = time.time()
    result = mlx_whisper.transcribe(
        str(args.video),
        path_or_hf_repo=MODEL_ID,
        language="ja",
        initial_prompt=INITIAL_PROMPT_JA,
    )
    print(f"     完了 ({time.time() - t0:.1f}s, {len(result.get('segments', []))} segments)")

    segments: list[dict] = result["segments"]

    if not args.skip_align:
        print("[2/3] forced-aligner で word/char-level timestamps を付与中 ...")
        t0 = time.time()
        segments = run_alignment(args.video, segments)
        print(f"     完了 ({time.time() - t0:.1f}s)")

    output = {
        "language": result.get("language", "ja"),
        "model": MODEL_ID,
        "speed": 1.0,
        "source": str(args.video.resolve()),
        "initial_prompt": INITIAL_PROMPT_JA,
        "note": "Whisper output — 手動修正前の叩き台。フィラー取りこぼしあり。",
        "segments": segments,
    }

    print("[3/3] JSON + SRT を書き出し中 ...")
    out_json = out_dir / f"{args.video.stem}.json"
    out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"     JSON: {out_json}")

    out_srt = out_dir / f"{args.video.stem}.srt"
    export_srt(segments, out_srt)
    print(f"     SRT:  {out_srt}")

    print("\nDone. 次のステップ: SRT を Subtitle Edit / Aegisub で開いて手動修正してください。")


if __name__ == "__main__":
    main()
