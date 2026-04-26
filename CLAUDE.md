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

### v2.5.0 (2026-04-26) — 最新安定版
- **タグ**: `v2.5.0` (PR #143-#145 一括リリース)
- **動画内テキスト塗りつぶし: 1 clip = 1 合成 PNG 方式に完全置換** (PR #143):
  - 旧 v2.2.0 / v2.3.0 の drawbox 方式 (元動画 73 分すべてを再エンコード → `source_blurred.mp4` 4.2GB) を廃止
  - 新方式: clip 候補の `time_ranges` 範囲だけ OCR + track 化、**全 track の bbox を 1 枚の透過 PNG に OR 合成**
  - PNG は FCPXML の **V2 レーン** (動画の直上、frame の下) に asset-clip として配置 — 元動画は無加工
  - **clip 全範囲で常時表示** (時間切替なし) — 同じ lane=1 に複数 PNG を時間重複で並べると DaVinci で 1 枚しか描画されないため
  - **動画と同じ `<adjust-conform type="fit"/>` + `<adjust-transform scale anchor>` を blur PNG にも適用** → ズーム・アンカー・4K source・縦動画クロップで完全追従
  - ファイルサイズ: 4.2GB → 数十KB / clip (約 100,000 倍削減)
  - 処理時間: 4分16秒 → 数秒〜十数秒 / clip
  - DaVinci 上で塗りつぶしの位置・色・有無を編集可能 (clip ごとに 1 枚の PNG)
  - `time_ranges` を複数 segment 跨ぎで分割するロジックを `core/export.py` に追加 (frame/title/BGM の lane を blur あり時 +1 シフト)
  - sidecar version=2 で旧 v1 (1 track = 1 PNG) キャッシュは自動無効化
- **Text+ Fill Gaps しきい値を user 指定可に** (PR #145):
  - `TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES`: 10 → **9999** (≈5.5 min @30fps、実用上ほぼ無制限)
  - 旧 10 frame では字幕間の長い gap が埋まらず Resolve 上で繋がりが切れる問題を解消
  - CLI: `textffcut send --text-plus-max-fill-frames N`
  - GUI: 字幕エディタ「📺 DaVinciへ送信」エリアに number_input、`text_plus_max_fill_frames` キーで `settings_manager` に永続化
  - 0 で Fill Gaps を実質無効化可能
- **字幕編集画面の動画フォルダ selectbox 撤去** (PR #144):
  - 上部「🎥 動画ファイル選択」で選択済の動画から `_TextffCut/` を自動解決
  - 二重選択 UX を解消、動画選択は画面上部 1 箇所に集約
  - `subtitle_editor_srt_idx` key を base_dir 名込みに分離 (動画切替時の stale state 衝突防止)
- **削除済み**: `core/text_blur/{ffmpeg.py, chunk_worker.py}` (708 行)、`use_cases/auto_blur/auto_blur_use_case.py` (290 行)、`tests/unit/use_cases/test_auto_blur_use_case.py`
- **新規**: `use_cases/auto_blur/blur_overlay_use_case.py::BlurOverlayUseCase` (434 行)、`tests/unit/use_cases/test_blur_overlay_use_case.py`
- **キャッシュ**: `{video}_TextffCut/blur_overlays/{clip_id}.overlays.json` + PNG 群
- **CLI**:
  - `textffcut clip video.mp4`: デフォルトで blur overlay 自動生成
  - `textffcut clip --no-auto-blur`: 塗りつぶしを無効化 (旧 `--no-blurred-source` リネーム)
  - `textffcut --auto-blur` (top-level、文字起こしと並列の旧コマンド) は廃止
  - `textffcut send --text-plus-max-fill-frames N`: Fill Gaps しきい値指定
- **GUI**:
  - 文字起こし画面: 旧 「🔒 動画内テキスト自動塗りつぶし」 チェックボックスは削除 (clip 段階で動くため不要)
  - クリップ設定画面: 「🔒 動画内テキスト塗りつぶし (V2 オーバーレイ)」 チェックボックス (Apple Silicon Mac でのみ表示)
  - 字幕編集画面: 「Fill Gaps 最大フレーム数」 number_input (Text+ 自動変換 ON 時のみ有効)
  - 字幕編集画面: 動画フォルダ selectbox 撤去 (上部で選択した動画と自動連動)

### v2.4.0 (2026-04-26)
- **タグ**: `v2.4.0`
- **タイトル画像 改行強制 + 縦中央配置** (PR #140 / Phase B + C):
  - 11 文字超のタイトルが 1 行で文字小さく上端だけ占有する問題を解消
  - `_TITLE_FORCE_BREAK_THRESHOLD = 11` 文字超を `_enforce_line_break()` で強制分割
  - target_size 範囲内で `_center_design_in_target()` により縦中央配置 (bbox 測定 → padding_top 動的計算)
  - 縦動画・横動画両対応
- **タイトル画像 SRT ベース AI 生成** (PR #141 / Phase A):
  - タイトル/字幕の内容ズレを構造的に解消 (例: タイトルに「逆差別」が含まれるが SRT に登場しない問題)
  - AI インプットを Phase 1 の元動画全体話題検出から **clip 範囲の最終 SRT** に切り替え
  - パイプライン順序: Phase 5.6 (SRT 先行生成、新設) → 5.7 (タイトル画像) → 6 (FCPXML)
  - SRT モードでは AI 自由生成許可 (元 title からの大幅書き換え可)、ファイル名は元 title 維持
  - `prompts/title_image_candidates_from_srt.md` 新規 (SRT モード用プロンプト)
  - プロンプト全 5 ファイルで `{MAX_LINE_CHARS}` placeholder 化 (定数 `_TITLE_FORCE_BREAK_THRESHOLD` から流し込み)
  - `SuggestAndExportResult.srt_failed_count` 追加で SRT 生成失敗を集計

### v2.3.0 (2026-04-26)
- **タグ**: `v2.3.0` (PR #133-#137 一括リリース)
- **DaVinci Resolve への自動取り込み機能** (PR #134):
  - `textffcut send` コマンドで FCPXML + SRT を Resolve の現在開いているビンに 1 コマンドで取り込み
  - timeline 名は `00_MMDD_Clip{NN}` 自動連番、素材用 SE トラック自動 mute
  - GUI: 字幕エディタの「📺 DaVinciへ送信」ボタン
- **SRT→Text+ 自動変換機能 (Snap Captions 互換)** (PR #136):
  - `textffcut send --text-plus` (CLI/GUI ともデフォルト ON) で SRT を Fusion Text+ クリップへ自動変換
  - 事前準備として Media Pool root に `TextffCut` ビン + `Caption_Default` テンプレ配置時のみ動作 (未配置なら warning + スキップ)
  - 新規ビデオトラック自動追加 / Green 着色 / U+2028→\n 改行変換 / duration_multiplier 補正 / 端伸ばし
  - SRT は一時ファイル化して ImportMedia (Resolve の MediaPool 内部位置累積問題を回避)
  - Text+ 配置は SRT を Python で直接パース (subtitle track の Resolve 仕様による位置ずれを切り離す)
- **動画内テキスト自動塗りつぶし機能** (PR #135):
  - 命名注意: コード上は `auto_blur` (内部識別子・CLI フラグは互換性維持)、ユーザー向け表現は「塗りつぶし」で統一
  - 実装は `drawbox` による塗りつぶし (gaussian blur ではない). 将来 mosaic / gaussian も engine 切替で追加可能な設計
  - コメント欄・UI 文字・チャンネルロゴ等を自動検出して周囲色で塗りつぶし、DaVinci 取り込み前の前処理として使用
  - **Apple Vision API (ocrmac)** ベース検出 → Apple Silicon Mac 専用機能 (Neural Engine 活用、EasyOCR 比 2.4x 高速)
  - **drawbox 方式** で塗りつぶし (gblur より 5x 高速、色滲みなし、bbox 縁から自動色サンプリング)
  - **検出スキップ最適化**: フレーム差分で前回 bbox を再利用 (検出回数 -70%)
  - **フルチャンク並列化**: 4 並列で 64 分動画を 4分16秒で処理
- **タイトル画像 文字内ループ穴の白アウトライン隙間修正** (PR #137):
  - 「な」「は」「ぱ」「べ」「使」等の文字内ループ穴で白アウトラインがリング描画され隙間が見える問題を解消
  - `_fill_mask_holes()` で flood-fill により穴を埋め、面積上限で大穴/小穴を選別
  - outer_mask は全穴埋めでシルエット全体塗りつぶし、inner_mask は font_size に応じた小穴のみ埋め
- **word drop 根本修正** (PR #133):
  - filler-aware word 境界スナップで PR #122-124 の症状治療を改善
  - SRT 句読点除去ロジック追加
- **CLI**:
  - `textffcut --auto-blur video.mp4`: Whisper 文字起こしと**並列実行** (Whisper 21s + 塗りつぶし 25s が並走、5min 動画 26.6s で完了)
  - `textffcut clip video.mp4`: cache 自動利用、なければ警告 + 元動画
  - `textffcut clip --no-blurred-source`: 明示的に元動画使用
  - `textffcut send clip.fcpxml`: DaVinci 取り込み + Text+ 自動変換 (デフォ ON)
  - `textffcut send clip.fcpxml --no-text-plus`: Text+ 変換無効化
- **GUI**:
  - 文字起こし画面: 「🔒 動画内テキスト自動塗りつぶし」チェックボックス
  - クリップ生成画面: cache 存在時のみ「塗りつぶし版を利用」チェックボックス表示
  - 字幕エディタ: 「📺 DaVinciへ送信」ボタン + 「Text+ 自動変換」チェックボックス
- **キャッシュ**: `{video}_TextffCut/source_blurred.mp4` + params sidecar (params hash + 元動画 mtime/size で検証)
- **依存追加** (`pyproject.toml`):
  - `ocrmac>=1.0.0` (Apple Vision Framework wrapper)
  - `opencv-python>=4.10.0` (numpy 2 対応版)
  - `scipy>=1.10.0` (タイトル画像内ループ穴の連結成分判定)
  - numpy `<2.0` 制約撤去 (主要 dep の numpy 2 対応確認済)

### v2.1.1 (2026-04-23)
- **タグ**: `v2.1.1`
- **無音削除で word が消えるバグを修正** (PR #122/#123/#124):
  - `core/video.py::_rescue_missing_words` で無音削除後に silence 判定で落ちた word を救済
  - SRT 層の `_ORPHAN_WORD_TOLERANCE` を撤去 (構造的に不要、境界跨ぎ誤吸収バグも同時に解消)
  - 救済 range に 1 frame padding + 近接 keep マージで FCPXML 30fps 丸めの `duration="0/1s"` 問題を回避
  - GUI 経路 (`presentation/views/text_editor.py`) と CLI 経路 (`use_cases/ai/suggest_and_export.py`) の両方で transcription を伝播
- **設計整理** (CLAUDE.md 注意事項に追記, PR #125):
  - FCPXML 30fps フレーム丸め (`round(0.5)=0`) で壊れた asset-clip が生成される罠を明文化
  - 無音削除の word 救済を「GUI/CLI 両経路で伝播」の運用注意として記録

### v2.1.0 (2026-04-22)
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
│   ├── video.py             # 動画処理・無音検出
│   ├── fcpxml_relink.py        # 別マシン向けFCPXMLパス書き換え
│   └── text_blur/              # 動画内テキスト検出+ぼかし (v2.2.0)
│       ├── detector.py            # OcrmacDetector + Box / merge_boxes
│       ├── tracker.py             # IoU マッチングで track 化
│       ├── ffmpeg.py              # filter_complex 構築 + 実行
│       └── chunk_worker.py        # full-chunk 並列化ワーカー
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
├── use_cases/auto_blur/     # 動画内テキスト塗りつぶしオーバーレイ (v2.5.0)
│   └── blur_overlay_use_case.py  # BlurOverlayUseCase: clip ごとに PNG 群生成
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

# DaVinci Resolve 取り込み (FCPXML + SRT + Text+ 自動変換, デフォ ON)
textffcut send path/to/clip.fcpxml

# Text+ 自動変換を無効化 (FCPXML + SRT のみ)
textffcut send path/to/clip.fcpxml --no-text-plus

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
4. **FCPXML フレーム丸め (30fps)**: `duration` は `round(seconds × 30)` で frame に量子化される。`round(0.5)=0`（banker's rounding）で `duration="0/1s"` が生成されるとアセット参照が壊れるため、無音削除後の `keep_range` は **最低 1 frame (33ms) の duration を保証** する必要がある。`core/video.py::_rescue_missing_words` の `_RESCUE_PADDING` がこれを担保。
5. **無音削除の word 救済**: `remove_silence_new` は `transcription_words` 引数を受け取る。GUI (`presentation/views/text_editor.py`) と CLI (`use_cases/ai/suggest_and_export.py`) の両方から `transcription` を伝播する必要がある。伝播が抜けると silence 判定で落とされた short word が SRT から欠落する。
6. **auto_blur (v2.5.0 PNG オーバーレイ方式)**: Apple Silicon Mac 専用 (`ocrmac`/Apple Vision API 依存)。`use_cases/auto_blur/blur_overlay_use_case.py::is_apple_silicon()` で起動時にチェック、非対応環境では警告のみ出して機能無効化。元動画は再エンコードせず、clip 候補の `time_ranges` だけ OCR + track 化して **全 track の bbox を 1 枚の合成 PNG** に OR 合成、FCPXML の **V2 レーン** (動画の直上、frame の下) に asset-clip として配置する。**clip 全範囲で常時表示** (時間切替なし) — 同じ lane=1 に複数 PNG を時間重複で並べると DaVinci で 1 枚しか描画されないため。**動画と同じ `<adjust-conform type="fit"/>` + `<adjust-transform scale anchor>`** を blur PNG にも適用するため、ズーム・アンカー・4K source・縦動画クロップで完全追従する。キャッシュは `{video}_TextffCut/blur_overlays/{clip_id}.overlays.json` + `{clip_id}.png` (params hash + 元動画 mtime/size + time_ranges + sidecar version=2 で検証、旧 v1 = 1 track = 1 PNG キャッシュは自動無効化)。`core/export.py::_build_fcpxml` 内で blur ありの場合 frame/title/BGM lane を +1 シフトする (`lane_offset` 変数)。time_ranges を複数 segment 跨ぎで分割するロジックは同関数内のループ。`--no-auto-blur` / GUI checkbox OFF で明示的に無効化可。
7. **textffcut send --text-plus (Snap Captions 互換)**: SRT を Fusion Text+ クリップへ自動変換する。**CLI/GUI ともデフォルト ON**。事前準備として Media Pool root に `TextffCut` ビン + `Caption_Default` という Fusion Title (Text+) テンプレートを置いた場合のみ動作し、未配置なら warning + スキップ (preset の `--no-frame` 等と同じ流儀)。実装は `infrastructure/davinci_resolve.py::convert_subtitles_to_text_plus()`。Snap Captions Lua の挙動を独自再実装 (再配布禁止のためコード流用なし)。挙動の要点:
   - 新規ビデオトラックを最上位に追加 → そこへ配置 (既存トラック衝突回避)
   - U+2028 → `\n` 改行変換 (Resolve は SRT 改行を Line Separator で保持)
   - duration_multiplier 補正: テスト clip 配置→測定→削除で Fusion comp の内部 duration による短縮を打ち消す。これがないと隣接 Text+ クリップ間に隙間が生じる
   - 端伸ばし (extend_edges): 最初の字幕をタイムライン先頭、最後の字幕を末尾まで延長
   - Fill Gaps: 字幕間 gap を埋める. デフォ `TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES = 9999` (≈5.5 min @30fps、実用上ほぼ無制限)。CLI `--text-plus-max-fill-frames N`、GUI 字幕エディタの number_input、settings_manager で永続化 (`text_plus_max_fill_frames` キー)。0 にすれば実質無効化。
   - 完了時に subtitle track 1 を無効化 (Text+ と Subtitle の二重表示回避)
   - **API 罠**: `AppendToTimeline()` は配置失敗時も `[None]` を返す (要素ごと `GetName() is None` 判定)。`SetInput("StyledText", text)` の戻り値は False を返すが副作用は効いている (戻り値チェック禁止)。
8. **タイトル画像 文字内ループ穴の白アウトライン (PR #137)**: 「な」「は」「ぱ」「べ」「使」等で白アウトラインがリング描画されると穴の周辺に細リングが残って見た目が汚い。`use_cases/ai/title_image_generator.py::_fill_mask_holes()` で flood-fill により穴を埋めて対処。outer_mask は全穴埋めでシルエット全体塗りつぶし、inner_mask は `font_size × 0.06` の二乗以下の小穴のみ埋める (大きいループ穴を埋めると黒インナーが文字細部まで広がって潰れるため)。**境界全周から flood-fill 起点を取る** ことが重要 (1点起動だと複数文字間で stroke 分断された背景が穴と誤認され「ひどい」状態になる)。連結成分判定は `scipy.ndimage.label`。
9. **タイトル画像 改行強制 + 縦中央配置 (Phase B/C、PR #140)**: AI が 1 行で長すぎるタイトルを返す問題と、画像上端のみ占有する問題を解消。`_TITLE_FORCE_BREAK_THRESHOLD = 11` 文字を超える 1 line は `_enforce_line_break()` で強制分割。target_size 指定時は `_center_design_in_target()` で content_height bbox 測定 → padding_top 動的計算 → 縦中央配置。
10. **タイトル画像 SRT ベース AI 生成 (Phase A、PR #141)**: タイトル画像の AI インプットを Phase 1 (元動画全体話題検出) の `ClipSuggestion.title + keywords` から **clip 範囲の最終 SRT 字幕** に切り替え、タイトルと字幕の内容ズレを構造的に解消。
    - **パイプライン順序**: Phase 5.6 (SRT 先行生成、新設) → 5.7 (タイトル画像、SRT パスを AI に渡す) → 5.8 (アンカー検出) → 6 (FCPXML 生成、SRT は Phase 5.6 で書き出し済)
    - **AI 自由生成許容**: SRT モードでは `reconstructed != title` のバリデーションを緩和。AI が SRT 内容を踏まえてタイトル文字列を再生成 (元 title からの大幅書き換え可)
    - **ファイル名と PNG 内タイトルの乖離**: ファイル名は元 `suggestion.title` でサニタイズ維持 (= ファイル名規則保護)、PNG 内タイトルは AI 自由生成版。両者が乖離する仕様は意図したもの (clip 内容判別は PNG 視覚確認で行う設計)
    - **プロンプト**: `prompts/title_image_candidates_from_srt.md` (SRT モード用)、`title_image_candidates.md` (既存モード用) の 2 種類。`design_title_layout_candidates(srt_text=...)` で分岐
    - **`{MAX_LINE_CHARS}` placeholder**: プロンプト内の文字数制限は `_TITLE_FORCE_BREAK_THRESHOLD` 定数から流し込み (= プロンプトとコード定数の同期維持)
    - **失敗時 graceful degradation**: SRT 生成失敗 → `SuggestAndExportResult.srt_failed_count` でカウント、対応 clip は title ベースにフォールバック。AI 候補生成失敗 → fallback design (元 title) で render
11. **リリース手順 (本体 + Homebrew tap)**: TextffCut の version up は 2 リポジトリ (本体 + `Coidemo/homebrew-textffcut`) に反映する 8 ステップ手順。詳細手順とつまずきポイントは memory `release_workflow_runbook.md` に記録。要点のみ記載:
    - **CLAUDE.md と pyproject.toml の version 整合性**: CLAUDE.md は手動更新で pyproject.toml とずれやすい。release 前に両方確認。
    - **`gh release create` は使えない**: tag push で GitHub Actions が空 Release を自動作成するため `gh release create` は HTTP 422。`gh release edit vX.Y.Z --notes "..."` で notes を後付けする。
    - **Homebrew tap の `commit.gpgsign=true`**: `Coidemo/homebrew-textffcut` clone 後は `git config --local commit.gpgsign false` を実行しないと commit 失敗 (本体 repo は false 設定済み)。
    - **`git commit --amend --no-edit` の事故**: 署名失敗で commit が無い状態で amend すると過去 (= 前回リリース) コミットが破壊される。失敗時は `git status` で状況確認してから amend 判断。`git reset --hard origin/main` で復旧可能 (push 前なら)。
    - **`docs/` は .gitignore で除外**: 新規ドキュメントは `git add -f` で強制追加が必要。
    - バージョン戦略: 機能追加 → minor up、修正のみ → patch up、複数 PR 一括 → minor up が現実的。

## 配布

Homebrew tapで配布：
```bash
brew install coidemo/textffcut/textffcut
```

---

最終更新: 2026-04-26 (v2.5.0 リリース、PR #143/#144/#145 を含む)
