# SRT字幕の改行位置とタイミング問題の調査報告

## 1. 発見された問題

### 1.1 不自然な改行位置
**現象**：
```srt
1
00:00:00,000 --> 00:00:02,100
<b>6月5日の木曜日かな木
曜日はい8時でございま</b>

2
00:00:02,200 --> 00:00:04,299
<b>す</b>
```

**問題点**：
1. 「木曜日」が「木」と「曜日」で分割されている
2. 「ございます」が「ございま」と「す」で分割されている
3. 2番目のエントリが「す」1文字のみ

### 1.2 音声とのタイミングずれ
- 1つのセンテンス「6月5日の木曜日かな木曜日はい8時でございます」が不自然に分割
- 「す」だけが独立したエントリになっており、音声の自然な区切りと一致しない

## 2. 原因分析

### 2.1 改行位置の問題

#### 現在の禁則処理ルール（japanese_line_break.py）
- 行頭禁則文字（、。など）
- 行末禁則文字（（［など）
- 英単語・数字の連続
- 特定パターン（日付など）

**不足している処理**：
1. **日本語の単語境界認識**がない
   - 「木曜日」「ございます」などの一般的な単語を認識できない
   - 形態素解析などの単語分割機能が未実装

2. **文節単位での分割**が考慮されていない
   - 「木曜日かな」は1つの文節として扱うべき
   - 助詞「は」「が」「を」などの前での分割を優先すべき

### 2.2 タイミング分割の問題

#### 現在の処理フロー（srt_diff_exporter.py）
```python
def _create_entries_from_text(self, text: str, start_time: float, end_time: float, start_index: int):
    # テキストを適切な長さで分割（改行処理込み）
    chunks = self._split_text_into_chunks(text)
    
    # 時間を均等に配分
    chunk_duration = available_duration / len(chunks)
```

**問題点**：
1. **テキストの分割と時間の分割が独立している**
   - 文字数ベースで分割した後、時間を均等配分
   - 実際の発話タイミングを考慮していない

2. **単語レベルのタイムスタンプが活用されていない**
   - WhisperXは単語レベルのタイムスタンプを提供
   - しかし、字幕生成時にこの情報が使われていない

## 3. 解決策の提案

### 3.1 改行位置の改善

#### A. 形態素解析の導入（推奨度：高）
```python
# janomeやMeCabを使用した単語境界の認識
import janome.tokenizer

def get_word_boundaries(text: str) -> list[int]:
    """単語の境界位置を取得"""
    tokenizer = janome.tokenizer.Tokenizer()
    boundaries = []
    pos = 0
    for token in tokenizer.tokenize(text):
        pos += len(token.surface)
        boundaries.append(pos)
    return boundaries
```

#### B. 簡易的な改善（即時実装可能）
```python
# 助詞での優先分割
PARTICLES = set("はがをにでとも")  # 一般的な助詞

def prefer_particle_break(text: str, position: int) -> bool:
    """助詞の前での改行を優先"""
    if position < len(text) and text[position] in PARTICLES:
        return True
    return False
```

### 3.2 タイミング分割の改善

#### A. 単語タイムスタンプの活用（推奨度：高）
```python
def _create_entries_with_word_timing(self, text: str, words: list[dict], start_index: int):
    """単語のタイムスタンプを使用してエントリを作成"""
    entries = []
    current_text = ""
    current_start = None
    
    for word in words:
        # 改行位置のチェック
        if len(current_text + word['word']) > self.max_line_length * self.max_lines:
            if current_text:
                # 現在の単語群でエントリを作成
                entries.append(SRTEntry(
                    index=start_index + len(entries),
                    start_time=current_start,
                    end_time=word['start'],  # 次の単語の開始まで
                    text=self._apply_natural_line_breaks(current_text)
                ))
            current_text = word['word']
            current_start = word['start']
        else:
            current_text += word['word']
            if current_start is None:
                current_start = word['start']
    
    # 最後のエントリ
    if current_text:
        entries.append(SRTEntry(
            index=start_index + len(entries),
            start_time=current_start,
            end_time=words[-1]['end'],
            text=self._apply_natural_line_breaks(current_text)
        ))
    
    return entries
```

#### B. 最小時間制約の適用
```python
# 1文字だけのエントリを防ぐ
MIN_ENTRY_DURATION = 1.0  # 最低1秒
MIN_ENTRY_CHARS = 3  # 最低3文字
```

## 4. 実装優先順位

### 即時対応（Phase 1）- 実装済み
1. **助詞での優先分割**を追加 ✓
2. **最小文字数制約**を追加（3文字以上）✓
3. **単語タイムスタンプの活用** ✓

### Phase 1の実装結果と残存問題
実装後のテストで以下の問題が判明：
- 「木曜日」が依然として「木」と「曜日」で分割される
- 原因：11文字目での改行を探す際、適切な位置が見つからない場合に強制的に11文字目で改行

### 汎用的な解決策（Phase 1.5）
1. **文字種による改行位置の決定**
   ```python
   def is_natural_break_point(text: str, pos: int) -> bool:
       """文字種の変化を利用した自然な改行位置の判定"""
       if pos <= 0 or pos >= len(text):
           return False
       
       prev_char = text[pos - 1]
       curr_char = text[pos]
       
       # ひらがなから漢字への変化
       if is_hiragana(prev_char) and is_kanji(curr_char):
           return True
       
       # 漢字からひらがなへの変化（助詞の可能性）
       if is_kanji(prev_char) and is_hiragana(curr_char):
           # 次の文字が助詞なら改行OK
           if curr_char in PARTICLES:
               return True
       
       return False
   ```

2. **最大文字数を超える場合の処理改善**
   - 現在：強制的に指定位置で改行
   - 改善案：文字数制限を緩和して自然な位置を探す
   ```python
   # 改行位置が見つからない場合、探索範囲を拡大
   if not found:
       # max_lengthを少し超えてでも自然な位置を探す
       extended_search_range = min(10, len(text) - max_length)
       for offset in range(1, extended_search_range + 1):
           pos = max_length + offset
           if is_natural_break_point(text, pos):
               return pos
   ```

### 中期対応（Phase 2）
1. **形態素解析の導入**（最も確実な解決策）
2. **文節単位での分割**

### 長期対応（Phase 3）
1. **読みやすさスコアリング**
2. **機械学習による最適改行位置の予測**

## 5. 実装後の評価と追加課題

### 5.1 形態素解析実装後の結果（2025-06-25）

実装した改善：
- ✅ janome形態素解析の導入
- ✅ 助詞での優先分割
- ✅ 最小文字数制約（3文字以上）
- ✅ 単語タイムスタンプの活用

現在の出力：
```srt
1
00:00:00,000 --> 00:00:02,100
<b>6月
5日の木曜日かな木曜日</b>

2
00:00:02,200 --> 00:00:04,299
<b>はい8時でございます</b>
```

### 5.2 残存問題

#### 問題1: 「6月」と「5日」の不自然な分割
**原因**：
- 形態素解析は「6」「月」「5」「日」と個別に分割
- 11文字目で改行を探す際、「6月」の後（2文字目）が単語境界として検出される
- 数字と単位の組み合わせが一つの意味単位として扱われない

**解決策**：
1. **複合語の認識強化**
   ```python
   # 数字+単位の複合語パターン
   COMPOUND_PATTERNS = [
       re.compile(r'\d+月\d+日'),  # 6月5日
       re.compile(r'\d+年\d+月'),  # 2025年6月
       re.compile(r'\d+時\d+分'),  # 8時30分
   ]
   ```

2. **最小改行単位の設定**
   - 行頭から最低X文字（例：5文字）は改行しない
   - 短すぎる1行目を防ぐ

#### 問題2: 音声とのタイミングずれ
**原因**：
- 無音削除により元の時間範囲が3つに分割
- 単語タイムスタンプが元動画の時間を参照
- TimeMapperでの変換時に精度が低下

**解決策**：
1. **セグメント単位での単語情報保持**
   - 無音削除後の各セグメントに対応する単語情報を保持
   - より正確なタイミング情報の維持

2. **最小エントリ時間の設定**
   - 0.5秒未満のエントリは前後と結合
   - 自然な読み速度の確保

### 5.3 提案する追加改善

#### 汎用的な解決策1: 形態素解析の品詞情報活用
```python
def get_word_boundaries_with_pos(text: str) -> list[tuple[int, str, str]]:
    """形態素解析による単語境界と品詞情報の取得"""
    tokenizer = get_tokenizer()
    if not tokenizer:
        return []
    
    boundaries = []
    pos = 0
    for token in tokenizer.tokenize(text):
        pos += len(token.surface)
        # (境界位置, 表層形, 品詞)
        boundaries.append((pos, token.surface, token.part_of_speech.split(',')[0]))
    return boundaries

def evaluate_break_position(boundaries: list, pos: int) -> float:
    """改行位置の良さをスコア化"""
    score = 1.0
    
    # 境界位置の前後の品詞を確認
    for i, (boundary, surface, pos_tag) in enumerate(boundaries):
        if boundary == pos:
            # 名詞の直後は改行しやすい
            if pos_tag == '名詞':
                score *= 1.5
            # 助詞の前は改行しやすい
            if i + 1 < len(boundaries) and boundaries[i + 1][2] == '助詞':
                score *= 2.0
            # 数詞の後は改行しにくい（次も数詞の可能性）
            if pos_tag == '名詞' and '数' in surface:
                if i + 1 < len(boundaries) and '数' in boundaries[i + 1][1]:
                    score *= 0.1
    
    return score
```

#### 汎用的な解決策2: 文字数制限の柔軟化
- 厳密な11文字制限ではなく、±20%程度の幅を持たせる
- 自然な改行位置が見つかるまで探索範囲を広げる
- ただし、ユーザー設定の最大値は超えない

#### Phase 2b: 無音削除後のタイミング最適化
- 各セグメントの実際の音声内容を考慮
- 発話の自然な区切りでエントリを分割

### 5.4 自然なSRTエントリ分割の設計（2025-06-25追記）

#### 現在の問題
「6月5日の木曜日かな木曜日はい8時でございます」が1つのSRTエントリになっており、4.3秒間表示され続ける。

#### 理想的な分割
意味的に自然な3分割：
1. 「6月5日の木曜日かな」（推測・疑問）- 0.0-1.5秒
2. 「木曜日」（確認・繰り返し）- 1.6-2.5秒  
3. 「はい8時でございます」（時刻の報告）- 2.6-4.3秒

#### 実装方針
**A. 無音位置ベースの分割（現在の無音削除結果を活用）**
```python
# 無音削除により3つのセグメントに分かれた場合
# 各セグメントを独立したSRTエントリとして扱う
segments = [
    (0.0, 1.5, "6月5日の木曜日かな"),
    (1.6, 2.5, "木曜日"),
    (2.6, 4.3, "はい8時でございます")
]
```

**B. 意味的な分割（形態素解析＋ヒューリスティック）**
```python
def split_by_semantic_units(text: str, words_with_timing: list) -> list[tuple[str, float, float]]:
    """意味的な単位で分割"""
    segments = []
    
    # 1. 終助詞（かな、ね、よ等）の後で分割
    # 2. 同じ単語の繰り返しは独立したセグメント
    # 3. 応答詞（はい、ええ、うん等）の前で分割
    
    current_text = ""
    current_start = None
    
    for i, word in enumerate(words_with_timing):
        if should_split_before(word, words_with_timing, i):
            if current_text:
                segments.append((current_text, current_start, word['start']))
            current_text = word['text']
            current_start = word['start']
        else:
            current_text += word['text']
            if current_start is None:
                current_start = word['start']
    
    # 最後のセグメント
    if current_text:
        segments.append((current_text, current_start, words_with_timing[-1]['end']))
    
    return segments

def should_split_before(word: dict, all_words: list, index: int) -> bool:
    """この単語の前で分割すべきか判定"""
    
    # 応答詞の前
    if word['text'] in ['はい', 'ええ', 'うん', 'いいえ']:
        return True
    
    # 前の単語と同じ（繰り返し）
    if index > 0 and word['text'] == all_words[index-1]['text']:
        return True
    
    # 前が終助詞
    if index > 0 and all_words[index-1]['pos'] == '助詞-終助詞':
        return True
    
    return False
```

**C. ハイブリッドアプローチ（推奨）**
1. まず無音位置でセグメント分割
2. 各セグメント内のテキストを確認
3. 必要に応じて意味的な調整を加える

```python
def create_natural_srt_entries(
    text: str,
    time_ranges: list[tuple[float, float]], 
    words_with_timing: list[dict]
) -> list[SRTEntry]:
    """自然なSRTエントリを作成"""
    
    # 無音削除で分割されたセグメント数を確認
    if len(time_ranges) > 1:
        # 複数セグメントの場合、テキストも分割
        text_segments = distribute_text_to_segments(
            text, time_ranges, words_with_timing
        )
        
        entries = []
        for i, (text_seg, (start, end)) in enumerate(zip(text_segments, time_ranges)):
            entries.append(SRTEntry(
                index=i+1,
                start_time=start,
                end_time=end,
                text=apply_line_breaks(text_seg)
            ))
        
        return entries
    else:
        # 単一セグメントの場合、意味的に分割を試みる
        return split_single_segment_semantically(
            text, time_ranges[0], words_with_timing
        )

def distribute_text_to_segments(
    text: str,
    time_ranges: list[tuple[float, float]],
    words_with_timing: list[dict]
) -> list[str]:
    """テキストを時間範囲に基づいて分配"""
    
    segments = []
    for start, end in time_ranges:
        # この時間範囲に含まれる単語を抽出
        words_in_range = [
            w for w in words_with_timing
            if start <= w['start'] <= end or start <= w['end'] <= end
        ]
        
        if words_in_range:
            segment_text = ''.join(w['text'] for w in words_in_range)
            segments.append(segment_text)
        else:
            # 単語タイミングがない場合は文字数で分配（フォールバック）
            segments.append("")
    
    # 空のセグメントがある場合は調整
    if any(not s for s in segments):
        segments = fallback_text_distribution(text, len(time_ranges))
    
    return segments
```

### 5.5 シンプルで高品質な自然分割の実装方針（2025-06-25 最終版）

#### 設計思想：「おまかせ」で良い結果を
ユーザーに複雑な設定を要求せず、内部で賢く処理して高品質な字幕を生成する。

#### 内部処理の改善（ユーザーには見せない）

**1. シンプルな優先順位ベースのアプローチ**
```python
class NaturalSubtitleSplitter:
    """自然な字幕分割を内部で自動処理"""
    
    def __init__(self):
        # 固定の内部パラメータ（ユーザー設定なし）
        self.rules = [
            # 優先度順
            ('silence_match', self.check_silence_boundary),      # 無音位置
            ('end_particle', self.check_end_particle),          # 終助詞
            ('response_word', self.check_response_word),        # 応答詞
            ('repetition', self.check_repetition),              # 繰り返し
            ('balanced_split', self.check_balanced_position)    # バランス
        ]
    
    def split(self, text: str, context: dict) -> list[dict]:
        """最適な分割を自動判定"""
        # 無音位置がある場合は最優先
        if 'silence_ranges' in context and len(context['silence_ranges']) > 1:
            return self.split_by_silence(text, context['silence_ranges'])
        
        # なければ意味的な分割
        return self.split_by_semantics(text, context)
```

**2. 実装の核心部分（内部ロジック）**
```python
def split_by_semantics(self, text: str, context: dict) -> list[dict]:
    """意味的な単位で分割（ユーザーは意識しない）"""
    
    # 形態素解析
    words = self.tokenize(text)
    
    # 優先順位に従って分割位置を決定
    split_positions = []
    
    for word_idx, word in enumerate(words):
        # 「かな」の後は高確率で分割
        if word['surface'] in ['かな', 'ね', 'よ'] and word['pos'] == '助詞-終助詞':
            split_positions.append(word['end_pos'])
        
        # 「はい」の前も分割
        elif word['surface'] in ['はい', 'ええ'] and word_idx > 0:
            split_positions.append(word['start_pos'])
        
        # 同じ単語の繰り返し
        elif word_idx > 0 and word['surface'] == words[word_idx-1]['surface']:
            # ただし短い場合は結合を検討
            if len(word['surface']) >= 3:
                split_positions.append(word['start_pos'])
    
    # 分割実行
    return self.create_segments(text, split_positions, context)
```

**3. 最小限の処理で最大の効果**
```python
def smart_segment_merge(segments: list[dict]) -> list[dict]:
    """短すぎるセグメントを賢く結合"""
    
    merged = []
    buffer = None
    
    for seg in segments:
        # 5文字未満は前後と結合を検討
        if len(seg['text']) < 5:
            if buffer:
                # 前と結合しても22文字以内なら結合
                if len(buffer['text']) + len(seg['text']) <= 22:
                    buffer['text'] += '\n' + seg['text']
                    buffer['end_time'] = seg['end_time']
                    continue
            else:
                buffer = seg
                continue
        
        # バッファがあれば確定
        if buffer:
            merged.append(buffer)
            buffer = None
        
        merged.append(seg)
    
    if buffer:
        merged.append(buffer)
    
    return merged
```

#### 実装の要点

1. **ユーザーが設定するもの**
   - 1行の最大文字数（11文字）
   - 最大行数（2行）
   - 以上。他は全て自動。

2. **内部で自動処理するもの**
   - 無音位置での分割
   - 終助詞・応答詞での分割
   - 短すぎる字幕の結合
   - 文字数バランスの調整

3. **やらないこと**
   - 複雑なパラメータ設定
   - ドメイン選択
   - 学習機能
   - 分割アグレッシブネス調整

#### コード例：実際の使用
```python
# ユーザーコード（main.py）
srt_exporter = SRTDiffExporter(config)
success = srt_exporter.export_from_diff(
    diff=diff_result,
    transcription_result=transcription,
    output_path=output_path,
    srt_settings={
        'max_line_length': 11,  # これだけ
        'max_lines': 2          # これだけ
    }
)

# 内部では賢く処理（ユーザーは知らなくていい）
# - 無音位置を検出して利用
# - 形態素解析で自然な分割
# - 短い字幕を自動結合
# - etc...

## 5.6 フレーム境界とタイミング精度の問題

### 問題
エクスポートしたSRTが1フレームだけ長い場合がある

### 原因の可能性
1. **フレーム境界での丸め処理**
   - SRTのミリ秒精度（3桁）とフレーム境界の不一致
   - 例：30fpsの場合、1フレーム = 33.333...ms
   
2. **浮動小数点の精度問題**
   - Python内部での浮動小数点演算の累積誤差
   
3. **_adjust_to_frame_boundary メソッドの丸めモード**
   - round_mode="floor" vs "round" vs "ceil" の選択

### 対策
- 終了時刻は常に floor（切り捨て）を使用
- 開始時刻は round（四捨五入）を使用
- フレーム単位での検証を追加

## 6. テストケース（更新）

### 6.1 期待される出力（2025-06-25最終版実装前）
```srt
1
00:00:00,000 --> 00:00:02,500
<b>6月5日の木曜日かな
木曜日はい</b>

2
00:00:02,600 --> 00:00:04,299
<b>8時でございます</b>
```

### 6.2 実際の出力（2025-06-25実装後）
```srt
1
00:00:00,000 --> 00:00:03,252
<b>6月5日の木曜日かな
木曜日</b>

2
00:00:03,252 --> 00:00:04,326
<b>はい8時でございます</b>
```

**実装結果の評価**：
- ✅ 無音削除で3つに分割されたセグメントが適切に2つのエントリに結合
- ✅ 「木曜日」（3文字）が前のエントリの2行目に含まれる（13文字≤22文字）
- ✅ 改行位置が自然（「6月5日の木曜日かな」の後）
- ✅ 時間範囲も適切に調整（0.00-3.25秒、3.25-4.33秒）

---

作成日: 2025-06-25  
更新日: 2025-06-25（形態素解析実装後の評価追加）