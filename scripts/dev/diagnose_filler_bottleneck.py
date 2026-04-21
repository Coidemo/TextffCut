"""Ground truth（人間による正確な書き起こし）とパイプライン各層を比較し、
フィラー検出のボトルネックを特定する。

前提ファイル:
  /tmp/ground_truth/audio.wav          音声サンプル
  /tmp/ground_truth/whisper_raw.txt    Whisper の出力（加筆前）
  /tmp/ground_truth/ground_truth.txt   ユーザー加筆版（要作成）

使い方:
  python scripts/dev/diagnose_filler_bottleneck.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# フィラー検出パターン（長い順に貪欲マッチ）
FILLER_PATTERNS = sorted(
    [
        "えーっと", "えっとね", "えーと", "えっと",
        "あのー", "うーんと", "うーん",
        "なんかその", "なんかこう", "なんか",
        "あのね", "あの",
        "まあその", "まあね", "まあまあ", "まあ", "まぁ",
        "えー", "あー", "んー",
        "やっぱり", "やっぱ",
        "そうですね",
        "でまあ", "でなんか", "であの", "でその",
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


def parse_timestamped_text(path: Path) -> str:
    """テンプレ形式 ([秒.秒秒] テキスト) から純テキストを抽出。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    texts = []
    for ln in lines:
        if ln.startswith("#") or not ln.strip():
            continue
        m = re.match(r"^\s*\[\s*[\d.]+\s*\]\s*(.*)$", ln)
        if m:
            texts.append(m.group(1).strip())
        else:
            texts.append(ln.strip())
    return "\n".join(t for t in texts if t)


def main() -> None:
    whisper_path = Path("/tmp/ground_truth/whisper_raw.txt")
    ground_truth_path = Path("/tmp/ground_truth/ground_truth.txt")

    if not whisper_path.exists():
        print(f"ERROR: {whisper_path} が見つかりません", file=sys.stderr)
        sys.exit(1)
    if not ground_truth_path.exists():
        print(f"ERROR: {ground_truth_path} が見つかりません", file=sys.stderr)
        print(
            "テンプレ /tmp/ground_truth/template.txt にフィラーを加筆して\n"
            "/tmp/ground_truth/ground_truth.txt として保存してから実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    whisper_text = parse_timestamped_text(whisper_path)
    ground_text = parse_timestamped_text(ground_truth_path)

    whisper_fillers = count_fillers(whisper_text)
    ground_fillers = count_fillers(ground_text)

    # Phase 0 で検出できる語リスト（filler_constants.py を参照）
    from use_cases.ai.filler_constants import AMBIGUOUS_FILLERS
    from use_cases.ai.filler_constants import FILLER_WORDS as PURE

    phase0_vocab = set(PURE) | AMBIGUOUS_FILLERS

    # Phase 0 の検出シミュレーション: Whisperテキストにあって、
    # かつ phase0_vocab に含まれる語のみ検出される想定
    # （実際は GiNZA 判定等で減るがここは語彙カバレッジだけ確認）
    phase0_detected: Counter = Counter()
    for f, n in whisper_fillers.items():
        if f in phase0_vocab:
            phase0_detected[f] = n

    # 総件数
    total_gt = sum(ground_fillers.values())
    total_whisper = sum(whisper_fillers.values())
    total_phase0 = sum(phase0_detected.values())

    whisper_capture_rate = total_whisper / total_gt * 100 if total_gt else 0
    phase0_detect_rate = total_phase0 / total_whisper * 100 if total_whisper else 0
    overall_removal_rate = total_phase0 / total_gt * 100 if total_gt else 0

    print("=" * 70)
    print("フィラー検出ボトルネック診断レポート")
    print("=" * 70)
    print()
    print(f"ground truth のフィラー総数: {total_gt:>4}")
    print(f"Whisper 捕捉:             {total_whisper:>4}  ({whisper_capture_rate:.0f}%)")
    print(f"Phase 0 語彙マッチ:        {total_phase0:>4}  ({phase0_detect_rate:.0f}% of Whisper)")
    print(f"総合除去見込み:            {total_phase0:>4}  ({overall_removal_rate:.0f}% of ground truth)")
    print()
    print("-" * 70)
    print("ボトルネック別の漏れ")
    print("-" * 70)
    whisper_miss = total_gt - total_whisper
    phase0_miss = total_whisper - total_phase0
    print(f"Whisper 取りこぼし: {whisper_miss} 件 (Whisperがテキスト化しなかったフィラー)")
    print(f"Phase 0 未登録語:   {phase0_miss} 件 (Whisperがキャプチャしたが語彙リスト外)")
    print()
    print("-" * 70)
    print("フィラー別: ground truth / Whisper / Phase 0 語彙マッチ")
    print("-" * 70)
    all_fillers = set(ground_fillers) | set(whisper_fillers)
    print(f"{'filler':<12s}  {'GT':>4s}  {'Whisper':>8s}  {'Phase0語彙':>10s}  {'備考':s}")
    for f in sorted(all_fillers, key=lambda x: -ground_fillers.get(x, 0)):
        gt = ground_fillers.get(f, 0)
        wh = whisper_fillers.get(f, 0)
        p0 = phase0_detected.get(f, 0)
        note = ""
        if f not in phase0_vocab:
            note = "❌ Phase 0 未登録"
        elif wh < gt:
            note = f"⚠ Whisper漏れ {gt - wh}件"
        elif wh > 0:
            note = "✓"
        print(f"{f:<12s}  {gt:>4}  {wh:>8}  {p0:>10}  {note}")

    print()
    print("-" * 70)
    print("テキスト比較（冒頭300字）")
    print("-" * 70)
    print(f"[Whisper]\n{whisper_text[:300]}")
    print()
    print(f"[Ground Truth]\n{ground_text[:300]}")


if __name__ == "__main__":
    main()
