# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 言語設定
**会話は日本語で行ってください。**

## プロジェクト概要

**TextffCut** - Apple Silicon Mac専用の動画文字起こし・AI自動切り抜きCLIツール

主な用途：
- MLX Whisperによる高速文字起こし（Apple Silicon最適化）
- AIによる自動切り抜き候補提案 → FCPXML + SRT字幕出力
- 無音部分を自動削除してタイトな編集素材を作成
- DaVinci ResolveやFinal Cut Pro用のFCPXMLを生成
- タイトル画像・BGM・SE・フレーム画像の自動配置

## バージョン情報

### v2.1.0 (2026-04-22) — 最新安定版
- **タグ**: `v2.1.0`
- **Phase A Whisper LoRA PoC 完成** (PR #119):
  - 同一話者 50 分データで Whisper Large-v3 に LoRA を適用、Char WER −35%・FIR 3.7倍
  - `textffcut -m large-v3-filler` で LoRA 適用モデルを選択可能 (HF Hub から自動 DL)
  - HF 配布: [`Coidemo/whisper-large-v3-filler-lora`](https://huggingface.co/Coidemo/whisper-large-v3-filler-lora) (42MB adapter) / [`Coidemo/whisper-large-v3-filler-mlx`](https://huggingface.co/Coidemo/whisper-large-v3-filler-mlx) (2.9GB MLX マージ済み)
- **境界重複 dedup + hallucination retry**: `core/mlx_whisper_refine.py` で base/LoRA 両モデル共通の後処理を実装。Whisper 30秒ウィンドウ境界の重複削除と反復 hallucination の selective retry。
- **学習パイプライン一式**: `experiments/whisper_lora/` にブラウザ編集ツール・LoRA 学習・MLX 変換・評価の 8 スクリプトを配置
- **クリップ品質の劇的向上**: 実動画処理でユーザー体感確認済み

### v2.0.10 (2026-04-21)
- **タグ**: `v2.0.10`
- **フィラー削減の大幅改善**:
  - Whisper `initial_prompt` を自然文+例形式に改善（PR #115）
  - SRT字幕の「あの」「まあ」を文脈判定で除去（PR #116、削減率 -92%）
  - Phase 3.6 フィラー音声の物理的切除を追加（PR #117、duration -3.7%, 最大-27%）
  - Whisperデフォルトを medium → large-v3（PR #118、CER -26%, 固有名詞認識 +18%）
- 処理時間は +60% だが、固有名詞（人名等）の誤認識が大幅改善

### v2.0.9 (2026-04-20)
- FCPXML別マシン配布対応 (`textffcut relink` コマンド、PR #113)
- SRT字幕の境界ズレをword-levelタイムスタンプで解消（PR #114）

### v2.0.8 (2026-04-20)
- CLI外部実行対応 + GUIポート競合回避 + バージョン統一

### v2.0.6 (2026-04-15)
- タイトル画像にドロップシャドウ追加（4パス描画）
- 黒文字+黒内縁バグ修正（セグメント単位の輝度判定）

### v2.0.5 (2026-04-14)
- タイトル画像品質改善（白外縁3層構造・助詞縮小・3パス描画順修正）

### v2.0.4 (2026-04-14)
- クリップ品質改善（topic境界制約・embedding coherence・フィラー3層除去・末尾途切れ改善）
- パイプライン並列化+Whisper廃止で処理時間49%短縮

### v2.0.3 (2026-04-12)
- タイトル画像の色セグメント境界をGiNZA単語境界にスナップ

### v2.0.2 (2026-04-12)
- 処理パイプライン高速化（GiNZA LRUキャッシュ、FFmpeg/Whisper API並列化）

### v2.0.1 (2026-04-08)
- Apple Silicon Mac専用（Docker廃止）
- MLX Whisperによる文字起こし
- AI自動切り抜き（`textffcut clip`）
- SRT字幕自動生成（GiNZA文節ベース）
- タイトル画像生成・コントラスト補正
- SE配置・アンカー検出

### v2.0.0 (2026-03-30)
- CLI全面刷新、Docker廃止

## 主要アーキテクチャ

CLIファースト設計。Apple Silicon Mac + MLX Whisper前提。

```
TextffCut/
├── textffcut_cli/           # CLIエントリーポイント
│   ├── command.py           # メインCLIコマンド定義
│   ├── suggest_command.py   # textffcut clip サブコマンド
│   ├── setup_command.py     # 初期設定ウィザード
│   └── upgrade_command.py   # 更新機能
├── core/                    # コア機能
│   ├── japanese_line_break.py  # GiNZA文節ベース日本語改行
│   ├── srt_diff_exporter.py    # SRT差分エクスポート
│   ├── export.py            # FCPXML/EDLエクスポート
│   └── video.py             # 動画処理・無音検出
├── use_cases/ai/            # AI機能
│   ├── suggest_and_export.py       # AI切り抜き→FCPXML+SRT出力
│   ├── generate_clip_suggestions.py # クリップ候補生成
│   ├── srt_subtitle_generator.py   # SRT字幕生成（Phase 1-3）
│   ├── early_filler_detection.py   # Phase 0: フィラー位置検出
│   ├── filler_audio_removal.py     # Phase 3.6: フィラー音声物理切除
│   ├── stammering_remover.py       # Phase 3.5: 吃音（連続反復）除去
│   ├── title_image_generator.py    # タイトル画像生成
│   ├── auto_anchor_detector.py     # 被写体位置自動検出
│   ├── se_placement.py             # 効果音配置
│   └── final_video_generator.py    # 最終動画生成
├── core/
│   ├── fcpxml_relink.py            # 別マシン向けFCPXMLパス書き換え
│   └── ...
├── adapters/                # インターフェースアダプター層
├── di/                      # 依存性注入コンテナ
├── domain/                  # ドメインモデル
├── infrastructure/          # 外部連携
├── ui/                      # Streamlit GUI
└── main.py                  # GUI起動
```

## CLIコマンド

```bash
# 文字起こし
textffcut [動画ファイル ...]

# AI自動切り抜き → FCPXML + SRT出力
textffcut clip [動画ファイル ...]

# GUI起動
textffcut gui

# モデル一覧
textffcut models

# 初期設定
textffcut setup

# 更新
textffcut upgrade
```

### textffcut clip の主要オプション

```bash
# AI/字幕
--ai-model gpt-4.1-mini    # AIモデル選択
--num 5                     # 候補数
--min-duration 30           # 最小秒数
--max-duration 60           # 最大秒数
--srt-max-chars 11          # SRT 1行最大文字数
--srt-max-lines 2           # SRT 最大行数
--no-srt                    # SRT生成スキップ

# 動画処理
--speed 1.0                 # 再生速度
--zoom 100                  # ズーム%
--anchor X Y                # アンカーポイント
--vertical                  # 縦動画用タイムライン
--remove-silence            # 無音削除

# メディア素材
--preset-dir DIR            # プリセット素材ディレクトリ
--no-frame / --no-bgm / --no-se / --no-title-image
--title-target-size 1080x438
```

### 出力構造

```
{動画名}_TextffCut/
├── fcpxml/
│   ├── 01_タイトル.fcpxml     # FCPXML（DaVinci/FCP用）
│   ├── 01_タイトル.srt        # SRT字幕
│   ├── 01_タイトル_title.png  # タイトル画像
│   └── ...
├── clip_suggestions/
│   └── gpt-4.1-mini.json     # AI候補キャッシュ
└── transcription/
    └── cache.json             # 文字起こしキャッシュ
```

## SRT字幕生成パイプライン

`srt_subtitle_generator.py` の3フェーズ処理：

1. **Phase 1**: GiNZA文節境界ベースのスコアリングで分割点を決定
   - 文節境界 = 自然な分割点（+20）
   - 接続助詞（から/けど/ので）= 強い分割（+40）
   - 文節内部 = 分割抑制（-30）
2. **Phase 2**: 改行挿入（max_chars制限内で2行化）
3. **Phase 3**: 短いエントリの結合（SENTENCE_ENDINGSで結合判定）

## フィラー除去パイプライン（v2.0.10〜）

4層でフィラーを段階的に削除：

1. **文字起こし層** (`core/transcription.py`): Whisper `initial_prompt` で
   フィラー保持を指示。`large-v3` モデルで捕捉率向上。
2. **Phase 0 検出** (`use_cases/ai/early_filler_detection.py`):
   `FILLER_WORDS` リスト + GiNZA文脈判定で位置を特定。`filler_map` を生成。
3. **Phase 3.5 吃音除去** (`use_cases/ai/stammering_remover.py`):
   連続反復パターン（「ない人はない人は」等）を検出・除去。time_ranges を更新。
4. **Phase 3.6 音声切除** (`use_cases/ai/filler_audio_removal.py`):
   Phase 0 の `filler_map` を使い、time_ranges からフィラー区間を物理的に減算。
   短すぎる（<0.15s）フィラーは音飛び防止でスキップ。
5. **SRT 字幕層** (`srt_subtitle_generator.py::_remove_inline_fillers`):
   SUBTITLE_FILLER_WORDS + 文脈依存フィラー（「あの」「まあ」）の最終除去。
   Phase 0 が検出できなかったセグメント境界またぎを補完。

**設計原則**: 音声切除（4）が効くと字幕も自動追従する。文脈判定（5）は
その後の最終クリーンアップ。両者相補で 90%+ 削減を実現。

### 日本語NLP

- **GiNZA/spaCy**: 文節境界API + 形態素解析
- **POS正規化**: UniDic→IPADIC互換変換（`_normalize_pos_tag()`）
- **フィラー除去**: GiNZA POS + 辞書ベースの2段階検出
- **後方互換シム**: `_CompatTokenizer`/`_CompatToken`（`srt_diff_exporter.py`用）

**注意**: GiNZA読み込み時は `spacy.load("ja_ginza", exclude=["compound_splitter"])` が必要（`split_mode=null`のConfigValidationError回避）

## 技術スタック

- **文字起こし**: MLX Whisper（Apple Silicon最適化）
- **日本語NLP**: GiNZA/spaCy（文節境界、形態素解析）
- **AI**: OpenAI API（GPT-4.1-mini/GPT-4.1）
- **動画処理**: FFmpeg
- **GUI**: Streamlit（オプション）
- **ターミナル**: Rich
- **設定**: `~/.textffcut/config.json`

## 開発コマンド

```bash
# 品質チェック（フォーマット + Lint + テスト）
make check

# テスト
python -m pytest tests/ -v
python -m pytest tests/ -v -k "test_name"  # 特定テスト

# フォーマット・Lint
make format
make lint

# コミット前チェック
make pre-commit
```

## 開発運用ルール

### ブランチ戦略
- `feature/機能名`: 新機能
- `fix/バグ名`: バグ修正
- `refactor/対象`: リファクタリング
- 開発完了後 → PR作成 → mainにマージ

### コミットメッセージ
- 日本語OK
- プレフィックス: `feat:`, `fix:`, `docs:`, `refactor:`

### 開発作業の進め方
1. 要件確認: `/docs/requirements_definition.md` を確認
2. 設計更新: 変更前に必ずユーザー確認を取る
3. タスク分解: 承認後に実装開始
4. 実装中に設計変更が必要 → 一旦停止して相談

### 重要な原則
- **何かを変更する前に必ず確認を取る**
- 要件定義書 → 基本設計書 → 詳細設計書の階層を守る
- 想定外の問題が発生したら、独断で進めず相談
- 実装後は `make check` を必ず実行

## 注意事項

1. **FCPXMLのアセット参照**: 同じ動画は1つのアセットとして定義し、全クリップが同一アセットを参照
2. **SRT字幕**: 文字起こしタイムスタンプに基づいて生成。無音削除時はTimeMapperで字幕位置を調整
3. **時間計算**: フレーム単位の丸めによる0.1秒程度の誤差は正常

## 配布

Homebrew tapで配布：
```bash
brew install coidemo/textffcut/textffcut
```

---

最終更新: 2026-04-21
