---
license: mit
language:
- ja
base_model: openai/whisper-large-v3
tags:
- automatic-speech-recognition
- whisper
- mlx
- apple-silicon
- japanese
- filler-detection
- disfluency
---

# Whisper Large-v3 Japanese Filler (MLX)

日本語音声からフィラー（「あの」「まあ」「えー」等の言い淀み）を高精度に捕捉するための Whisper Large-v3 派生モデル。**Apple Silicon 向け MLX 形式**。

LoRA アダプタ [`Coidemo/whisper-large-v3-filler-lora`](https://huggingface.co/Coidemo/whisper-large-v3-filler-lora) を base にマージして MLX 形式 (`weights.npz`) に変換済み。即 `mlx_whisper` で推論できる。

## 性能 (held-out 9.2 分、initial_prompt なし)

| 指標 | Base Whisper | This Model | 改善 |
|------|-------------|-----------|------|
| Char WER | 8.61% | **5.59%** | **-35% 相対** |
| FIR (Filler Inclusion Rate) | 13.3% | **48.9%** | **3.7倍** |
| filler recall | 6/45 | 22/45 | +16 |

## 使い方

### mlx_whisper で直接

```python
import mlx_whisper

result = mlx_whisper.transcribe(
    "video.mp4",
    path_or_hf_repo="Coidemo/whisper-large-v3-filler-mlx",
    language="ja",
    initial_prompt=(
        "以下は話し言葉のインタビューです。間投詞や言い淀みも省略せずに"
        "書き起こしてください。例: えーっと、あの、うーん、なんか、まあ"
    ),
)
for seg in result["segments"]:
    print(seg["text"])
```

### TextffCut 経由 (推奨 — フィラー音声切除・SRT 生成等まで一気通貫)

```bash
# TextffCut をインストール
brew install coidemo/textffcut/textffcut

# LoRA モデルで文字起こし + AI 切り抜き + FCPXML + SRT 生成
textffcut clip -m large-v3-lora-20260129 ./videos/動画.mp4
```

TextffCut 内で本モデルの自動 DL、境界重複 dedup、hallucination retry、forced-aligner による word/char-level timestamps 付与まで自動。

## 訓練・変換パイプライン

1. **訓練**: `openai/whisper-large-v3` の Decoder attention 層に LoRA (rank=16) を適用。日本語ポッドキャスト 1 話者 50 分、手動修正済みトランスクリプトで 10 epochs fine-tune (Apple M4 Max で 17 分)
2. **マージ**: PEFT の `merge_and_unload()` で base に rank 更新を畳み込み
3. **MLX 変換**: HF Transformers Whisper の weight naming (`self_attn.q_proj` 等) を MLX Whisper の naming (`attn.query` 等) に変換、Conv1d の shape を MLX 規約 `(out, k, in)` に permute、`alignment_heads` (word timestamp 用) も `(10, 2)` int64 配列で埋め込み

詳細スクリプト: [TextffCut リポジトリの `experiments/whisper_lora/merge_and_convert_mlx.py`](https://github.com/Coidemo/TextffCut/blob/main/experiments/whisper_lora/merge_and_convert_mlx.py)

## ファイル構成

- `config.json`: MLX Whisper の ModelDimensions (n_mels=128, n_audio_layer=32, n_text_layer=32 等)
- `weights.npz`: マージ済み weights (fp16, 2.9GB)

## 制限事項

- **Apple Silicon 専用** (MLX は Apple Silicon のみ動作)
- **話者特化**: 訓練話者 (podcaster「けんすう」氏) のフィラーパターン (「あの」支配的) に過適合
- 「えっと」「えーっと」系フィラーは訓練話者が使わないため改善なし
- 日本語以外では効果なし
- 訓練データに類似した音響パターンで稀に「まあまあまあ…」ループが発生するが、TextffCut の post-process で自動対処される

## ライセンス

[MIT License](https://opensource.org/licenses/MIT) — 継承元: [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3)

## 関連

- **TextffCut**: 本モデルを使う動画文字起こし・AI 自動切り抜きツール — https://github.com/Coidemo/TextffCut
- **LoRA adapter**: `Coidemo/whisper-large-v3-filler-lora` (PEFT 形式、42MB、HF transformers で使う場合)

## 引用

```bibtex
@article{radford2022whisper,
  title={Robust Speech Recognition via Large-Scale Weak Supervision},
  author={Radford, Alec and Kim, Jong Wook and Xu, Tao and Brockman, Greg and McLeavey, Christine and Sutskever, Ilya},
  journal={arXiv preprint arXiv:2212.04356},
  year={2022}
}
```
