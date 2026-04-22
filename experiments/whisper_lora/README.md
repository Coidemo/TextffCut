# Whisper LoRA PoC (Phase A: 同一話者版)

## 目的

M4 Max 128GB 上で **Whisper Large-v3** に LoRA アダプタを適用し、
同一話者の音声に対してフィラー検出精度（FIR / WER）を向上させられるかを
検証する PoC。

TextffCut 本体（`core/`, `use_cases/` 等）には一切干渉せず、
この `experiments/whisper_lora/` 配下で完結する。

## 設計方針

| 項目 | 値 | 理由 |
|------|-----|------|
| ベースモデル | `openai/whisper-large-v3` | TextffCut v2.0.10 の本番デフォルトと一致 |
| 学習手法 | LoRA (rank=16, α=32) | フル fine-tune はコスト高 |
| 対象レイヤー | Decoder の Q/K/V/O (+FFN) | Encoder 凍結で話者過適合を抑制 |
| バックエンド | PyTorch MPS | M4 Max GPU を利用 |
| 精度 | fp16 | 128GB あるが fp16 で学習高速化 |
| データ形式 | HF `datasets` (`{audio, text, timestamps}`) | 標準的なフォーマット |

## 段階

- **Phase A** (ここ): 単一話者 3-5h で「LoRA でフィラー検出が効くか」を検証
- **Phase B** (将来): 複数話者に拡張し汎化版を目指す
- **Phase C** (将来): 本体 `mlx-whisper` に LoRA マージ済みモデルを載せて配布

## セットアップ

```bash
cd experiments/whisper_lora

# 独立 venv で本体の依存と分離する
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

本体プロジェクトの venv は使わないこと（torch/transformers のバージョン衝突防止）。

## スモークテスト（最初に必ず実行）

環境が正しくセットアップされているかを確認する。実データ不要。

```bash
python test_mps_setup.py
```

期待される出力:

```
PyTorch: 2.x.x
MPS available: True
Loading openai/whisper-large-v3 ...
Loaded in XXs
trainable params: ~X,XXX,XXX || all params: 1,543,XXX,XXX || trainable%: X.XX

Running 3 forward+backward steps...
  Step 1: loss=X.XX, time=XX.Xs, mem=XX.XGB
  Step 2: loss=X.XX, time=XX.Xs, mem=XX.XGB
  Step 3: loss=X.XX, time=XX.Xs, mem=XX.XGB

Smoke test passed.
```

想定値:
- メモリ使用量: 25-40 GB 程度（M4 Max 128GB に対して余裕）
- 1 step あたり: 5-15 秒（これで 10h データ・5 epoch の学習時間を概算）

## 今後追加予定のファイル

- `prepare_dataset.py`: 動画 + 文字起こしキャッシュ → HF Dataset 変換
- `train_lora.py`: LoRA 学習メインループ
- `evaluate.py`: ベース vs LoRA の FIR / WER 比較
- `merge_and_export.py`: LoRA マージ → MLX 変換
- `configs/phase_a.yaml`: ハイパラ設定

## 参考文献

- WhisperD: [arXiv 2505.21551](https://arxiv.org/abs/2505.21551) — 11.4h データで FIR 0.04→0.70
- Acoustically Precise Hesitation Tagging: [arXiv 2506.04076](https://arxiv.org/abs/2506.04076) — LoRA rank=32 で WER -11.3%
