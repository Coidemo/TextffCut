# テキスト処理関連 詳細設計仕様書 - 文脈マーカー処理の更新

## 更新日: 2025-07-12

## 1. 変更の概要

文脈マーカー `{}` の処理において、位置計算の複雑さによるバグを解消するため、新しい処理フローを採用します。

### 1.1 実装結果

本設計に基づく実装が完了し、以下が確認されました：

- ✅ 「いなこと言うと」の断片化問題が解決
- ✅ 文脈マーカーの内容が正しく除外される
- ✅ エッジケース（ネスト、特殊文字、境界等）に対応
- ✅ 処理性能は要求範囲内（100セグメントで5秒以内）

### 1.2 最終的な実装方針

当初検討したタイムスタンプ取得の最適化（差分検出直後の取得）については、以下の理由により**現在の分離構造を維持**することに決定：

1. **責任の明確化**: 差分検出（`find_differences`）と時間取得（`get_time_ranges`）は異なる関心事
2. **テスト容易性**: 各機能を独立してテスト可能
3. **柔軟性**: 差分のみ必要なケースに対応
4. **パフォーマンス**: ミリ秒単位の差で実用上問題なし

## 2. 新しい処理フロー

### 2.1 全体の流れ

```
1. 文脈マーカーの位置を記録（元のテキストの位置）
2. テキストを正規化（スペース削除）しながら位置を追跡
3. 文脈マーカーを一時的に削除（差分検出のため）
4. SequenceMatcherで差分検出
5. 差分検出結果から即座にタイムスタンプを取得
6. 文脈マーカー位置を復元して、その部分を除外
7. 境界調整を適用
```

### 2.2 各ステップの詳細

#### ステップ1: 文脈マーカーの位置を記録

```python
def extract_context_markers(self, text: str) -> List[dict]:
    """文脈マーカー {} を抽出して位置情報を返す"""
    markers = []
    for match in re.finditer(r'\{([^}]+)\}', text):
        markers.append({
            'content': match.group(1),
            'full_match': match.group(0),
            'start': match.start(),
            'end': match.end()
        })
    return markers
```

**例:**
- 入力: `"あいうえお{かきく}けこさしすせそ"`
- 出力: `[{'content': 'かきく', 'full_match': '{かきく}', 'start': 5, 'end': 10}]`

#### ステップ2: 正規化と位置追跡

```python
def normalize_with_position_tracking(self, text: str, markers: List[dict]) -> Tuple[str, List[dict], List[int]]:
    """テキストを正規化しながら位置を追跡"""
    normalized = ""
    pos_map = []  # 元の位置 → 正規化後の位置のマッピング
    
    for i, char in enumerate(text):
        if char not in ' 　\n\r':  # スペース・改行以外
            pos_map.append(len(normalized))
            normalized += char
        else:
            pos_map.append(len(normalized))  # スペースは次の文字と同じ位置
    
    # マーカー位置を更新
    updated_markers = []
    for marker in markers:
        new_start = pos_map[marker['start']]
        new_end = pos_map[marker['end']]
        
        updated_markers.append({
            'content': self.normalize_for_comparison(marker['content']),
            'full_match': marker['full_match'],
            'start': new_start,
            'end': new_end,
            'original_start': marker['start'],
            'original_end': marker['end']
        })
    
    return normalized, updated_markers, pos_map
```

**例:**
- 入力: `"あい うえお{かきく}けこ さしすせそ"` (スペースあり)
- 出力: 
  - 正規化テキスト: `"あいうえお{かきく}けこさしすせそ"`
  - 更新されたマーカー: `[{'content': 'かきく', 'start': 5, 'end': 10}]`

#### ステップ3: 文脈マーカーの一時削除

```python
# 文脈マーカーを削除（{}とその中身を削除）
comparison_text = normalized_edited
marker_ranges_in_normalized = []

# 逆順で処理して位置のずれを防ぐ
for marker in sorted(context_markers_normalized, key=lambda m: m['start'], reverse=True):
    comparison_text = (
        comparison_text[:marker['start']] + 
        comparison_text[marker['end']:]
    )
    marker_ranges_in_normalized.append((marker['start'], marker['end']))
```

**例:**
- 入力: `"あいうえお{かきく}けこさしすせそ"`
- 出力: `"あいうえおけこさしすせそ"`

#### ステップ4: 差分検出

```python
matcher = SequenceMatcher(None, original_text, comparison_text)
opcodes = list(matcher.get_opcodes())
```

#### ステップ5: タイムスタンプの即時取得

差分検出の結果（opcodes）が得られたら、その位置情報を使って即座にタイムスタンプを取得します。

```python
for tag, i1, i2, j1, j2 in opcodes:
    if tag == 'equal':
        # 元のテキストの位置 i1-i2 から直接タイムスタンプを取得
        timestamps = self.get_timestamps_for_range(transcription_result, i1, i2)
```

この時点でタイムスタンプを取得することで、後の位置復元の複雑さを回避できます。

#### ステップ6: 文脈マーカー位置の復元と除外

```python
# 削除された文字数による位置調整を計算
position_adjustments = []
cumulative_adjustment = 0
for start, end in sorted(marker_ranges_in_normalized):
    position_adjustments.append({
        'position': start - cumulative_adjustment,
        'adjustment': cumulative_adjustment,
        'deleted_length': end - start
    })
    cumulative_adjustment += (end - start)

# 位置調整を適用
adjusted_j1 = j1
adjusted_j2 = j2
for adj in position_adjustments:
    if j1 >= adj['position']:
        adjusted_j1 += adj['adjustment']
    if j2 >= adj['position']:
        adjusted_j2 += adj['adjustment']
```

その後、文脈マーカーと重なる部分を除外します。

#### ステップ7: 境界調整の適用

最後に、境界調整マーカー `[<0.1]`、`[0.1>]` などを適用します。

## 3. 重要な変更点

### 3.1 位置計算の簡素化

- 以前: 文脈マーカー削除 → 位置復元の複雑な計算 → 断片化バグ
- 新規: 位置記録 → 正規化 → {}のみ削除（中身は残す） → 差分検出 → シンプルな位置計算

### 3.2 実装の簡素化

- 文脈マーカーの{}のみを削除し、中身は残すアプローチにより、位置計算が大幅に簡素化
- 複雑な位置復元ロジックが不要になり、バグの原因を根本的に解消

### 3.3 バグの解消

位置計算の複雑さによる「いなこと言うと」のような断片化バグが解消されます。

## 4. 実装時の注意点

1. **位置のインデックス**: 1ベースではなく0ベースで統一
2. **正規化の一貫性**: スペース・改行の除去ルールを統一
3. **マーカーの順序**: 削除時は必ず逆順で処理
4. **境界ケース**: 文脈マーカーが重なる場合の処理を考慮

## 5. テストケース

### 5.1 基本的なケース

```python
# ケース1: 単一の文脈マーカー
original = "あいうえおかきくけこさしすせそ"
edited = "あいうえお{かきく}けこさしすせそ"
# 期待結果: "かきく"部分が除外され、"あいうえお"と"けこさしすせそ"が抽出される

# ケース2: 複数の文脈マーカー
original = "あいうえおかきくけこさしすせそ"
edited = "{あいうえお}かきく{けこ}さしすせそ"
# 期待結果: "かきく"と"さしすせそ"が抽出される

# ケース3: スペースを含むテキスト
original = "あいうえおかきくけこさしすせそ"
edited = "あい うえお{かきく}けこ さしすせそ"
# 期待結果: スペースが正規化され、正しく処理される
```

### 5.2 エッジケース

```python
# ケース4: 文脈マーカーが隣接
edited = "{あいうえお}{かきく}けこさしすせそ"

# ケース5: 文脈マーカー内にスペース
edited = "あいうえお{か き く}けこさしすせそ"

# ケース6: 境界調整と文脈マーカーの組み合わせ
edited = "あいうえお[<0.1]{かきく}[0.1>]けこさしすせそ"
```

## 6. 関連ファイルの更新

### 6.1 実装ファイル
- `adapters/gateways/text_processing/sequence_matcher_gateway.py`: 主要な実装（完了）

### 6.2 テストファイル
- `tests/unit/adapters/gateways/test_sequence_matcher_context_markers.py`: 基本的なユニットテスト（7個、全て成功）
- `tests/unit/adapters/gateways/test_sequence_matcher_edge_cases.py`: エッジケーステスト（8個、全て成功）
- `tests/integration/test_context_marker_integration.py`: 統合テスト（4個、全て成功）

### 6.3 ドキュメント
- `docs/text_processing_detailed_design_update.md`: 本ドキュメント（更新完了）
- `docs/implementation_plan_context_marker.md`: 実装計画（完了）
- `docs/verification_plan_context_marker.md`: 検証計画（完了）