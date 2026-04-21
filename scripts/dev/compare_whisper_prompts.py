"""Whisper の initial_prompt 改善の A/B/C 比較スクリプト。

同じ音声サンプルを 3種類の prompt で文字起こしして、
フィラー捕捉数・総文字数・処理時間を比較する。

使い方:
    python scripts/dev/compare_whisper_prompts.py [音声ファイル]

デフォルト: /tmp/whisper_test/sample.wav
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


PROMPTS = {
    "A_baseline": "えー、あの、えーと、まあ、なんか、うーん、まぁ、んー、えっと、そうですね",
    "B_natural": (
        "以下は話し言葉のインタビュー録音です。間投詞（えー、あー、うーん、あのー、えーっと、なんか、まあ）や"
        "言い淀みも省略せずそのまま正確に書き起こしてください。"
    ),
    "C_longvowel": (
        "えーっと、えーと、えー、あのー、あの、うーん、うーんと、なんか、"
        "なんかその、まあ、まぁ、んー、んーと、あー、そうですね"
    ),
    "D_combined": (
        "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに書き起こしてください。"
        "例: えーっと、えー、あのー、あの、うーん、うーんと、なんか、なんかその、"
        "まあ、まぁ、んー、あー、そうですね"
    ),
}

# 検出したいフィラーパターン（重複を避けるため長い順）
FILLER_PATTERNS = [
    "えーっと",
    "えっとね",
    "えーと",
    "えっと",
    "あのー",
    "うーんと",
    "うーん",
    "えー",
    "あー",
    "あの",
    "まあ",
    "まぁ",
    "んー",
    "なんか",
    "やっぱり",
    "やっぱ",
    "そうですね",
]


def count_fillers(text: str) -> tuple[int, Counter]:
    """テキスト中のフィラー出現数を数える（長い順に貪欲マッチ）。"""
    counter: Counter = Counter()
    total = 0
    i = 0
    while i < len(text):
        matched = None
        for f in FILLER_PATTERNS:
            if text[i : i + len(f)] == f:
                matched = f
                break
        if matched:
            counter[matched] += 1
            total += 1
            i += len(matched)
        else:
            i += 1
    return total, counter


def run_once(audio_path: Path, prompt: str, model: str = "medium") -> dict:
    """1回 Whisper を実行して結果を返す。"""
    import mlx_whisper

    mlx_model = f"mlx-community/whisper-{model}"
    t0 = time.perf_counter()
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=mlx_model,
        language="ja",
        initial_prompt=prompt,
    )
    elapsed = time.perf_counter() - t0

    segments = result.get("segments", [])
    full_text = "".join(s.get("text", "") for s in segments)
    total_fillers, counter = count_fillers(full_text)

    return {
        "elapsed_sec": elapsed,
        "n_segments": len(segments),
        "total_chars": len(full_text),
        "total_fillers": total_fillers,
        "filler_counter": dict(counter),
        "sample_texts": [s.get("text", "")[:60] for s in segments[:5]],
    }


def main() -> None:
    audio_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/whisper_test/sample.wav")
    if not audio_path.exists():
        print(f"ERROR: {audio_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"入力: {audio_path}")
    print(f"モデル: mlx-community/whisper-medium")
    print()

    results: dict[str, dict] = {}
    for name, prompt in PROMPTS.items():
        print(f"--- {name} ---")
        print(f"prompt: {prompt[:80]}...")
        try:
            res = run_once(audio_path, prompt)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        results[name] = res
        print(
            f"  {res['elapsed_sec']:.1f}s / {res['n_segments']}seg / "
            f"{res['total_chars']}字 / フィラー{res['total_fillers']}個"
        )
        print()

    # 比較サマリ
    print("=" * 70)
    print("【サマリ】フィラー種別ごとの検出数")
    print(f"{'filler':<12s}  " + "  ".join(f"{n:>12s}" for n in results))
    all_fillers = set()
    for r in results.values():
        all_fillers.update(r.get("filler_counter", {}).keys())
    for f in sorted(all_fillers):
        row = [f"{r.get('filler_counter', {}).get(f, 0):>12d}" for r in results.values()]
        print(f"{f:<12s}  " + "  ".join(row))

    print()
    print(f"{'合計フィラー':<12s}  " + "  ".join(f"{r['total_fillers']:>12d}" for r in results.values()))
    print(f"{'総文字数':<12s}  " + "  ".join(f"{r['total_chars']:>12d}" for r in results.values()))
    print(f"{'処理秒数':<12s}  " + "  ".join(f"{r['elapsed_sec']:>12.1f}" for r in results.values()))

    # JSON 保存
    out_json = audio_path.parent / "comparison_result.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n詳細: {out_json}")


if __name__ == "__main__":
    main()
