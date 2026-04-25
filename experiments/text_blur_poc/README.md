# Text Blur PoC

動画内のテキスト（コメント・UI 文字・チャンネルロゴ等）を自動検出してぼかしを適用する PoC。

## 目的

DaVinci Resolve で字幕合成する前提で、元動画のテキスト要素を全て自動でぼかした
動画ファイル（`*_blurred.mp4`）を生成できるかを検証する。

TextffCut 本体には干渉せず、`experiments/text_blur_poc/` 配下で完結する。

## 設計方針

| 項目 | 値 | 理由 |
|------|-----|------|
| 検出モデル | EasyOCR の detect-only mode | CRAFT 内蔵・日本語対応・API シンプル |
| 動画処理 | OpenCV frame-by-frame | PoC 重視。ffmpeg ネイティブ最適化は本実装時 |
| ぼかし | Gaussian blur | カーネルサイズ可変 |
| 速度変更 | ffmpeg `setpts` + `atempo` | ぼかし合成後にまとめて適用 |

## 段階

- **P1**: 静止画 1 枚で検出 → bbox 可視化（モデル動作確認）
- **P2**: 動画を sample-rate でフレーム抽出 → bbox 時系列 JSON 生成
- **P3**: IoU マッチングで bbox 追跡 + 短時間ギャップ補間（ちらつき抑制）
- **P4**: OpenCV で frame-by-frame ぼかし合成 → ffmpeg で速度変更を適用 → 1 ファイル出力
- **P5**: 実動画で品質評価 → 本実装フェーズ判断

## セットアップ

```bash
cd experiments/text_blur_poc

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

### P1: 静止画でモデル動作確認
```bash
python detect_single_frame.py \
    --input samples/sample_30s.mp4 \
    --timestamp 5.0 \
    --output outputs/p1_detected.jpg
```

### P4: 動画を処理（最終形）
```bash
python detect_and_blur.py \
    --input samples/sample_30s.mp4 \
    --output outputs/sample_blurred.mp4 \
    --speed 1.2 \
    --sample-rate 3 \
    --blur-strength 25 \
    --padding 10 \
    --preview
```

## サンプル動画

`samples/sample_30s.mp4` は実動画から 30 秒切り出し（けんすうスピーク podcast、コメント表示部分）。
チャンネルロゴ（右上）・質問テキスト（下部）・コメント主タグが含まれる。
