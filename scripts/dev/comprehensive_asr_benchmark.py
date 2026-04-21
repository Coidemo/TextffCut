"""複数のASRモデル・組み合わせを包括的に比較。

測定指標:
  1. フィラー捕捉率 (vs ground truth)
  2. 文字正確性 (CER: Character Error Rate)
  3. 固有名詞正確性 (手動リスト照合)
  4. 処理時間
  5. コスト見積
  6. ForcedAligner互換性

実行:
  python scripts/dev/comprehensive_asr_benchmark.py
"""

from __future__ import annotations

import base64
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from openai import OpenAI  # noqa: E402
from utils.api_key_manager import api_key_manager  # noqa: E402


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
    key=len, reverse=True,
)

# 固有名詞と専門用語（正しく認識されるべき語）
PROPER_NOUNS = [
    "尾原",        # 人名（小原は誤認識、どちらかOK）
    "深津",        # 人名（復活は誤認識）
    "ナイジェル",  # Nigel
    "ハワード",    # Howard
    "ジョージ",    # George
    "ソロス",      # Soros
    "メタゲーム",  # concept
    "ディープリサーチ",
    "生成AI",
    "再帰",        # 再帰性 or 再帰省（どちらかは聞けば分かる）
    "SNS",         # 大文字小文字差異あり
    "1971",
    "1980年代",
    "多岐",        # 多機は誤認識
]


@dataclass
class ASRResult:
    label: str
    text: str
    elapsed_sec: float
    cost_usd: float = 0.0
    aligner_ok: bool = False
    aligner_chars: int = 0
    note: str = ""


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


def normalize_for_cer(text: str) -> str:
    """CER計算のためにテキストを正規化。"""
    # 句読点・空白除去
    text = re.sub(r"[、。！？\s\n]+", "", text)
    # 全角半角統一
    text = text.lower()
    return text


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate (正規化後)。低いほど良い。"""
    ref = normalize_for_cer(reference)
    hyp = normalize_for_cer(hypothesis)
    if not ref:
        return 0.0
    sm = SequenceMatcher(None, ref, hyp)
    ratio = sm.ratio()  # 類似度 0-1
    return 1 - ratio


def count_proper_nouns(text: str) -> int:
    """固有名詞リストに含まれる語の出現数。"""
    return sum(1 for noun in PROPER_NOUNS if noun in text)


def parse_ts(path: Path) -> str:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        m = re.match(r"^\s*\[\s*[\d.]+\s*\]\s*(.*)$", ln)
        if m:
            out.append(m.group(1).strip())
    return "\n".join(out)


# ----------------------------------------------------------------------
# ASR 実装各種
# ----------------------------------------------------------------------


def run_mlx(audio_path: Path, model: str) -> ASRResult:
    import mlx_whisper

    mlx_model = f"mlx-community/whisper-{model}"
    if model == "large-v3":
        mlx_model = "mlx-community/whisper-large-v3-mlx"
    elif model == "medium":
        mlx_model = "mlx-community/whisper-medium-mlx"

    prompt = (
        "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに書き起こしてください。"
        "例: えーっと、えー、あのー、あの、うーん、うーんと、なんか、なんかその、"
        "まあ、まぁ、んー、あー、そうですね"
    )
    t0 = time.perf_counter()
    result = mlx_whisper.transcribe(
        str(audio_path), path_or_hf_repo=mlx_model, language="ja", initial_prompt=prompt
    )
    elapsed = time.perf_counter() - t0
    text = "".join(s.get("text", "") for s in result.get("segments", []))
    return ASRResult(label=f"MLX-{model}", text=text, elapsed_sec=elapsed, cost_usd=0.0)


def run_openai_transcribe(client: OpenAI, audio_path: Path, model: str, cost_per_min: float) -> ASRResult:
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=model,
            file=f,
            language="ja",
            response_format="text",
            prompt=(
                "以下は話し言葉のインタビューです。間投詞（えーっと、あのー、うーん、"
                "なんか、まあ等）も省略せずそのまま書き起こしてください。"
            ),
        )
    elapsed = time.perf_counter() - t0
    duration_min = 2.0  # 2分サンプル前提
    return ASRResult(
        label=model, text=str(resp), elapsed_sec=elapsed, cost_usd=cost_per_min * duration_min
    )


def run_gpt4o_audio_direct(client: OpenAI, audio_path: Path) -> ASRResult:
    """gpt-4o-audio-preview で直接文字起こし。"""
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("ascii")
    resp = client.chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "この音声を正確に日本語で書き起こしてください。"
                    "間投詞（えーっと、あのー、うーん、なんか、まあ等）"
                    "も省略せずそのまま含めてください。書き起こしテキストのみ返してください。"
                )},
                {"type": "input_audio", "input_audio": {"data": audio_data, "format": "wav"}},
            ],
        }],
        temperature=0.0,
    )
    elapsed = time.perf_counter() - t0
    text = resp.choices[0].message.content or ""
    # cost: 音声入力 $100/1M tokens, 約 100 tokens/分 → $0.02 / 2分
    return ASRResult(label="gpt-4o-audio-direct", text=text, elapsed_sec=elapsed, cost_usd=0.20)


def run_refine(client: OpenAI, audio_path: Path, base_text: str, label: str) -> ASRResult:
    """gpt-4o-audio-preview で既存テキストにフィラー補完。"""
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("ascii")
    prompt = f"""以下は日本語のインタビュー音声と、それを書き起こしたテキストです。

このテキストは正しい部分が多いが、間投詞（えー、あー、あのー、うーん、なんか、まあ等）を
取りこぼしている可能性があります。音声をよく聞いて、**欠落しているフィラーだけ** を
正確な位置に補完した完全な書き起こしを返してください。

# 重要
- 既存のテキストの内容は変更しないでください（補完のみ）
- 新しい単語を創作しないでください
- 結果テキストのみ返してください

# 既存テキスト
{base_text[:2000]}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "input_audio", "input_audio": {"data": audio_data, "format": "wav"}},
            ],
        }],
        temperature=0.0,
    )
    elapsed = time.perf_counter() - t0
    return ASRResult(
        label=label, text=resp.choices[0].message.content or "", elapsed_sec=elapsed, cost_usd=0.25
    )


def test_aligner(audio_path: Path, text: str) -> tuple[bool, int]:
    """ForcedAligner で alignment が取れるかテスト。"""
    try:
        from mlx_forced_aligner import ForcedAligner

        aligner = ForcedAligner()
        segments = [{"start": 0.0, "end": 120.0, "text": text}]
        result = aligner.align(str(audio_path), "", segments=segments)
        total_chars = sum(len(s.get("chars") or []) for s in result.segments)
        return True, total_chars
    except Exception as e:
        return False, 0


# ----------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------


def main() -> None:
    audio_path = Path("/tmp/ground_truth/audio.wav")
    gt_path = Path("/tmp/ground_truth/ground_truth.txt")

    if not audio_path.exists() or not gt_path.exists():
        print("ERROR: ファイル不足", file=sys.stderr)
        sys.exit(1)

    gt_text = parse_ts(gt_path)
    gt_fillers = count_fillers(gt_text)
    total_gt = sum(gt_fillers.values())
    gt_proper = count_proper_nouns(gt_text)

    print(f"Ground Truth: {len(gt_text)}字, フィラー {total_gt}件, 固有名詞 {gt_proper}/{len(PROPER_NOUNS)}")
    print()

    api_key = api_key_manager.load_api_key()
    client = OpenAI(api_key=api_key)

    results: list[ASRResult] = []

    # --- 直接文字起こし系 ---
    print("## 直接文字起こし")
    for model in ["medium", "large-v3-turbo", "large-v3"]:
        try:
            print(f"  MLX-{model} 実行中...", end=" ", flush=True)
            r = run_mlx(audio_path, model)
            results.append(r)
            print(f"{r.elapsed_sec:.1f}s / {len(r.text)}字")
        except Exception as e:
            print(f"FAILED: {e}")

    for model, cost in [("whisper-1", 0.006), ("gpt-4o-transcribe", 0.006), ("gpt-4o-mini-transcribe", 0.003)]:
        try:
            print(f"  {model} 実行中...", end=" ", flush=True)
            r = run_openai_transcribe(client, audio_path, model, cost)
            results.append(r)
            print(f"{r.elapsed_sec:.1f}s / {len(r.text)}字")
        except Exception as e:
            print(f"FAILED: {e}")

    try:
        print(f"  gpt-4o-audio-direct 実行中...", end=" ", flush=True)
        r = run_gpt4o_audio_direct(client, audio_path)
        results.append(r)
        print(f"{r.elapsed_sec:.1f}s / {len(r.text)}字")
    except Exception as e:
        print(f"FAILED: {e}")

    # --- 組み合わせ: X → gpt-4o-audio refine ---
    print()
    print("## Refine 組み合わせ")
    for base in list(results):  # list()で固定（後から追加される分は含めない）
        if "refine" in base.label:
            continue
        if base.label in ("MLX-medium", "gpt-4o-mini-transcribe"):
            try:
                print(f"  {base.label} → refine 実行中...", end=" ", flush=True)
                r = run_refine(client, audio_path, base.text, f"{base.label} → refine")
                r.cost_usd += base.cost_usd
                results.append(r)
                print(f"{r.elapsed_sec:.1f}s / {len(r.text)}字")
            except Exception as e:
                print(f"FAILED: {e}")

    # --- ForcedAligner テスト（重要）---
    print()
    print("## ForcedAligner 互換性テスト")
    for r in results:
        try:
            ok, nchars = test_aligner(audio_path, r.text)
            r.aligner_ok = ok
            r.aligner_chars = nchars
            status = f"✓ {nchars}chars" if ok else "✗"
            print(f"  {r.label:<40}: {status}")
        except Exception as e:
            r.aligner_ok = False
            print(f"  {r.label:<40}: ERROR ({e})")

    # --- 評価 ---
    print()
    print("=" * 90)
    print("包括評価")
    print("=" * 90)

    header = f"{'label':<35} {'字数':>5} {'CER':>6} {'filler':>6} {'捕捉率':>7} {'固有名詞':>8} {'時間':>6} {'コスト':>7} {'aligner':>8}"
    print(header)
    print("-" * len(header))

    for r in results:
        fillers = count_fillers(r.text)
        n_fillers = sum(fillers.values())
        c_rate = n_fillers / total_gt * 100 if total_gt else 0
        err = cer(gt_text, r.text) * 100
        nouns = count_proper_nouns(r.text)
        align = f"{r.aligner_chars}字" if r.aligner_ok else "✗"
        print(f"{r.label:<35} {len(r.text):>5} {err:>5.1f}% {n_fillers:>6} {c_rate:>6.0f}% {nouns:>4}/{len(PROPER_NOUNS):<3} {r.elapsed_sec:>5.1f}s ${r.cost_usd:>5.3f}  {align:>8}")

    # --- フィラー別詳細 ---
    print()
    print("-" * 90)
    print("フィラー別の捕捉数")
    print("-" * 90)
    all_f = set(gt_fillers.keys())
    for r in results:
        all_f.update(count_fillers(r.text).keys())
    print(f"{'filler':<10} GT   " + "  ".join(f"{r.label[:8]:>8}" for r in results[:8]))
    for f in sorted(all_f, key=lambda x: -gt_fillers.get(x, 0)):
        row = [f"{count_fillers(r.text).get(f, 0):>8d}" for r in results[:8]]
        print(f"{f:<10} {gt_fillers.get(f, 0):<3}  " + "  ".join(row))


if __name__ == "__main__":
    main()
