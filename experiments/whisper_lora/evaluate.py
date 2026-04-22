"""Base Whisper Large-v3 vs LoRA 適用版 の比較評価。

eval データセットの各チャンクに対して両モデルで文字起こしを行い、
WER (文字単位) と FIR (Filler Inclusion Rate) を計算する。

入力:
    --eval-ds:       prepare_dataset.py の出力 eval/
    --lora-adapter:  train_lora.py の出力 final/ (LoRA アダプタ)
    --out:           比較結果の JSON 出力先

使い方:
    cd experiments/whisper_lora
    source .venv/bin/activate
    python evaluate.py \
        --eval-ds data/hf/20260129_生成AI/eval \
        --lora-adapter outputs/20260129_phase_a/final \
        --out results/20260129_phase_a_eval.json

出力:
    JSON ファイルに per-chunk の ground truth / base 予測 / lora 予測、
    および全体の WER / FIR を記録。コンソールにもサマリを表示。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import librosa
import torch
from datasets import load_from_disk
from peft import PeftModel
from transformers import WhisperForConditionalGeneration, WhisperProcessor

MODEL_ID = "openai/whisper-large-v3"
SAMPLE_RATE = 16000
INITIAL_PROMPT_JA = (
    "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに書き起こしてください。"
    "例: えーっと、えー、あのー、あの、うーん、うーんと、なんか、なんかその、"
    "まあ、まぁ、んー、あー、そうですね"
)

# 評価対象フィラー (FIR 計算用)
FILLERS = [
    "えー", "えっと", "えーっと", "あの", "あのー", "あのね",
    "うーん", "うーんと", "んー", "あー", "まあ", "まぁ",
    "なんか", "なんかその", "そうですね", "やっぱ", "やっぱり",
    "で、", "ね、",
]


def char_wer(reference: str, hypothesis: str) -> float:
    """文字単位の WER (編集距離 / 参照長)。日本語向け。"""
    ref = list(reference)
    hyp = list(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    # 動的計画法による編集距離
    m, n = len(ref), len(hyp)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost,  # substitution
            )
    return dp[m][n] / len(ref)


def compute_fir(reference: str, hypothesis: str) -> tuple[int, int]:
    """FIR の分子・分母を返す。

    各フィラー語について、ref に出現する回数のうち hyp にも(min回数以上)含まれる
    ものをカウント。戻り値: (recalled, total_ref_fillers)
    """
    recalled = 0
    total = 0
    for f in FILLERS:
        ref_cnt = reference.count(f)
        if ref_cnt == 0:
            continue
        hyp_cnt = hypothesis.count(f)
        recalled += min(ref_cnt, hyp_cnt)
        total += ref_cnt
    return recalled, total


def load_audio_chunk(example: dict) -> torch.Tensor:
    audio, _ = librosa.load(
        example["audio_path"],
        sr=SAMPLE_RATE,
        offset=float(example["offset"]),
        duration=float(example["duration"]),
        mono=True,
    )
    return torch.from_numpy(audio)


def transcribe_one(
    model: WhisperForConditionalGeneration,
    processor: WhisperProcessor,
    audio: torch.Tensor,
    device: torch.device,
) -> str:
    """initial_prompt を使わずに transcribe (base / LoRA 同条件比較のため)。

    prompt を使うと「フィラー語例を与える」ことで base にも恩恵が出てしまい、
    LoRA 自体の学習効果を計測しにくくなる。また Whisper の 448 token 制限にも
    かかりやすくなる。
    """
    features = processor.feature_extractor(
        audio.numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt"
    ).input_features.to(device, dtype=next(model.parameters()).dtype)

    with torch.no_grad():
        pred_ids = model.generate(
            features,
            max_new_tokens=440,
            language="japanese",
            task="transcribe",
        )
    text = processor.batch_decode(pred_ids, skip_special_tokens=True)[0]
    return text.strip()


def evaluate_model(
    model: WhisperForConditionalGeneration,
    processor: WhisperProcessor,
    eval_ds,
    device: torch.device,
    label: str,
) -> tuple[list[dict], dict]:
    print(f"\n[{label}] 評価実行中 ({len(eval_ds)} chunks) ...")
    records = []
    total_ref_chars = 0
    total_wer_edits = 0.0
    total_recalled = 0
    total_fillers = 0
    filler_counter: Counter[str] = Counter()

    for i, ex in enumerate(eval_ds):
        audio = load_audio_chunk(ex)
        hyp = transcribe_one(model, processor, audio, device)
        ref = ex["text"].strip()

        wer = char_wer(ref, hyp)
        recalled, total = compute_fir(ref, hyp)
        for f in FILLERS:
            filler_counter[f] += hyp.count(f)

        records.append({
            "idx": i,
            "offset": ex["offset"],
            "duration": ex["duration"],
            "reference": ref,
            "hypothesis": hyp,
            "char_wer": round(wer, 4),
            "filler_recalled": recalled,
            "filler_total": total,
        })

        total_ref_chars += len(ref)
        total_wer_edits += wer * len(ref)
        total_recalled += recalled
        total_fillers += total
        print(f"  [{i+1:3d}/{len(eval_ds)}] WER={wer:.3f}  fillers={recalled}/{total}")

    summary = {
        "n_chunks": len(eval_ds),
        "total_ref_chars": total_ref_chars,
        "char_wer": round(total_wer_edits / total_ref_chars, 4) if total_ref_chars else 0.0,
        "fir": round(total_recalled / total_fillers, 4) if total_fillers else 0.0,
        "filler_recalled": total_recalled,
        "filler_total_in_ref": total_fillers,
        "filler_counts_in_hyp": dict(filler_counter),
    }
    print(f"[{label}] WER={summary['char_wer']:.4f}, FIR={summary['fir']:.4f} "
          f"({total_recalled}/{total_fillers})")
    return records, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-ds", type=Path, required=True)
    parser.add_argument("--lora-adapter", type=Path, required=True, help="train_lora.py 出力の final/")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}")

    processor = WhisperProcessor.from_pretrained(MODEL_ID, language="japanese", task="transcribe")
    eval_ds = load_from_disk(str(args.eval_ds))
    print(f"eval dataset: {len(eval_ds)} chunks")

    # ===== Base モデル =====
    print(f"\nLoading base {MODEL_ID} (fp16) ...")
    base_model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, dtype=torch.float16).to(device)
    base_model.eval()
    base_records, base_summary = evaluate_model(base_model, processor, eval_ds, device, label="BASE")

    # ===== LoRA 適用モデル =====
    # base と別インスタンスを用意 (base を壊さないため)
    print(f"\nLoading base for LoRA + adapter from {args.lora_adapter} ...")
    lora_base = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, dtype=torch.float16)
    lora_model = PeftModel.from_pretrained(lora_base, str(args.lora_adapter))
    lora_model = lora_model.to(device)
    lora_model.eval()
    lora_records, lora_summary = evaluate_model(lora_model, processor, eval_ds, device, label="LORA")

    # ===== 結果書き出し =====
    result = {
        "eval_ds": str(args.eval_ds),
        "lora_adapter": str(args.lora_adapter),
        "base": base_summary,
        "lora": lora_summary,
        "improvement": {
            "char_wer_delta": round(lora_summary["char_wer"] - base_summary["char_wer"], 4),
            "fir_delta": round(lora_summary["fir"] - base_summary["fir"], 4),
        },
        "per_chunk_base": base_records,
        "per_chunk_lora": lora_records,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # サマリ表示
    print("\n" + "=" * 64)
    print("COMPARISON")
    print("=" * 64)
    print(f"  Char WER:  base={base_summary['char_wer']:.4f}  lora={lora_summary['char_wer']:.4f}  "
          f"(Δ {result['improvement']['char_wer_delta']:+.4f})")
    print(f"  FIR:       base={base_summary['fir']:.4f}  lora={lora_summary['fir']:.4f}  "
          f"(Δ {result['improvement']['fir_delta']:+.4f})")
    print(f"  filler recall:  base {base_summary['filler_recalled']}/{base_summary['filler_total_in_ref']}  "
          f"  lora {lora_summary['filler_recalled']}/{lora_summary['filler_total_in_ref']}")
    print(f"\n詳細: {args.out}")


if __name__ == "__main__":
    main()
