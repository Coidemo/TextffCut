"""Hybrid ASR + ForcedAligner 検証スクリプト

gpt-4o-mini-transcribe で文字起こし → mlx-forced-aligner で文字レベル
アライメントが取れるかを実証する。

実行:
  python scripts/dev/validate_hybrid_asr_aligner.py
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from openai import OpenAI  # noqa: E402
from utils.api_key_manager import api_key_manager  # noqa: E402


FILLER_PATTERNS = sorted(
    [
        "えーっと",
        "えっとね",
        "えーと",
        "えっと",
        "あのー",
        "うーんと",
        "うーん",
        "なんかその",
        "なんかこう",
        "なんか",
        "あのね",
        "あの",
        "まあその",
        "まあね",
        "まあまあ",
        "まあ",
        "まぁ",
        "えー",
        "あー",
        "んー",
        "やっぱり",
        "やっぱ",
        "そうですね",
        "でまあ",
        "でなんか",
        "であの",
        "でその",
    ],
    key=len,
    reverse=True,
)


def count_fillers(text: str) -> Counter:
    c: Counter = Counter()
    i = 0
    while i < len(text):
        for f in FILLER_PATTERNS:
            if text[i : i + len(f)] == f:
                c[f] += 1
                i += len(f)
                break
        else:
            i += 1
    return c


def main() -> None:
    audio_path = Path("/tmp/ground_truth/audio.wav")

    # --- Step 1: gpt-4o-mini-transcribe で verbose_json で segments 取得 ---
    print("Step 1: gpt-4o-mini-transcribe で文字起こし...")
    api_key = api_key_manager.load_api_key()
    client = OpenAI(api_key=api_key)

    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=f,
            language="ja",
            response_format="json",
            prompt=(
                "以下は話し言葉のインタビューです。間投詞（えーっと、あのー、うーん、"
                "なんか、まあ等）も省略せずそのまま書き起こしてください。"
            ),
        )
    step1_elapsed = time.perf_counter() - t0
    full_text = resp.text
    print(f"  完了 ({step1_elapsed:.1f}s): {len(full_text)}字")
    print(f"  冒頭: {full_text[:150]}")

    fillers_in_text = count_fillers(full_text)
    print(f"  フィラー数: {sum(fillers_in_text.values())} {dict(fillers_in_text)}")
    print()

    # --- Step 2: ForcedAligner に渡す ---
    print("Step 2: mlx-forced-aligner でアライメント...")
    try:
        from mlx_forced_aligner import ForcedAligner
    except ImportError as e:
        print(f"  FAILED: mlx-forced-aligner 未インストール: {e}")
        sys.exit(1)

    t0 = time.perf_counter()
    aligner = ForcedAligner()

    # full_text を1セグメントとして渡す（audio全体: 0-120s）
    segments_for_align = [{"start": 0.0, "end": 120.0, "text": full_text}]

    try:
        result = aligner.align(str(audio_path), "", segments=segments_for_align)
        step2_elapsed = time.perf_counter() - t0
        print(f"  完了 ({step2_elapsed:.1f}s)")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # 結果を検証
    print()
    print(f"アラインメント結果: {len(result.segments)} セグメント")
    total_words = sum(len(s.get("words", []) or []) for s in result.segments)
    total_chars = sum(len(s.get("chars", []) or []) for s in result.segments)
    print(f"  合計 words: {total_words}")
    print(f"  合計 chars: {total_chars}")

    # 最初のセグメントの中身を確認
    if result.segments:
        s = result.segments[0]
        print()
        print(f"--- 最初のセグメント ---")
        print(f"  text: {s.get('text', '')[:100]}")
        words = s.get("words") or []
        chars = s.get("chars") or []
        print(f"  words 数: {len(words)}")
        print(f"  chars 数: {len(chars)}")
        if words[:5]:
            print(f"  最初の5 words:")
            for w in words[:5]:
                w_text = w.get("word", "?") if isinstance(w, dict) else getattr(w, "word", "?")
                w_start = w.get("start", 0) if isinstance(w, dict) else getattr(w, "start", 0)
                w_end = w.get("end", 0) if isinstance(w, dict) else getattr(w, "end", 0)
                print(f"    {w_text:>6}  [{w_start:.2f} - {w_end:.2f}]")
        if chars[:10]:
            print(f"  最初の10 chars:")
            for c in chars[:10]:
                c_text = c.get("char", "?") if isinstance(c, dict) else getattr(c, "char", "?")
                c_start = c.get("start", 0) if isinstance(c, dict) else getattr(c, "start", 0)
                c_end = c.get("end", 0) if isinstance(c, dict) else getattr(c, "end", 0)
                print(f"    {c_text:>3}  [{c_start:.2f} - {c_end:.2f}]")

    # --- Step 3: アライメントの健全性チェック ---
    print()
    print("Step 3: アライメントの健全性チェック")
    all_chars = []
    for s in result.segments:
        all_chars.extend(s.get("chars") or [])

    if all_chars:
        times = []
        for c in all_chars:
            start = c.get("start", 0) if isinstance(c, dict) else getattr(c, "start", 0)
            end = c.get("end", 0) if isinstance(c, dict) else getattr(c, "end", 0)
            times.append((start, end))

        first_t = times[0]
        last_t = times[-1]
        print(f"  最初の文字: [{first_t[0]:.2f} - {first_t[1]:.2f}]")
        print(f"  最後の文字: [{last_t[0]:.2f} - {last_t[1]:.2f}]")
        print(f"  全体の duration: {last_t[1] - first_t[0]:.1f}s (音声: 120s)")

        # 単調性チェック
        non_monotonic = sum(1 for i in range(1, len(times)) if times[i][0] < times[i - 1][0])
        print(f"  時刻の非単調 occurrences: {non_monotonic} ({non_monotonic / len(times) * 100:.0f}%)")

        # 異常に長い char (>2秒)
        long_chars = sum(1 for s, e in times if e - s > 2.0)
        print(f"  2秒超の char: {long_chars}")

        # ゼロ幅 char
        zero_chars = sum(1 for s, e in times if e - s == 0)
        print(f"  ゼロ幅 char: {zero_chars}")


if __name__ == "__main__":
    main()
