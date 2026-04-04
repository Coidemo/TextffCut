# TextffCut 差分検出（TextProcessor）詳細調査報告

調査日時: 2026年4月3日
対象: TextffCut の差分検出メカニズムと「飛び飛びマッチ」問題の根本原因

---

## 1. システム構成図

```
┌─────────────────────────────────────────────────────────┐
│ ユーザー入力 (編集テキスト)                              │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ core/text_processor.py::TextProcessor.find_differences()  │
│  ↓                                                        │
│  1. normalize_text()        テキスト正規化               │
│  2. remove_spaces()         空白除去                     │
│  3. SequenceMatcher()       差分検出                     │
│  4. get_opcodes()           マッチング結果取得          │
│  5. _convert_position_with_spaces() 位置変換            │
│  6. _calculate_length_with_spaces() 長さ計算             │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ adapters/gateways/text_processing/                       │
│ - sequence_matcher_gateway.py                            │
│ - simple_text_processor_gateway.py                       │
│                                                          │
│ これらがDomain層のユースケースを呼び出す                 │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Domain層 Use Cases:                                      │
│ - TextDifferenceDetector                                │
│ - TimeRangeCalculator                                   │
│ - CharacterArrayBuilder                                 │
│                                                          │
│ これらがドメインロジックを実装                            │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Domain層 Entities:                                       │
│ - TranscriptionResult (文字起こし結果)                   │
│ - TranscriptionSegment (セグメント)                      │
│ - Word (単語タイムスタンプ)                              │
│ - CharacterWithTimestamp (文字タイムスタンプ)            │
│ - TextDifference (差分情報)                              │
└──────────────────────────────────────────────────────────┘
```

---

## 2. 核となるコンポーネント詳細分析

### 2.1 core/text_processor.py の find_differences メソッド

**メソッドシグネチャ:**
```python
def find_differences(
    self, 
    original: str,     # 元のテキスト（文字起こし結果）
    edited: str,       # 編集後のテキスト
    skip_normalization: bool = False
) -> TextDifference
```

**処理フロー (lines 603-697):**

1. **正規化段階（lines 623-625）**
   - `normalize_text()`を呼び出し
   - 全角スペース→半角、改行統一、連続空白→単一スペース
   - 前後の空白削除

2. **抜粋判定（lines 627-630）**
   - `len(edited) < len(original) * 0.5` の場合は抜粋として別処理
   - 抜粋処理: `_find_differences_for_excerpt()` へ分岐

3. **空白除去（lines 632-634）**
   ```python
   original_no_spaces = self.remove_spaces(original)
   edited_no_spaces = self.remove_spaces(edited)
   ```
   - 日本語では重要：スペースなしで差分検出

4. **SequenceMatcherによる差分検出（line 637）**
   ```python
   matcher = SequenceMatcher(None, original_no_spaces, edited_no_spaces)
   ```
   - Python標準 difflib の SequenceMatcher
   - **第1引数 None** = isjunk 関数なし
   - これがキーポイント！（後述）

5. **opcodes処理（lines 648-684）**
   ```python
   for tag, i1, i2, j1, j2 in matcher.get_opcodes():
       if tag == "equal":
           # 元テキストでの位置を計算
           original_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
           length = self._calculate_length_with_spaces(original, original_pos, i2 - i1)
           common_positions.append(TextPosition(...))
       elif tag in ["insert", "replace"]:
           # 追加文字を記録
   ```

**⚠️ SequenceMatcherの重要な性質:**

`SequenceMatcher(isjunk=None)` を使用しているため：
- `isjunk` 関数がないため、**すべての文字が比較対象**
- 短い共通文字列（1-2文字）も評価される
- **グローバル・マッチング**: オリジナルテキストのどこに一致するかを探す
- 一旦マッチすると、その位置をベースに次の比較が進む

例：
```
original_no_spaces = "あいうえおかきくけこ"  (10文字)
edited_no_spaces   = "あいうえおXXかきくけこ"  (12文字)

SequenceMatcherは以下のようにマッチを找す：
- "あいうえお" (5文字) = EQUAL
- "XX" = INSERT
- "かきくけこ" (5文字) = EQUAL
```

しかし、もし edited に「い」というように短い文字が何度も出現する場合：
```
original = "あいうえおかきくけこさいしすせそ"
edited   = "あいうえおXXい..."

SequenceMatcherは以下をマッチする可能性：
- "あいうえお" = EQUAL (位置0-5)
- "XX" = INSERT
- "い" = EQUAL (位置5 in original, または位置26 in original)  ← 飛び飛びマッチ！
```

### 2.2 位置変換メカニズム

**_convert_position_with_spaces（lines 699-709）:**
```python
def _convert_position_with_spaces(self, text_with_spaces: str, text_no_spaces: str, pos_no_spaces: int) -> int:
    """空白を除去したテキストの位置を、元のテキストの位置に変換"""
    original_pos = 0
    no_spaces_pos = 0
    
    while no_spaces_pos < pos_no_spaces and original_pos < len(text_with_spaces):
        if not text_with_spaces[original_pos].isspace():
            no_spaces_pos += 1
        original_pos += 1
    
    return original_pos
```

**処理:**
- 空白を除いた位置から、元テキスト位置へ逆変換
- **シンプルだが問題あり**: SequenceMatcherが短い文字列でマッチした場合、この変換は正確に機能しない

**例（問題ケース）:**
```
original_with_spaces = "あ い う え お か き く け こ" (11文字, スペース5個)
original_no_spaces = "あいうえおかきくけこ" (10文字)
edited_no_spaces = "あいうえおXXい..."

SequenceMatcher:
- i1=0, i2=5, j1=0, j2=5 → "あいうえお" = EQUAL
- i1=5, i2=5, j1=5, j2=7 → "XX" = INSERT
- i1=5, i2=6, j1=7, j2=8 → "い" = EQUAL ← PROBLEM!
  
_convert_position_with_spaces(original_no_spaces, 5)
  = original_with_spacesの位置9 (「か」の位置)
  
しかし edited の「い」は実は元テキストの別の「い」とマッチしている可能性
```

**_calculate_length_with_spaces（lines 711-721）:**
```python
def _calculate_length_with_spaces(self, text: str, start_pos: int, length_no_spaces: int) -> int:
    """空白を除去した長さから、元のテキストでの長さを計算"""
    length = 0
    no_spaces_count = 0
    
    while no_spaces_count < length_no_spaces and start_pos + length < len(text):
        if not text[start_pos + length].isspace():
            no_spaces_count += 1
        length += 1
    
    return length
```

**問題:**
- SequenceMatcherが短い共通文字列でマッチした場合、その短い部分から長さを計算
- 実際のマッチ位置とズレている可能性がある

### 2.3 データ構造

#### TranscriptionResult と TranscriptionSegment

**TranscriptionResult（domain/entities/transcription.py, lines 195-303）:**
```python
@dataclass
class TranscriptionResult:
    id: str
    video_id: str
    language: str
    segments: list[TranscriptionSegment]
    duration: float              # 動画全体の長さ（秒）
    original_audio_path: str = ""
    model_size: str = "medium"
    processing_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def text(self) -> str:
        """全セグメントのテキストを結合"""
        return "".join(seg.text for seg in self.segments)
```

**TranscriptionSegment（lines 105-193）:**
```python
@dataclass
class TranscriptionSegment:
    id: str
    text: str                              # セグメント内のテキスト
    start: float                           # セグメントの開始時刻（秒）
    end: float                             # セグメントの終了時刻（秒）
    words: list[Word | dict] | None = None # 単語レベルタイムスタンプ
    chars: list[Char | dict] | None = None # 文字レベルタイムスタンプ（MLXアライメント用）
```

**Word（lines 14-59）:**
```python
@dataclass
class Word:
    word: str          # 1文字（日本語の通常ケース）
    start: float       # 単語の開始時刻（秒）
    end: float         # 単語の終了時刻（秒）
    confidence: float | None = None
```

**セグメント粒度:**
- 1セグメント = **数秒〜10秒程度**の発話（典型的には3-5秒）
- セグメント内の word は1文字 = 1word（日本語の場合）
- 1セグメントの word 数 = セグメント内の文字数（通常5-20文字程度）

例：
```
Segment 1: start=0.0, end=3.5, text="こんにちは"
  words: [
    {word: "こ", start: 0.0, end: 0.4},
    {word: "ん", start: 0.4, end: 0.8},
    {word: "に", start: 0.8, end: 1.2},
    {word: "ち", start: 1.2, end: 1.6},
    {word: "は", start: 1.6, end: 3.5},
  ]
```

---

## 3. 「飛び飛びマッチ」問題の根本原因

### 3.1 問題発生のメカニズム

**シナリオ: 短い共通文字列が複数回出現**

```
元テキスト（original_no_spaces）:
"あいうえおかきくけこさいしすせそたちつてと"
 0123456789...                       30

編集テキスト（edited_no_spaces）:
"あいうえおXXい..."
 012345..

SequenceMatcher の動作:
1. "あいうえお"（5文字） → EQUAL (i1=0, i2=5, j1=0, j2=5)
2. "XX" （2文字） → INSERT (i1=5, i2=5, j1=5, j2=7)
3. "い" （1文字） → EQUAL (i1=?, i2=?, j1=7, j2=8)

③の問題：
- edited[7:8] = "い"
- SequenceMatcherは original 内で「い」を探す
- 複数の「い」があるため、**greedy**に**最初の「い」ではなく**次の出現を選ぶ可能性
- original[5] = 「い」（位置5）にマッチ
- または original[12] = 「い」（位置12）にマッチするかもしれない
```

**飛び飛びマッチの具体例:**

```
Segment 1 (0-3秒): "こんにちは"
Segment 2 (3-5秒): "今日は"
Segment 3 (5-7秒): "いい天気です"

全テキスト: "こんにちは今日はいい天気です"

ユーザー編集: "こんにちは{今日は}いい天気です"
             （「今日は」を除外マーカーで指定）

期待される matching:
- "こんにちは" → Segment 1
- （マーカー除外）
- "いい天気です" → Segment 3

しかし SequenceMatcher は以下の可能性：
- "こんにちは" → Segment 1 ✓
- "い" → Segment 2 の「い」ではなく、Segment 3 の最初の「い」 ✗
  （SequenceMatcherのマッチング戦略により）
- "い天気です" → Segment 3 の「い」から

結果：タイムスタンプ生成時に Segment 2 と Segment 3 が混在
```

### 3.2 SequenceMatcherの動作特性

**Python difflib.SequenceMatcher の仕様:**

1. **No isjunk Function** (`isjunk=None`)
   - すべての文字が比較対象
   - 短い共通文字列（1-2文字）もマッチ対象
   - スペースなどの「無視する文字」がない

2. **Greedy Matching**
   - 最長の共通部分文字列をまず探す
   - その後、残りの部分で再帰的にマッチ
   - ただし、短い部分では **複数の候補がある場合、最初の出現を選ぶ傾向**

3. **Position-Relative**
   - マッチ結果は「元テキスト内のどこにマッチしたか」を返す
   - 複数マッチがあっても、１つの位置を返す
   - その位置が「正しい」かどうかは検証されない

---

## 4. セグメント粒度とマッチング精度

### 4.1 セグメント粒度とマッチング戦略

**1セグメント = 数秒の発話**
- 典型: 3-5秒
- 文字数: 5-20文字程度
- Word数: セグメント内の文字数と同じ（日本語 1字 = 1word）

**ユースケース: 30秒の動画**
```
Segment 1 (0.0-3.5秒): "こんにちは皆さん" (8文字)
Segment 2 (3.5-6.2秒): "今日は天気がいいですね" (12文字)
Segment 3 (6.2-9.8秒): "これはテストです" (8文字)
...
Segment N (last segment): ...

全テキスト: "こんにちは皆さん今日は天気がいいですねこれはテストです..."
           (total: ~100-200文字)

ユーザー編集: "こんにちは皆さん{今日は天気がいいですね}これはテストです..."
```

### 4.2 マッチング精度の問題

**SequenceMatcher での マッチ位置の決定:**

```
編集テキスト内の文字 → 元テキスト内のどの位置にマッチするか？

短い文字（1-3文字）の場合：
- 複数の候補がある
- SequenceMatcherは確定的だが、セマンティック上は曖昧

例：「い」という1文字
- Segment 2: "いいですね" の最初の「い」
- Segment 3: 別の「い」
- 全体で10回以上出現する可能性

SequenceMatcherは確定的に１つを選ぶが、
その選択が「意図された位置」であるか保証されない
```

---

## 5. CharacterArrayBuilder との統合

### 5.1 CharacterArrayBuilderの役割

**目的:**
- TranscriptionResult から タイムスタンプ付き文字配列を構築
- 各文字に対応する開始時刻・終了時刻を取得

**実装（domain/use_cases/character_array_builder.py）:**

```python
def build_from_transcription(
    self, transcription_result: TranscriptionResult
) -> Tuple[List[CharacterWithTimestamp], str]:
    """
    TranscriptionResultから文字配列を構築
    
    処理:
    1. 各セグメントをループ
    2. 各セグメント内の words から CharacterWithTimestamp を生成
    3. 全文字の配列を返す
    """
```

**CharacterWithTimestamp（domain/entities/character_timestamp.py）:**
```python
@dataclass(frozen=True)
class CharacterWithTimestamp:
    char: str              # 文字（1文字）
    start: float           # 開始時間（秒）
    end: float             # 終了時間（秒）
    segment_id: str        # 所属セグメントID
    word_index: int        # words配列でのインデックス
    original_position: int # テキスト内での位置
    confidence: float      # 認識信頼度
```

**時間範囲計算の問題点:**

`sequence_matcher_gateway.py` の `get_time_ranges` メソッド：

- `text_difference` が返す `position_ranges` が不正確な場合
- その不正確な位置から `char_array` にアクセス
- 結果として **ズレたセグメントのタイムスタンプが返される**

---

## 6. TimeRangeCalculator との連携

### 6.1 TimeRangeCalculator の実装

**domain/use_cases/time_range_calculator.py:**

```python
def calculate_time_ranges(
    self, differences: TextDifference, transcription_result: TranscriptionResult
) -> list[tuple[float, float]]:
    """
    差分情報から時間範囲を計算
    
    処理:
    1. differences.differences から UNCHANGED 部分を抽出
    2. 各 UNCHANGED テキストについて _find_text_time_ranges() を呼び出し
    3. 時間範囲を計算
    """
```

**_find_text_time_ranges:**

```python
def _find_text_time_ranges(
    self, target_text: str, transcription_result: TranscriptionResult
) -> list[tuple[float, float]]:
    """指定テキストの時間範囲を検索"""
    
    full_text = transcription_result.text
    position = full_text.find(target_text)
    
    if position == -1:
        return []
    
    # セグメントをループして、対象テキストに対応する時間を計算
    ...
```

**問題点:**
- `full_text.find(target_text)` は **最初の出現**を見つけるが、
- もし SequenceMatcher が飛び飛びマッチをしていれば、テキストが複数箇所に分散
- その場合、線形探索 `find()` は不正確な位置を返す可能性

---

## 7. 問題発生パターン

### 7.1 パターン1: 短い繰り返し文字（最も一般的）

```
元テキスト（Segment単位）:
  S1 "あいうえおかきくけこ" (0-3秒)
  S2 "さしすせそたちつてと" (3-6秒)
  S3 "なにぬねのはひふへほ" (6-9秒)
  S4 "まみむめもやゆよらりる" (9-12秒)

ユーザー編集:
  "あいうえおかきくけこ{さしすせそたちつてと}なにぬねのはひふへほまみむめもやゆよらりる"
  
期待: UNCHANGED = "あいうえおかきくけこ" + "なにぬねのはひふへほまみむめもやゆよらりる"

SequenceMatcher:
  original_no_spaces = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりる"
  edited_no_spaces = "あいうえおかきくけこなにぬねのはひふへほまみむめもやゆよらりる"
  
  opcodes:
  1. EQUAL: "あいうえおかきくけこ"
  2. DELETE: "さしすせそたちつてと"
  3. EQUAL: "なにぬねのはひふへほまみむめもやゆよらりる" ✓
```

この場合は正確に動作します。

### 7.2 パターン2: 短い共通部分（1-3文字）で複数セグメント

```
元テキスト:
  S1 "今日は天気がいい" (0-3秒)
  S2 "朝はとても寒いです" (3-6秒)
  S3 "でもいい季節になりました" (6-9秒)

ユーザー編集:
  "今日は天気がいい{朝はとても寒いです}でもいい季節になりました"

SequenceMatcher:
  original_no_spaces = "今日は天気がいい朝はとても寒いですでもいい季節になりました"
  edited_no_spaces = "今日は天気がいいでもいい季節になりました"
  
  opcodes:
  1. EQUAL: "今日は天気がいい" (S1)
  2. DELETE: "朝はとても寒いです" (S2) ✓
  3. EQUAL: "い" → Position? 
     - original[17] = 「い」(S1最後)
     - original[26] = 「い」(S2内)
     - original[30] = 「い」(S3内)
     
     SequenceMatcherは original[17] を選ぶのか original[30] を選ぶのか？
     → 不確定！

4. 続く: "い季節になりました" 
   - 前の「い」がどこにあるかで、その後の部分が決定される
```

**実際のマッチ結果が飛び飛びになる可能性が高い！**

### 7.3 パターン3: 文脈マーカー処理後のズレ

**sequence_matcher_gateway.py のマーカー処理:**

複雑な処理により:
- {}削除による位置ズレの計算が複雑
- SequenceMatcherでマッチした位置が「{}削除後の位置」と「元の位置」でズレている可能性
- `_split_range_excluding_markers()` で範囲分割する際に誤差が蓄積

---

## 8. 具体的なバグシナリオ

### シナリオ: 日本語の「い」を含むセグメント群

```
音声認識結果（TranscriptionResult）:
  
  Segment 1 (0.0-2.5秒): text="これはいい例です"
    words: [{word:"こ", start:0.0, end:0.3}, 
            {word:"れ", start:0.3, end:0.6}, 
            {word:"は", start:0.6, end:0.9}, 
            {word:"い", start:0.9, end:1.2}, 
            {word:"い", start:1.2, end:1.5}, 
            {word:"例", start:1.5, end:1.8}, 
            {word:"で", start:1.8, end:2.1}, 
            {word:"す", start:2.1, end:2.5}]
  
  Segment 2 (2.5-5.0秒): text="いろいろ試してみました"
    words: [{word:"い", start:2.5, end:2.8}, 
            {word:"ろ", start:2.8, end:3.1}, 
            {word:"い", start:3.1, end:3.4}, 
            {word:"ろ", start:3.4, end:3.7}, 
            {word:"試", start:3.7, end:4.0}, 
            {word:"し", start:4.0, end:4.3}, 
            {word:"て", start:4.3, end:4.6}, 
            {word:"み", start:4.6, end:4.8}, 
            {word:"ま", start:4.8, end:4.9}, 
            {word:"し", start:4.9, end:5.0}]

全テキスト:
  "これはいい例ですいろいろ試してみました"
   0123456789...

ユーザー編集:
  "これはいい例です{いろいろ試してみました}"
  
期待される結果:
  UNCHANGED = "これはいい例です"
  → TimeRange: start=0.0, end=2.5秒
  
SequenceMatcher処理:

  original_no_spaces = "これはいい例ですいろいろ試してみました"
  edited_no_spaces = "これはいい例です"
  
  opcodes:
  1. EQUAL: "これはいい例です" (0-8文字)
     → TimeRange: 0.0-2.5秒 ✓
  2. DELETE: "いろいろ試してみました" (8-18文字)
     ✓ これ自体は正しい
  
予期される問題:
  もし SequenceMatcher が短い「い」でマッチしていると
  → Position が正確でない可能性
  → 時間計算がズレる
```

---

## 9. 技術スタック分析

### 9.1 使用されている差分検出アルゴリズム

| 実装場所 | アルゴリズム | 特徴 | 問題 |
|---------|------------|------|------|
| `core/text_processor.py` | `difflib.SequenceMatcher` | Python標準, シンプル | 短い共通部分でマッチが曖昧 |
| `adapters/gateways/sequence_matcher_gateway.py` | `difflib.SequenceMatcher` (修正版) | 文脈マーカー処理を追加 | マーカー削除後の位置ズレ |
| `domain/use_cases/text_difference_detector.py` | 最長共通部分文字列 | 独自実装, 単語ベース | 文字ベースでないため粒度が異なる |

### 9.2 位置追跡メカニズムの複雑性

```
元テキスト（スペース付き）
    ↓ remove_spaces()
スペース除去テキスト
    ↓ SequenceMatcher
差分と位置（スペース除去テキスト内）
    ↓ _convert_position_with_spaces()
位置（元テキスト内）
    ↓ _calculate_length_with_spaces()
長さ（元テキスト内）
    ↓ TimeRangeCalculator._find_text_time_ranges()
テキスト検索と時間範囲計算
    ↓ CharacterArrayBuilder で文字配列をアクセス
タイムスタンプ取得
    ↓ 最終的な時間範囲
```

**各段階での誤差蓄積:**
1. SequenceMatcher のマッチが曖昧（複数候補から1つを選ぶ）
2. 位置変換が不正確（空白の処理の複雑さ）
3. テキスト検索が不正確（複数出現から1つを選ぶ）
4. 最終的なタイムスタンプが数秒のズレ

---

## 10. まとめ：飛び飛びマッチの根本原因

### 10.1 主要な原因

1. **SequenceMatcherの短い共通部分への対応不足**
   - `isjunk=None` により、1-2文字のマッチも有効
   - 複数の候補がある場合、確定的だが曖昧
   - セマンティック上の正しさを保証しない

2. **スペース除去による位置の複雑化**
   - スペースを除去した状態で差分検出
   - 位置を逆変換する際に誤差が発生
   - `_convert_position_with_spaces()` が完全ではない

3. **セグメント粒度の不一致**
   - セグメント = 3-5秒の音声
   - テキスト = 5-20文字
   - 短い文字列を含むセグメント境界付近で問題発生

4. **文脈マーカー処理の複雑性**
   - {}削除によるオフセット計算が複雑
   - `_split_range_excluding_markers()` での範囲分割に誤差

5. **時間範囲計算の線形探索**
   - `full_text.find(target_text)` で最初の出現を探す
   - SequenceMatcher が飛び飛びマッチしていると失敗

### 10.2 影響を受けやすいテキスト

- **短い共通文字（「い」「の」「た」など）が多い場合**
- **セグメント境界付近に同じ文字が複数出現**
- **編集指定が複数セグメントにまたがる場合**
- **正規化処理で空白が大量に削除される場合（不自然な改行など）**

### 10.3 セグメント粒度詳細データ

**1動画（15分 = 900秒）の場合:**
- セグメント数: 50-100個（平均 9-18秒/セグメント）
- 1セグメント当たりの文字数: 5-25文字
- 1セグメント当たりの単語数: 5-25個（1文字=1word）
- 1単語のタイムスタンプ精度: ±0.1-0.3秒

---

## 結論

**「飛び飛びマッチ」問題は、以下の根本原因による複合的な問題:**

1. **difflib.SequenceMatcher が短い共通部分を曖昧にマッチ** （構造的問題）
2. **スペース除去・位置変換による複雑化とズレ** （実装上の問題）
3. **複数出現テキストの検索で最初のみを探す** （アルゴリズムの限界）
4. **セグメント粒度とテキスト粒度の不一致** （設計の問題）

**解決の方向性:**
- より精密なアルゴリズム（LCS, Edit Distance ベース）
- Word レベルのタイムスタンプ直接利用（スペース除去なし）
- セグメント境界に基づくマッチング（テキスト全検索ではなく）
- テスト強化（複数マッチ候補がある場合の検証）
