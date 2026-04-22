"""Whisper Large-v3 + LoRA の環境スモークテスト

目的:
  M4 Max + PyTorch MPS + PEFT の組み合わせが期待通り動作するかを、
  実データなしで確認する。

実行内容:
  1. MPS が利用可能か確認
  2. Whisper Large-v3 を fp16 でロード
  3. LoRA (rank=16) を装着、学習対象パラメータ数を表示
  4. ダミー音声 (30s @ 16kHz) で forward+backward を 3 step 実行
  5. メモリ使用量と 1 step あたりの時間を計測

使い方:
  python test_mps_setup.py
"""

from __future__ import annotations

import sys
import time

import numpy as np
import torch
from peft import LoraConfig, get_peft_model
from transformers import WhisperForConditionalGeneration, WhisperProcessor

MODEL_ID = "openai/whisper-large-v3"
SAMPLE_RATE = 16000
DUMMY_AUDIO_SECONDS = 30
NUM_STEPS = 3


def check_mps() -> torch.device:
    print(f"PyTorch: {torch.__version__}")
    print(f"MPS available: {torch.backends.mps.is_available()}")
    print(f"MPS built:     {torch.backends.mps.is_built()}")
    if not torch.backends.mps.is_available():
        print("ERROR: MPS not available. M4 Max / PyTorch 2.3+ が必要です。", file=sys.stderr)
        sys.exit(1)
    return torch.device("mps")


def load_model() -> tuple[WhisperForConditionalGeneration, WhisperProcessor]:
    print(f"\nLoading {MODEL_ID} (fp16) ...")
    t0 = time.time()
    processor = WhisperProcessor.from_pretrained(MODEL_ID)
    model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_ID,
        dtype=torch.float16,
    )
    print(f"Loaded in {time.time() - t0:.1f}s")
    return model, processor


def apply_lora(model: WhisperForConditionalGeneration) -> WhisperForConditionalGeneration:
    # Encoder を凍結して話者過適合を抑制する（Phase A の設計方針）
    for param in model.model.encoder.parameters():
        param.requires_grad = False

    # Decoder の attention にのみ LoRA を挿入
    # PEFT 0.11+ は target_modules に regex を渡せる
    # task_type は指定しない: Whisper は PeftModelForSeq2SeqLM の自動 input_ids 処理と衝突する
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=r".*decoder\.layers\.\d+\.(self_attn|encoder_attn)\.(q_proj|k_proj|v_proj|out_proj)",
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def smoke_test(
    model: WhisperForConditionalGeneration,
    processor: WhisperProcessor,
    device: torch.device,
) -> None:
    model = model.to(device)
    model.train()

    # ダミー音声: 30 秒のランダムノイズ
    rng = np.random.default_rng(seed=0)
    dummy_audio = rng.standard_normal(SAMPLE_RATE * DUMMY_AUDIO_SECONDS).astype(np.float32)

    inputs = processor(dummy_audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    input_features = inputs.input_features.to(device, dtype=torch.float16)

    labels = processor.tokenizer(
        "えーっと、テストです。あの、動くかな。",
        return_tensors="pt",
    ).input_ids.to(device)

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=1e-4,
    )

    print(f"\nRunning {NUM_STEPS} forward+backward steps (decoder-only LoRA)...")
    for i in range(NUM_STEPS):
        t0 = time.time()
        outputs = model(input_features=input_features, labels=labels)
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        torch.mps.synchronize()
        elapsed = time.time() - t0
        mem_gb = torch.mps.current_allocated_memory() / (1024**3)
        print(f"  Step {i + 1}: loss={loss.item():.4f}, time={elapsed:.2f}s, mem={mem_gb:.2f}GB")


def main() -> None:
    device = check_mps()
    model, processor = load_model()
    model = apply_lora(model)
    smoke_test(model, processor, device)
    print("\nSmoke test passed. Environment is ready for LoRA training.")


if __name__ == "__main__":
    main()
