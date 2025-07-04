# テキスト処理関連 詳細設計仕様書

## 1. 概要

本文書は、TextffCutのテキスト処理に関わる全ての関数・メソッドについて、その入出力と処理内容を詳細に定義します。

## 2. データ構造定義

### 2.1 ドメインエンティティ

#### TranscriptionResult
```python
class TranscriptionResult:
    """文字起こし結果（ドメインエンティティ）"""
    segments: list[TranscriptionSegment]  # セグメントのリスト
    text: str                             # 全文テキスト
    language: str                         # 言語コード
    duration: float                       # 総時間（秒）
```

#### TranscriptionSegment
```python
class TranscriptionSegment:
    """文字起こしセグメント（ドメインエンティティ）"""
    start: float                          # 開始時間（秒）
    end: float                            # 終了時間（秒）
    text: str                             # セグメントのテキスト
    words: list[WordInfo] | None          # 単語情報
    chars: list[CharInfo] | None          # 文字情報
```

#### WordInfo
```python
class WordInfo:
    """単語情報（ドメインエンティティ）"""
    word: str                             # 単語
    start: float                          # 開始時間（秒）
    end: float                            # 終了時間（秒）
    confidence: float                     # 信頼度（0.0-1.0）
```

### 2.2 レガシー形式（coreパッケージ）

#### LegacyTranscriptionResult
```python
class TranscriptionResult:  # core.transcription
    """レガシー文字起こし結果"""
    segments: list[TranscriptionSegment]  # レガシーセグメント
    text: str                             # 全文テキスト
    language: str                         # 言語コード
```

#### LegacyTranscriptionSegment
```python
class TranscriptionSegment:  # core.transcription
    """レガシー文字起こしセグメント"""
    start: float                          # 開始時間
    end: float                            # 終了時間
    text: str                             # テキスト
    words: list[dict] | None              # 単語辞書のリスト
    chars: list[dict] | None              # 文字辞書のリスト
```

#### レガシー単語辞書形式
```python
{
    "word": str,        # 単語
    "start": float,     # 開始時間
    "end": float,       # 終了時間
    "confidence": float # 信頼度
}
```

## 3. Gateway層の詳細仕様

### 3.1 TextProcessorGatewayAdapter

#### find_differences メソッド
```python
def find_differences(
    self,
    original_text: str,
    edited_text: str
) -> TextDifference:
```

**入力:**
- `original_text`: 元のテキスト（文字列）
- `edited_text`: 編集後のテキスト（文字列）

**出力:**
- `TextDifference`: 差分情報（ドメインエンティティ）

**処理内容:**
1. レガシーのTextProcessorを使用して差分を検出
2. レガシー形式の差分結果をドメインエンティティに変換
3. 変換時に以下を行う：
   - 共通部分・追加部分・削除部分を分類
   - 各部分の位置情報を保持
   - DifferenceType列挙型で分類

#### get_time_ranges メソッド
```python
def get_time_ranges(
    self,
    diff_result: TextDifference,
    transcription_result: TranscriptionResult
) -> list[TimeRange]:
```

**入力:**
- `diff_result`: 差分情報（ドメインエンティティ）
- `transcription_result`: 文字起こし結果（ドメインエンティティ）

**出力:**
- `list[TimeRange]`: 時間範囲のリスト

**処理内容:**
1. 差分情報から共通部分を抽出
2. 文字起こし結果のセグメントから対応する時間範囲を特定
3. 以下の変換を行う：
   - ドメインエンティティの差分情報をレガシー形式に変換
   - ドメインエンティティの文字起こし結果をレガシー形式に変換
   - レガシーのget_time_rangesを呼び出し
   - 結果をドメインエンティティの時間範囲に変換

**重要な注意点:**
- `transcription_result.segments`は`TranscriptionSegment`オブジェクトのリスト
- レガシー形式に変換する際、segmentsは辞書形式ではなくオブジェクト形式

### 3.2 変換処理の詳細

#### _convert_to_legacy_segments メソッド
```python
def _convert_to_legacy_segments(
    self,
    segments: list[TranscriptionSegment]
) -> list[LegacyTranscriptionSegment]:
```

**入力:**
- `segments`: ドメインエンティティのセグメントリスト

**出力:**
- レガシー形式のセグメントリスト

**処理内容:**
1. 各セグメントについて以下を実行：
   - `start`, `end`, `text`をそのままコピー
   - `words`がある場合、WordInfoオブジェクトを辞書形式に変換
   - `chars`がある場合、CharInfoオブジェクトを辞書形式に変換
2. LegacyTranscriptionSegmentオブジェクトを作成
3. words/charsは辞書のリストとして設定

#### domain_to_legacy_dict メソッド（問題の箇所）
```python
def domain_to_legacy_dict(
    self,
    transcription_result: TranscriptionResult
) -> dict:
```

**入力:**
- `transcription_result`: ドメインエンティティの文字起こし結果

**出力:**
- レガシー形式の辞書

**処理内容:**
1. segmentsを変換（ここが問題）
   - 現状：`seg_dict["start"]`のように辞書としてアクセスしている
   - 正しい：`segment.start`のようにオブジェクトとしてアクセスすべき
2. 各セグメントについて：
   - 基本情報（start, end, text）を辞書に変換
   - wordsがある場合、WordInfoリストを辞書リストに変換
   - charsがある場合、CharInfoリストを辞書リストに変換

**修正が必要な理由:**
- 入力の`transcription_result.segments`は`TranscriptionSegment`オブジェクトのリスト
- 現在の実装は辞書として扱っているためAttributeError

## 4. Presenter層の詳細仕様

### 4.1 TextEditorPresenter

#### initialize メソッド
```python
def initialize(
    self,
    transcription_result: TranscriptionResult
) -> None:
```

**入力:**
- `transcription_result`: 文字起こし結果（ドメインエンティティまたはアダプター）

**処理内容:**
1. TranscriptionResultAdapterの場合、内部のドメインエンティティを取得
2. ViewModelに設定
3. 全文テキストを取得して設定
4. セッション状態から編集済みテキストがあれば復元

#### update_edited_text メソッド
```python
def update_edited_text(
    self,
    text: str
) -> None:
```

**入力:**
- `text`: 編集されたテキスト

**処理内容:**
1. ViewModelを更新
2. テキストが空でなければ_process_edited_textを呼び出し
3. 空の場合は関連情報をリセット

#### _process_edited_text メソッド
```python
def _process_edited_text(self) -> None:
```

**入力:**
- なし（ViewModelから取得）

**処理内容:**
1. 境界調整マーカーの存在をチェック
2. マーカーがあれば除去
3. 区切り文字を検出
4. 区切り文字がある場合：
   - セクション分割モードで処理
   - find_differences_with_separatorを使用
5. 区切り文字がない場合：
   - 単一セクションモードで処理
   - find_differencesを使用
6. 差分結果から時間範囲を更新

### 4.2 TranscriptionPresenter

#### load_selected_cache メソッド
```python
def load_selected_cache(self) -> bool:
```

**処理内容:**
1. LoadCacheRequestを作成
2. LoadTranscriptionCacheUseCaseを実行
3. 結果（ドメインエンティティ）をTranscriptionResultAdapterでラップ
4. ViewModelとSessionManagerに保存

**重要:**
- SessionManagerにはドメインエンティティを保存（アダプターではない）
- ViewModelにはアダプターを設定

## 5. 問題の根本原因と解決策

### 5.1 現在の問題

1. **型の不一致**
   - ドメインエンティティはオブジェクト形式
   - レガシーコードは一部で辞書形式を期待
   - 変換処理で混乱が生じている

2. **変換の重複**
   - 同じ変換を複数箇所で行っている
   - 変換ロジックが統一されていない

3. **エラーハンドリング不足**
   - 型チェックが不十分
   - 変換失敗時の処理が不明確

### 5.2 解決策

1. **統一的な変換メソッドの実装**
   - ドメイン→レガシー変換を一箇所に集約
   - レガシー→ドメイン変換を一箇所に集約

2. **型安全性の向上**
   - 入力の型チェックを強化
   - 変換前後の検証を追加

3. **テストの充実**
   - 各変換パターンのユニットテスト
   - 境界値テスト
   - エラーケーステスト

## 6. 実装優先順位

1. **最優先: domain_to_legacy_dictの修正**
   - セグメントを正しくオブジェクトとして扱う
   - words/charsの変換を適切に行う

2. **高優先: 変換ロジックの統一**
   - TextProcessorConverterクラスの実装
   - 全ての変換をこのクラスに集約

3. **中優先: エラーハンドリング**
   - 型チェックの追加
   - 適切なエラーメッセージ

4. **低優先: テストの追加**
   - ユニットテスト
   - 統合テスト