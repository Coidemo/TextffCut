"""
精度比較スクリプト: WhisperX vs MLX (mlx-whisper + mlx-forced-aligner)

TextffCutのTranscriptionResultを使って、同じ動画に対する
両パイプラインの出力を比較する。

Usage:
    python scripts/compare_whisperx_vs_mlx.py videos/動画.mp4
    python scripts/compare_whisperx_vs_mlx.py videos/動画.mp4 --model medium --save results.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

# TextffCutのルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.transcription import TranscriptionResult, TranscriptionSegment
from config import Config


def transcribe_whisperx(
    video_path: str, model_size: str = "medium", language: str = "ja"
) -> tuple[TranscriptionResult, dict]:
    """WhisperXパイプライン（従来版）"""
    import torch
    import whisperx

    print(f"\n{'='*60}")
    print(f"WhisperX ({model_size})")
    print(f"{'='*60}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "int8"
    times = {}

    t0 = time.time()
    audio = whisperx.load_audio(video_path)
    times["audio_load"] = time.time() - t0

    t1 = time.time()
    asr_model = whisperx.load_model(model_size, device, compute_type=compute_type, language=language)
    result = asr_model.transcribe(audio, batch_size=8, language=language, task="transcribe")
    times["transcribe"] = time.time() - t1

    t2 = time.time()
    align_model, align_meta = whisperx.load_align_model(language_code=language, device=device)
    result = whisperx.align(
        result["segments"], align_model, align_meta, audio, device,
        return_char_alignments=True,
    )
    times["alignment"] = time.time() - t2
    times["total"] = time.time() - t0

    # TranscriptionResultに変換
    segments = []
    for seg in result.get("segments", []):
        segments.append(TranscriptionSegment(
            start=seg.get("start", 0),
            end=seg.get("end", 0),
            text=seg.get("text", ""),
            words=seg.get("words"),
            chars=seg.get("chars"),
        ))

    tr = TranscriptionResult(
        language=language,
        segments=segments,
        original_audio_path=video_path,
        model_size=model_size,
        processing_time=times["total"],
    )

    print(f"  文字起こし: {times['transcribe']:.1f}s")
    print(f"  アライメント: {times['alignment']:.1f}s")
    print(f"  合計: {times['total']:.1f}s")
    print(f"  セグメント数: {len(segments)}")

    return tr, times


def transcribe_mlx(
    video_path: str, model_size: str = "medium", language: str = "ja"
) -> tuple[TranscriptionResult, dict]:
    """MLXパイプライン（mlx-whisper + mlx-forced-aligner）"""
    import mlx_whisper
    from mlx_forced_aligner import ForcedAligner

    mlx_model_map = {
        "large-v3": "mlx-community/whisper-large-v3-mlx",
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "medium": "mlx-community/whisper-medium-mlx",
        "small": "mlx-community/whisper-small-mlx",
        "base": "mlx-community/whisper-base-mlx",
    }
    mlx_model = mlx_model_map.get(model_size, f"mlx-community/whisper-{model_size}")

    print(f"\n{'='*60}")
    print(f"MLX (mlx-whisper {mlx_model} + mlx-forced-aligner)")
    print(f"{'='*60}")

    times = {}

    t1 = time.time()
    whisper_result = mlx_whisper.transcribe(
        video_path, path_or_hf_repo=mlx_model, language=language,
    )
    times["transcribe"] = time.time() - t1

    t2 = time.time()
    aligner = ForcedAligner()

    segments_for_align = [
        {"start": s["start"], "end": s["end"], "text": s.get("text", "").strip()}
        for s in whisper_result["segments"]
        if s.get("text", "").strip()
    ]

    align_result = aligner.align(video_path, "", segments=segments_for_align)
    times["alignment"] = time.time() - t2
    times["total"] = times["transcribe"] + times["alignment"]

    # TranscriptionResultに変換
    segments = []
    for seg in align_result.segments:
        segments.append(TranscriptionSegment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"],
            words=seg.get("words"),
            chars=seg.get("chars"),
        ))

    tr = TranscriptionResult(
        language=language,
        segments=segments,
        original_audio_path=video_path,
        model_size=model_size,
        processing_time=times["total"],
    )

    print(f"  文字起こし: {times['transcribe']:.1f}s")
    print(f"  アライメント: {times['alignment']:.1f}s")
    print(f"  合計: {times['total']:.1f}s")
    print(f"  セグメント数: {len(segments)}")

    return tr, times


def compare(wx: TranscriptionResult, mlx: TranscriptionResult, max_segs: int = 10):
    """TranscriptionResult同士を比較"""

    print(f"\n{'='*60}")
    print("比較結果")
    print(f"{'='*60}")

    # セグメント数
    print(f"\nセグメント数: WhisperX={len(wx.segments)}, MLX={len(mlx.segments)}")

    # 速度
    print(f"処理時間:     WhisperX={wx.processing_time:.1f}s, MLX={mlx.processing_time:.1f}s")
    if wx.processing_time > 0:
        speedup = wx.processing_time / mlx.processing_time
        print(f"速度比:       MLXは{speedup:.2f}倍{'速い' if speedup > 1 else '遅い'}")

    # テキスト比較
    n = min(max_segs, len(wx.segments), len(mlx.segments))
    text_match = 0

    print(f"\n--- テキスト比較（{n}セグメント） ---")
    for i in range(n):
        wx_text = wx.segments[i].text.strip()
        mlx_text = mlx.segments[i].text.strip()
        match = wx_text == mlx_text
        if match:
            text_match += 1
        icon = "✅" if match else "❌"
        print(f"\n  [{i+1}] {icon}")
        print(f"    WX:  [{wx.segments[i].start:.1f}-{wx.segments[i].end:.1f}s] {wx_text}")
        print(f"    MLX: [{mlx.segments[i].start:.1f}-{mlx.segments[i].end:.1f}s] {mlx_text}")

    print(f"\n  テキスト一致率: {text_match}/{n} ({text_match/n*100:.0f}%)")

    # words比較
    print(f"\n--- 単語タイムスタンプ比較（最初の3セグメント） ---")
    for i in range(min(3, n)):
        wx_words = wx.segments[i].words or []
        mlx_words = mlx.segments[i].words or []

        if not wx_words or not mlx_words:
            continue

        seg_text = wx.segments[i].text.strip()[:30]
        print(f"\n  Seg{i+1}: \"{seg_text}\"")
        print(f"    WX words: {len(wx_words)}, MLX words: {len(mlx_words)}")
        print(f"    {'word':10s} {'WX_start':>9s} {'MLX_start':>9s} {'diff':>7s}  {'WX_end':>9s} {'MLX_end':>9s} {'diff':>7s}")

        for j in range(min(8, len(wx_words), len(mlx_words))):
            ww = wx_words[j]
            mw = mlx_words[j]
            # WhisperXは辞書形式
            ww_word = ww.get("word", "") if isinstance(ww, dict) else getattr(ww, "word", "")
            mw_word = mw.get("word", "") if isinstance(mw, dict) else getattr(mw, "word", "")
            ww_s = ww.get("start", 0) if isinstance(ww, dict) else getattr(ww, "start", 0)
            mw_s = mw.get("start", 0) if isinstance(mw, dict) else getattr(mw, "start", 0)
            ww_e = ww.get("end", 0) if isinstance(ww, dict) else getattr(ww, "end", 0)
            mw_e = mw.get("end", 0) if isinstance(mw, dict) else getattr(mw, "end", 0)

            word_disp = ww_word if ww_word == mw_word else f"{ww_word}/{mw_word}"
            print(f"    {word_disp:10s} {ww_s:9.3f} {mw_s:9.3f} {mw_s-ww_s:+7.3f}  {ww_e:9.3f} {mw_e:9.3f} {mw_e-ww_e:+7.3f}")

    # chars比較
    print(f"\n--- 文字タイムスタンプ比較（Seg1, 最初の15文字） ---")
    if n > 0:
        wx_chars = wx.segments[0].chars or []
        mlx_chars = mlx.segments[0].chars or []

        if wx_chars and mlx_chars:
            print(f"    WX chars: {len(wx_chars)}, MLX chars: {len(mlx_chars)}")
            print(f"    {'char':5s} {'WX_start':>9s} {'MLX_start':>9s} {'diff':>7s}  {'WX_end':>9s} {'MLX_end':>9s} {'diff':>7s}")
            for j in range(min(15, len(wx_chars), len(mlx_chars))):
                wc = wx_chars[j]
                mc = mlx_chars[j]
                wc_char = wc.get("char", "") if isinstance(wc, dict) else getattr(wc, "char", "")
                mc_char = mc.get("char", "") if isinstance(mc, dict) else getattr(mc, "char", "")
                wc_s = wc.get("start", 0) if isinstance(wc, dict) else getattr(wc, "start", 0)
                mc_s = mc.get("start", 0) if isinstance(mc, dict) else getattr(mc, "start", 0)
                wc_e = wc.get("end", 0) if isinstance(wc, dict) else getattr(wc, "end", 0)
                mc_e = mc.get("end", 0) if isinstance(mc, dict) else getattr(mc, "end", 0)

                char_disp = wc_char if wc_char == mc_char else f"{wc_char}/{mc_char}"
                print(f"    {char_disp:5s} {wc_s:9.3f} {mc_s:9.3f} {mc_s-wc_s:+7.3f}  {wc_e:9.3f} {mc_e:9.3f} {mc_e-wc_e:+7.3f}")
        else:
            wx_has = "あり" if wx_chars else "なし"
            mlx_has = "あり" if mlx_chars else "なし"
            print(f"    WX chars: {wx_has}, MLX chars: {mlx_has}")


def main():
    parser = argparse.ArgumentParser(description="WhisperX vs MLX 精度比較（TextffCut内）")
    parser.add_argument("video", help="動画ファイルパス")
    parser.add_argument("--model", default="medium", help="モデルサイズ (default: medium)")
    parser.add_argument("--max-segments", type=int, default=10, help="比較セグメント数")
    parser.add_argument("--save", type=Path, default=None, help="結果JSONを保存")
    parser.add_argument("--mlx-only", action="store_true", help="MLXのみ実行")
    parser.add_argument("--whisperx-only", action="store_true", help="WhisperXのみ実行")
    args = parser.parse_args()

    wx_result = None
    mlx_result = None
    all_times = {}

    if not args.mlx_only:
        try:
            wx_result, all_times["whisperx"] = transcribe_whisperx(args.video, args.model)
        except ImportError as e:
            print(f"WhisperXが利用不可: {e}")
        except Exception as e:
            print(f"WhisperXエラー: {e}")
            import traceback
            traceback.print_exc()

    if not args.whisperx_only:
        try:
            mlx_result, all_times["mlx"] = transcribe_mlx(args.video, args.model)
        except ImportError as e:
            print(f"MLXが利用不可: {e}")
        except Exception as e:
            print(f"MLXエラー: {e}")
            import traceback
            traceback.print_exc()

    if wx_result and mlx_result:
        compare(wx_result, mlx_result, args.max_segments)

    if args.save and (wx_result or mlx_result):
        save_data = {"times": all_times}
        if wx_result:
            save_data["whisperx"] = wx_result.to_dict()
        if mlx_result:
            save_data["mlx"] = mlx_result.to_dict()
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"\n結果を保存: {args.save}")


if __name__ == "__main__":
    main()
