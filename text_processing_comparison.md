# テキスト処理ロジックの新旧比較レポート

## 概要
このドキュメントでは、TextffCutプロジェクトにおける旧テキスト処理実装（`core/text_processor.py`）と新しいリファクタリング実装（`domain/use_cases/`配下）の主な違いを分析します。

## 1. PAD設定とその影響

### 旧実装 (core/text_processor.py)
- PAD設定は直接テキスト処理には関与していない
- PADは`VideoProcessor`の`_calculate_keep_segments`メソッドで適用される
- 無音削除時のセグメント境界に対してのみ適用（テキスト差分検出とは独立）

### 新実装 (domain/use_cases/)
- 同様にPAD設定はテキスト処理には直接関与しない
- VideoProcessorGatewayを通じて同じPADロジックが適用される

**影響**: PAD設定の差分はテキスト処理精度には影響しない。両実装とも、PADは動画セグメントの境界調整にのみ使用される。

## 2. テキスト正規化の違い

### 旧実装 (TextProcessor.normalize_text)
```python
def normalize_text(text: str, preserve_newlines: bool = False) -> str:
    # 全角スペースを半角に変換
    text = text.replace("　", " ")
    
    if preserve_newlines:
        # 改行を保持する場合の処理
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        lines = text.split("\n")
        # 各行内の連続する空白を1つに
        normalized_lines = []
        for line in lines:
            line = re.sub(r"[ \t]+", " ", line.strip())
            normalized_lines.append(line)
        # 空行を除去して結合
        text = "\n".join(line for line in normalized_lines if line)
    else:
        # 連続する空白（改行含む）を1つのスペースに
        text = re.sub(r"\s+", " ", text)
    
    return text.strip()
```

### 新実装 (SimpleTextProcessorGateway.find_differences)
```python
if not skip_normalization:
    # 改行を統一
    normalized_original = original_text.replace('\r\n', '\n').replace('\r', '\n')
    normalized_edited = edited_text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 連続する改行を1つに
    normalized_original = re.sub(r'\n+', '\n', normalized_original)
    normalized_edited = re.sub(r'\n+', '\n', normalized_edited)
    
    # 前後の空白を削除
    normalized_original = normalized_original.strip()
    normalized_edited = normalized_edited.strip()
```

**主な違い**:
1. 旧実装は全角スペースを半角に変換するが、新実装はこの処理を行わない
2. 旧実装は連続する空白を1つのスペースに統一するが、新実装は改行のみを統一
3. 旧実装は`preserve_newlines`オプションがあるが、新実装は常に改行を保持

## 3. セグメント境界処理

### 旧実装
- `find_differences_with_separator`メソッドで区切り文字付きテキストを処理
- 各セクションを独立して検索し、結果をマージ
- `merge_time_ranges`で近い範囲を結合（デフォルトgap_threshold=1.0秒）

### 新実装
- `find_differences_with_separator`でセパレータで分割後、セクションを結合して処理
- セパレータを除外した連続テキストとして差分検出

**重要な違い**: 旧実装は各セクションを独立処理するが、新実装は結合して一括処理

## 4. 差分検出アルゴリズムの違い

### 旧実装
1. `difflib.SequenceMatcher`を使用
2. 空白を除去したテキストで差分を計算
3. 元のテキストの位置に変換して返す
4. 抜粋テキスト（元の50%未満）の特別処理あり

### 新実装
1. カスタムアルゴリズム（最長共通部分文字列アプローチ）
2. 編集テキストが元のテキストに完全に含まれるかを最初にチェック
3. 部分一致を段階的に検索（長い部分から短い部分へ）
4. 抜粋の特別処理なし（すべて同じアルゴリズムで処理）

**精度への影響**:
- 新実装はより単純で直感的なアプローチ
- 完全一致を優先するため、部分的な変更の検出精度が低下する可能性
- 空白処理の違いにより、スペースを含むテキストで結果が異なる可能性

## 5. その他の論理的差異

### 文脈指定パターン
- 旧実装: `parse_context_pattern`で`{前文脈}ターゲット{後文脈}`形式をサポート
- 新実装: この機能は実装されていない

### 境界調整マーカー
- 旧実装: `[<数値]`、`[数値>]`形式のマーカーで境界調整をサポート
- 新実装: 簡易的な実装のみ（完全な機能は未実装）

### エラーハンドリング
- 旧実装: 詳細なエラーメッセージと位置情報を提供
- 新実装: シンプルなログ出力のみ

## 推奨事項

1. **正規化の統一**: 全角半角変換とスペース処理を両実装で統一すべき
2. **アルゴリズムの改善**: 新実装の差分検出アルゴリズムを改良し、部分的な変更も正確に検出できるようにする
3. **機能の完全性**: 文脈指定パターンや境界調整マーカーなど、旧実装の高度な機能を新実装に移植
4. **テストカバレッジ**: 両実装の動作差異を網羅するテストケースを追加

## 結論

主な差異は以下の3点：
1. テキスト正規化処理（特に空白処理）
2. セパレータ付きテキストの処理方法
3. 差分検出アルゴリズムの実装

これらの違いが、特定のケースでテキスト差分検出の精度に影響を与える可能性があります。