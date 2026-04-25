"""Whisper Large-v3 + LoRA 学習スクリプト (Phase A)

prepare_dataset.py が生成した HF Dataset (train/eval) を使って、Decoder のみに
LoRA を当てた Whisper Large-v3 を fine-tune する。

入力:
    --train-ds: prepare_dataset.py の出力 train/ ディレクトリ
    --eval-ds:  同 eval/ ディレクトリ
    --out:      checkpoint 出力先

出力:
    {out}/checkpoint-{step}/  : エポック毎の checkpoint
    {out}/final/              : 最終 LoRA アダプタ (+ processor)
    {out}/training_log.json   : 学習ログ

使い方:
    cd experiments/whisper_lora
    source .venv/bin/activate
    python train_lora.py \
        --train-ds data/hf/20260129_生成AI/train \
        --eval-ds  data/hf/20260129_生成AI/eval \
        --out      outputs/20260129_phase_a \
        --epochs 10

想定所要時間 (M4 Max 128GB):
    128 train chunks, 10 epoch, batch 2 + grad_accum 8 = 実効 batch 16
    -> 約 80 optimizer step
    -> 数時間 (初回は mel feature 計算で +数分)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import librosa
import torch
from datasets import load_from_disk
from peft import LoraConfig, get_peft_model
from transformers import (
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)

MODEL_ID = "openai/whisper-large-v3"
SAMPLE_RATE = 16000


def preprocess_audio_text(example: dict, processor: WhisperProcessor) -> dict:
    """音声チャンクをロード → mel spec 抽出 & text トークン化。"""
    audio, _ = librosa.load(
        example["audio_path"],
        sr=SAMPLE_RATE,
        offset=float(example["offset"]),
        duration=float(example["duration"]),
        mono=True,
    )
    # 80-mel, 3000 frames (30秒分にパディング済み)
    features = processor.feature_extractor(audio, sampling_rate=SAMPLE_RATE, return_tensors="np")
    example["input_features"] = features.input_features[0]  # (80, 3000)
    # 日本語/transcribe prefix は processor に設定済みなので自動付与される
    example["labels"] = processor.tokenizer(example["text"]).input_ids
    return example


@dataclass
class DataCollatorWhisperLoRA:
    """Whisper LoRA 学習用 data collator。

    input_features は processor により常に (80, 3000) になるので単純 stack。
    labels は可変長なので pad、pad 領域は -100 で loss から除外。
    """

    processor: WhisperProcessor
    dtype: torch.dtype = torch.float16  # モデル重みに揃える

    def __call__(self, features: list[dict]) -> dict[str, torch.Tensor]:
        input_features = torch.tensor([f["input_features"] for f in features], dtype=self.dtype)
        label_batch = self.processor.tokenizer.pad(
            [{"input_ids": f["labels"]} for f in features],
            return_tensors="pt",
        )
        labels = label_batch["input_ids"].masked_fill(label_batch.attention_mask.ne(1), -100)
        # Whisper は bos/prefix を自前で付けるケースがあるので、全行 bos で
        # 始まっていれば先頭を削る (HF Whisper fine-tune の定石)
        bos = self.processor.tokenizer.bos_token_id
        if bos is not None and (labels[:, 0] == bos).all().item():
            labels = labels[:, 1:]
        return {"input_features": input_features, "labels": labels}


def build_model(lora_r: int, lora_alpha: int, lora_dropout: float) -> WhisperForConditionalGeneration:
    """Whisper Large-v3 に Decoder-only LoRA を装着。"""
    print(f"Loading {MODEL_ID} (fp16) ...")
    model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, dtype=torch.float16)

    # 生成時のデフォルト設定
    model.generation_config.language = "japanese"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None

    # Encoder を凍結（話者過適合を抑制する方針）
    for p in model.model.encoder.parameters():
        p.requires_grad = False

    # Decoder の attention 各層にだけ LoRA を挿入
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=(r".*decoder\.layers\.\d+\.(self_attn|encoder_attn)\.(q_proj|k_proj|v_proj|out_proj)"),
        lora_dropout=lora_dropout,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-ds", type=Path, required=True)
    parser.add_argument("--eval-ds", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    # Processor (language/task は processor に設定しておくと tokenize 時に prefix 自動付与)
    processor = WhisperProcessor.from_pretrained(MODEL_ID, language="japanese", task="transcribe")

    # Model
    model = build_model(args.lora_r, args.lora_alpha, args.lora_dropout)

    # Dataset
    print(f"Loading datasets from {args.train_ds}, {args.eval_ds}")
    train_raw = load_from_disk(str(args.train_ds))
    eval_raw = load_from_disk(str(args.eval_ds))
    print(f"  train: {len(train_raw)} records, eval: {len(eval_raw)} records")

    print("Preprocessing audio/text (this caches to HF datasets cache) ...")
    train_ds = train_raw.map(
        lambda x: preprocess_audio_text(x, processor),
        num_proc=1,
        desc="train preprocess",
    )
    eval_ds = eval_raw.map(
        lambda x: preprocess_audio_text(x, processor),
        num_proc=1,
        desc="eval preprocess",
    )

    # Trainer
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(args.out),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        predict_with_generate=False,  # loss ベースで評価 (fast)
        report_to=[],
        remove_unused_columns=False,
        dataloader_num_workers=0,  # librosa が fork-unsafe な可能性
        seed=args.seed,
    )

    trainer = Seq2SeqTrainer(
        args=training_args,
        model=model,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=DataCollatorWhisperLoRA(processor=processor),
    )

    print("\nStarting training ...")
    train_result = trainer.train()

    # 最終アダプタ保存
    final_dir = args.out / "final"
    model.save_pretrained(str(final_dir))
    processor.save_pretrained(str(final_dir))
    print(f"\nFinal adapter saved: {final_dir}")

    # ログを JSON 出力
    log_path = args.out / "training_log.json"
    log_path.write_text(
        json.dumps(
            {
                "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
                "train_result": {
                    "global_step": train_result.global_step,
                    "training_loss": float(train_result.training_loss),
                },
                "log_history": trainer.state.log_history,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Log saved: {log_path}")


if __name__ == "__main__":
    main()
