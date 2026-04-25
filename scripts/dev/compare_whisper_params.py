"""Whisper のパラメタ変種を ground truth に対して比較し、
フィラー捕捉率を最大化する設定を探す。

前提:
  /tmp/ground_truth/audio.wav
  /tmp/ground_truth/ground_truth.txt (ユーザー加筆済み)

実行:
  python scripts/dev/compare_whisper_params.py
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# 共通 initial_prompt（本体と同じ）
INITIAL_PROMPT = (
    "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに書き起こしてください。"
    "例: えーっと、えー、あのー、あの、うーん、うーんと、なんか、なんかその、"
    "まあ、まぁ、んー、あー、そうですね"
)

# 変種パラメタ
VARIANTS = {
    "A_baseline": {},  # デフォルト
    "B_no_condition": {"condition_on_previous_text": False},
    "C_low_no_speech": {"no_speech_threshold": 0.3},
    "D_B_plus_C": {"condition_on_previous_text": False, "no_speech_threshold": 0.3},
    "E_temperature_fallback": {"temperature": (0.0, 0.2, 0.4)},
    "F_all_combined": {
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.3,
        "temperature": (0.0, 0.2, 0.4),
    },
}

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
    counter: Counter = Counter()
    i = 0
    while i < len(text):
        for f in FILLER_PATTERNS:
            if text[i : i + len(f)] == f:
                counter[f] += 1
                i += len(f)
                break
        else:
            i += 1
    return counter


def parse_timestamped(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    texts = []
    for ln in lines:
        if ln.startswith("#") or not ln.strip():
            continue
        m = re.match(r"^\s*\[\s*[\d.]+\s*\]\s*(.*)$", ln)
        if m:
            texts.append(m.group(1).strip())
    return "\n".join(texts)


def run_variant(audio_path: Path, params: dict) -> dict:
    import mlx_whisper

    t0 = time.perf_counter()
    kwargs = {
        "path_or_hf_repo": "mlx-community/whisper-medium",
        "language": "ja",
        "initial_prompt": INITIAL_PROMPT,
        **params,
    }
    result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    elapsed = time.perf_counter() - t0

    segments = result.get("segments", [])
    full_text = "".join(s.get("text", "") for s in segments)
    return {
        "elapsed": elapsed,
        "text": full_text,
        "n_segments": len(segments),
        "fillers": count_fillers(full_text),
    }


def main() -> None:
    audio_path = Path("/tmp/ground_truth/audio.wav")
    gt_path = Path("/tmp/ground_truth/ground_truth.txt")
    if not audio_path.exists() or not gt_path.exists():
        print("ERROR: ground truth ファイルが見つかりません", file=sys.stderr)
        sys.exit(1)

    gt_text = parse_timestamped(gt_path)
    gt_fillers = count_fillers(gt_text)
    total_gt = sum(gt_fillers.values())

    print(f"Ground Truth フィラー総数: {total_gt}")
    print(f"  内訳: {dict(gt_fillers)}")
    print()

    results = {}
    for name, params in VARIANTS.items():
        print(f"--- {name} ---")
        print(f"  params: {params}")
        res = run_variant(audio_path, params)
        res["total"] = sum(res["fillers"].values())
        res["recall"] = res["total"] / total_gt * 100 if total_gt else 0
        results[name] = res
        print(
            f"  {res['elapsed']:.1f}s / {res['n_segments']}seg / "
            f"フィラー {res['total']}件 / 捕捉率 {res['recall']:.0f}%"
        )
        print()

    # サマリ表
    print("=" * 70)
    print("サマリ")
    print("=" * 70)
    all_fillers = set()
    for r in results.values():
        all_fillers.update(r["fillers"].keys())
    all_fillers.update(gt_fillers.keys())

    print(f"{'filler':<12s}  {'GT':>3s}  " + "  ".join(f"{n:>10s}" for n in results))
    for f in sorted(all_fillers, key=lambda x: -gt_fillers.get(x, 0)):
        gt = gt_fillers.get(f, 0)
        row = [f"{r['fillers'].get(f, 0):>10d}" for r in results.values()]
        print(f"{f:<12s}  {gt:>3}  " + "  ".join(row))

    print()
    print(f"{'合計':<12s}  {total_gt:>3}  " + "  ".join(f"{r['total']:>10d}" for r in results.values()))
    print(f"{'捕捉率':<12s}  {'':>3}  " + "  ".join(f"{r['recall']:>9.0f}%" for r in results.values()))
    print(f"{'処理秒':<12s}  {'':>3}  " + "  ".join(f"{r['elapsed']:>10.1f}" for r in results.values()))


if __name__ == "__main__":
    main()
