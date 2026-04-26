# タイトル画像生成 改善提案書

**作成日**: 2026-04-26
**ステータス**: Draft
**ブランチ**: `proposal/title-improvement`

## 1. 背景

ユーザー報告で 3 つの問題が確認された:

1. **改行されず文字が小さくなる**: 「炎上と逆差別 男女で扱いが違うのはなぜ?」が 1 行で描画され、画像 1080×1920 の上端しか占有しない (画像 #11)
2. **タイトルと最終字幕の内容が微妙にズレる**: タイトルに「逆差別」が含まれるが対応 SRT には登場しない
3. **`title.json` が生成されない clip がある**: 該当 clip では PNG のみ存在し JSON キャッシュが欠如

## 2. 真因 (Explore agent による調査結果)

| 問題 | 真因 |
|---|---|
| 1 (改行なし) | AI プロンプトで「2-3行に分割」と指示するが守られないケースがあり、後処理で強制分割するロジックがない。`_ensure_fit_height` の高さ制限フォールバックは font_size 縮小のみで改行追加なし |
| 2 (内容ズレ) | **AI に渡すインプットが `ClipSuggestion.title` + `keywords` (= Phase 1 の元動画全体話題検出時に生成) で、最終 SRT (= clip range の最終字幕) ではない**。情報源の非同期によって構造的にズレる |
| 3 (json 欠如) | バッチ AI 呼び出しが例外発生時、try/except で warning ログのみ出して PNG はフォールバックで生成、JSON キャッシュは保存されない |
| 上端のみ占有 | `padding_top` が動的調整されない。1 行で content_height が小さい時に縦中央配置するロジックがない |

## 3. 改善方針 (3 案を併行実装)

### 案 B: 改行強制ロジック (短期、保険的)

ユーザー要望:「8 文字以上は必ず改行」のような見やすさ保険。

#### 実装内容

**B-1. AI プロンプト強化** (`use_cases/ai/title_image_generator.py:521-552` `_DEFAULT_PROMPT`)
```
## デザインルール
1. 2-3行に分割（意味の切れ目、インパクト重視で改行）
   ★追加: タイトルが 8 文字を超える場合は必ず複数行に分割すること
   ★追加: 各 line の合計文字数は 12 文字以下を目安に
```

**B-2. 後処理バリデーション + 強制分割** (新規追加)

`design_title_layout()` (line 469) で AI 返却を受け取った後、`_parse_design_json` の直後で:

```python
# B-2: 1 line で 8 文字超のタイトルは強制分割
TITLE_FORCE_BREAK_THRESHOLD = 8
if len(design.lines) == 1 and reconstructed_total_chars > TITLE_FORCE_BREAK_THRESHOLD:
    # _split_title() で再分割し、design を作り直す
    parts = _split_title(reconstructed, max_lines=3)
    design = _rebuild_design_from_parts(parts, original_design=design)
    logger.info(f"AI returned 1-line for {len(reconstructed)}-char title; force-split into {len(parts)} lines")
```

**B-3. `_split_title` の閾値変更** (line 990)
```python
# Before
if len(title) <= 10:
    return [title]
# After (8 文字基準に統一)
if len(title) <= TITLE_FORCE_BREAK_THRESHOLD:
    return [title]
```

#### 工数: ~1.5 時間
#### 影響範囲: `title_image_generator.py` 中規模、既存テストに影響あり (要更新)

---

### 案 C: 縦中央配置ロジック (短期、視認性向上)

#### 実装内容

`render_title_image()` (line 1032) の中で:

```python
# C: content_height を測定して padding_top を動的調整
content_h = _measure_content_height(design, font_dir)
canvas_h = height
# 1080×1920 の縦動画では中央配置、横動画は上端に近く配置
if orientation == "vertical":
    new_padding = max(60, (canvas_h - content_h) // 2)
else:
    new_padding = design.padding_top  # 既存維持
design.padding_top = new_padding
```

ただし `_ensure_fit_height` との相互作用を考慮し、`_ensure_fit_height` 適用後に padding 計算する順序を検討。

#### 工数: ~1 時間
#### 影響範囲: `title_image_generator.py` 小規模、既存 FCPXML との位置整合性確認必要

---

### 案 A: SRT ベースのタイトル生成 (中期、構造的解決)

#### 実装内容

**A-1. AI に渡すインプットを最終 SRT に変更**

現状:
```
Phase 1 で AI が生成した ClipSuggestion.title + keywords
   → そのまま design_title_layout() / _batch() に渡す
```

修正後:
```
Phase 5.7 で clip range 内の最終 SRT を読み込む
   → SRT 全文を新プロンプト (= SRT 要約 + デザイン提案) に渡す
   → AI が SRT 内容を踏まえてキャッチーなタイトルを生成 + デザイン
```

**A-2. プロンプト分離**

新規ファイル: `prompts/title_image_design_from_srt.md` (or 既存 `title_image_design.md` を改修)

```
あなたは YouTube ショート動画のタイトルテキストデザイナーです。
以下の SRT 字幕の内容を踏まえて、SNS で目を引くキャッチーなタイトルを 1〜2 行 (合計 8〜16 文字目安)
で生成し、デザインを提案してください。

## SRT 字幕
{SRT_TEXT}

## 元の話題タイトル (参考、必ずしも従わなくて OK)
{ORIGINAL_TITLE}

## キーワード (参考)
{KEYWORDS}

## デザインルール
(B-1 と同じルール)
```

**A-3. バッチ呼び出し関数の引数変更**

`generate_title_images_batch()` (line 1762) のシグネチャに `srt_texts: list[str]` を追加。

呼び出し側 `suggest_and_export.py` で各 clip の SRT パスから本文を読み取り、リストで渡す。

#### 工数: ~3 時間
#### 影響範囲:
- `title_image_generator.py`: バッチ関数のシグネチャ変更
- `prompts/`: プロンプトファイル新規 or 改修
- `suggest_and_export.py`: SRT 読み込みロジック追加
- 既存テスト要更新

---

## 4. 実装順序

| ステップ | 案 | 効果 | 工数 |
|---|---|---|---|
| 1 | C (縦中央配置) | 既存タイトルが見やすくなる (即効性) | 1h |
| 2 | B (改行強制) | 1 行 PNG の再発防止 (保険) | 1.5h |
| 3 | A (SRT ベース) | タイトル/字幕ズレを構造的に解消 | 3h |

合計: ~5.5 時間。

順序の理由:
- C は既存挙動への影響が最小、まずユーザーが目に見える効果を確認できる
- B は AI が複数行を返さないケースの保険
- A を最後に持ってくることで、A の AI 改善効果が B/C の上に乗ってわかりやすい

## 5. 各案の検証方針

### 検証用 clip
- `videos/20260210_..._TextffCut/title_images/03_炎上と逆差別_男女で扱いが違うのはなぜ.png` (画像 #11、改行なし問題)
- `videos/20260210_..._TextffCut/title_images/01_AIは道具じゃなく"チーム"で使うべき理由.png` (リッチデザイン保持確認)
- 8 文字未満の短いタイトル (e.g. "AI格差の正体") - 改行されないことを確認
- 8 文字以上のタイトル - 改行されることを確認

### 検証方法
1. キャッシュから再生成 → before/after を HTML で比較 (PR #137 で使った手法)
2. 既存タイトル画像関連テスト 143 件パス確認
3. ユーザー実機で `textffcut clip` 実行 → 各 clip でタイトル + 字幕の整合性確認

## 6. リスク・検討事項

### A (SRT ベース) の副作用
- **`ClipSuggestion.title` と「実際生成されたタイトル」が異なる可能性**: clip suggestion JSON のメタデータ (title フィールド) と PNG のタイトル文字が乖離する → ファイル名命名規則 (`01_<title>.png`) との整合性をどう取るか
- **AI コスト増**: SRT 全文を AI に送るので API 入力トークン数 +50%程度。clip 候補生成時の1リクエストとは別なので、追加コスト発生
- **AI の「キャッチーな再生成」が元タイトルと違いすぎる場合**: ユーザー混乱の可能性。「元タイトルをベースにしつつ最大 ±2 文字程度の調整」を制約に入れる案もあり

### C (縦中央配置) の互換性
- 既存 FCPXML はタイトル PNG の **上端** を基準に position 計算している可能性
- 縦中央配置に変更すると既存 clip との見た目が変わる
- 対処: 配置時に `offset_y` を新計算 or padding_top を利用側で吸収

### B の AI プロンプト変更
- 既存の AI 呼び出しキャッシュは無効化される (= 既存 clip も再生成必要)
- prompts/ ディレクトリのファイルがないので `_DEFAULT_PROMPT` 直接編集
- 8 文字基準は font_size, orientation により変わるべきか? → 縦動画 (vertical) は 8 文字、横動画は 12 文字、等

## 7. ユーザー確認事項

1. **3 案すべて実装で OK か** (確認済み)
2. **8 文字基準は妥当か?** (font_size 190 で 1 行 11 文字程度が物理的限界。8 文字なら font_size を上げる余地あり)
3. **A の副作用「タイトル文字が元と違う場合」**: 元タイトルベースで微調整する範囲は?
4. **C の縦中央配置を縦動画のみに適用するか、横動画も含めるか**
5. **既存 PNG キャッシュをクリアして再生成するタイミング** (個別 clip ごと? 一括?)

## 8. 関連
- 提案 PR: (この PR)
- 関連 PR: #137 (タイトル画像 ループ穴修正)
- 該当ファイル: `use_cases/ai/title_image_generator.py` (1868 行)
- 該当 clip: `03_炎上と逆差別_男女で扱いが違うのはなぜ.png`
