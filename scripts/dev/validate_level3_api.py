"""Level 3 (Post-Whisper LLM) の効果を検証する。

複数のOpenAI API を使って ground truth と比較し、フィラー捕捉率を測定。

実行:
  python scripts/dev/validate_level3_api.py
"""

from __future__ import annotations

import base64
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


def parse_ts(path: Path) -> str:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        m = re.match(r"^\s*\[\s*[\d.]+\s*\]\s*(.*)$", ln)
        if m:
            out.append(m.group(1).strip())
    return "\n".join(out)


def run_whisper_1(client: OpenAI, audio_path: Path) -> tuple[str, float]:
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ja",
            response_format="text",
            prompt=(
                "以下は話し言葉のインタビューです。間投詞（えーっと、あのー、うーん、なんか、まあ等）"
                "も省略せずそのまま書き起こしてください。"
            ),
        )
    return str(resp), time.perf_counter() - t0


def run_gpt4o_transcribe(client: OpenAI, audio_path: Path, model: str = "gpt-4o-transcribe") -> tuple[str, float]:
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=model,
            file=f,
            language="ja",
            response_format="text",
            prompt=(
                "以下は話し言葉のインタビューです。間投詞（えーっと、あのー、うーん、なんか、まあ等）"
                "も省略せずそのまま書き起こしてください。"
            ),
        )
    return str(resp), time.perf_counter() - t0


def run_gpt4o_audio_refine(client: OpenAI, audio_path: Path, whisper_text: str) -> tuple[str, float]:
    """gpt-4o-audio-preview に音声 + Whisper出力を渡してフィラー補完させる。"""
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("ascii")

    prompt = f"""以下は日本語のインタビュー音声と、Whisperによる仮の書き起こしテキストです。

Whisperは「えー」「あー」「あのー」「うーん」「なんか」「まあ」などのフィラーを
取りこぼすことがあります。音声をよく聞いて、Whisperのテキストに加えて
**聞き取れるが欠落しているフィラー** を補完した完全な書き起こしを返してください。

# 重要
- Whisperのテキストはおおむね正しいのでほぼそのまま保持してください
- フィラーの追加のみに集中してください
- 新しい単語を創作しないでください
- 結果テキストのみ返してください（説明不要）

# Whisperの出力
{whisper_text[:2000]}
"""

    resp = client.chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_data, "format": "wav"},
                    },
                ],
            }
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content or "", time.perf_counter() - t0


def main() -> None:
    audio_path = Path("/tmp/ground_truth/audio.wav")
    gt_path = Path("/tmp/ground_truth/ground_truth.txt")
    wh_path = Path("/tmp/ground_truth/whisper_raw.txt")

    if not all(p.exists() for p in (audio_path, gt_path, wh_path)):
        print("ERROR: 必要なファイルがない", file=sys.stderr)
        sys.exit(1)

    api_key = api_key_manager.load_api_key()
    client = OpenAI(api_key=api_key)

    gt_text = parse_ts(gt_path)
    gt_fillers = count_fillers(gt_text)
    total_gt = sum(gt_fillers.values())

    whisper_local_text = parse_ts(wh_path)
    wh_local_fillers = count_fillers(whisper_local_text)
    total_wh_local = sum(wh_local_fillers.values())

    print(f"Ground Truth フィラー総数: {total_gt}件 {dict(gt_fillers)}")
    print(f"MLX Whisper medium (既知): {total_wh_local}件 {dict(wh_local_fillers)}")
    print()

    results: dict[str, dict] = {
        "MLX_medium": {
            "total": total_wh_local,
            "fillers": wh_local_fillers,
            "elapsed": 0.0,
            "text": whisper_local_text,
        },
    }

    # whisper-1
    print("--- whisper-1 (OpenAI) ---")
    try:
        text, elapsed = run_whisper_1(client, audio_path)
        f = count_fillers(text)
        results["whisper-1"] = {"total": sum(f.values()), "fillers": f, "elapsed": elapsed, "text": text}
        print(f"  {elapsed:.1f}s / フィラー {sum(f.values())}件 / 捕捉率 {sum(f.values())/total_gt*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

    # gpt-4o-transcribe
    print("--- gpt-4o-transcribe ---")
    try:
        text, elapsed = run_gpt4o_transcribe(client, audio_path, "gpt-4o-transcribe")
        f = count_fillers(text)
        results["gpt-4o-transcribe"] = {"total": sum(f.values()), "fillers": f, "elapsed": elapsed, "text": text}
        print(f"  {elapsed:.1f}s / フィラー {sum(f.values())}件 / 捕捉率 {sum(f.values())/total_gt*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

    # gpt-4o-mini-transcribe
    print("--- gpt-4o-mini-transcribe ---")
    try:
        text, elapsed = run_gpt4o_transcribe(client, audio_path, "gpt-4o-mini-transcribe")
        f = count_fillers(text)
        results["gpt-4o-mini-transcribe"] = {
            "total": sum(f.values()),
            "fillers": f,
            "elapsed": elapsed,
            "text": text,
        }
        print(f"  {elapsed:.1f}s / フィラー {sum(f.values())}件 / 捕捉率 {sum(f.values())/total_gt*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

    # gpt-4o-audio-preview: Whisperテキスト + 音声で補完
    print("--- gpt-4o-audio-preview (Whisper + refine) ---")
    try:
        text, elapsed = run_gpt4o_audio_refine(client, audio_path, whisper_local_text)
        f = count_fillers(text)
        results["gpt-4o-audio-refine"] = {
            "total": sum(f.values()),
            "fillers": f,
            "elapsed": elapsed,
            "text": text,
        }
        print(f"  {elapsed:.1f}s / フィラー {sum(f.values())}件 / 捕捉率 {sum(f.values())/total_gt*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

    # サマリ
    print("=" * 80)
    print("サマリ")
    print("=" * 80)
    all_f = set(gt_fillers.keys())
    for r in results.values():
        all_f.update(r["fillers"].keys())

    print(f"{'filler':<12}  GT   " + "  ".join(f"{n:>22}" for n in results))
    for f in sorted(all_f, key=lambda x: -gt_fillers.get(x, 0)):
        gt_n = gt_fillers.get(f, 0)
        row = [f"{r['fillers'].get(f, 0):>22}" for r in results.values()]
        print(f"{f:<12}  {gt_n:>3}  " + "  ".join(row))
    print(f"\n{'合計':<12}  {total_gt:>3}  " + "  ".join(f"{r['total']:>22}" for r in results.values()))
    recall_line = "  ".join(f"{r['total']/total_gt*100:>21.0f}%" for r in results.values())
    print(f"{'捕捉率':<12}  {'':>3}  " + recall_line)


if __name__ == "__main__":
    main()
