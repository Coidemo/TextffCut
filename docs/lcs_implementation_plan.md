# LCSベース文字処理システム実装計画

## 実装方針

既存システムを動かしながら、段階的に新しいLCSベースのシステムに移行します。

## ディレクトリ構造

```
domain/
├── use_cases/
│   ├── text_difference_detector.py      # 既存（現在の実装）
│   ├── text_difference_detector_lcs.py  # 新規（LCS実装）
│   └── time_range_calculator_lcs.py    # 新規（文字レベル時間計算）
├── entities/
│   └── character_timestamp.py           # 新規（文字タイムスタンプ）
└── value_objects/
    └── lcs_match.py                     # 新規（LCSマッチ情報）

adapters/
└── gateways/
    └── text_processing/
        ├── simple_text_processor_gateway.py  # 既存
        └── lcs_text_processor_gateway.py     # 新規

infrastructure/
└── containers/
    └── container.py  # フィーチャーフラグ追加
```

## 詳細実装タスク

### Day 1: 基盤データ構造とLCSコア実装

#### 1-1. データ構造の実装（2時間）
```python
# domain/entities/character_timestamp.py
@dataclass
class CharacterWithTimestamp:
    char: str
    start: float
    end: float
    segment_id: str
    word_index: int
    original_position: int

# domain/value_objects/lcs_match.py
@dataclass
class LCSMatch:
    original_index: int
    edited_index: int
    char: str
    timestamp: CharacterWithTimestamp

@dataclass
class DifferenceBlock:
    type: DifferenceType
    text: str
    start_time: float
    end_time: float
    char_positions: list[CharacterWithTimestamp]
```

#### 1-2. 文字配列構築機能（2時間）
```python
# domain/use_cases/character_array_builder.py
class CharacterArrayBuilder:
    def build_from_segments(self, segments: list[dict]) -> tuple[list[CharacterWithTimestamp], str]:
        """セグメントのwords配列から文字配列を構築"""
        pass
    
    def validate_reconstruction(self, full_text: str, original_text: str) -> bool:
        """再構築されたテキストの妥当性を検証"""
        pass
```

#### 1-3. LCS差分検出実装（3時間）
```python
# domain/use_cases/text_difference_detector_lcs.py
class TextDifferenceDetectorLCS:
    def detect_differences(self, original_text: str, edited_text: str, 
                         transcription_result: TranscriptionResult) -> TextDifference:
        """LCSベースの差分検出"""
        pass
    
    def _compute_lcs_dp_table(self, text1: str, text2: str) -> list[list[int]]:
        """動的計画法でLCSテーブルを構築"""
        pass
    
    def _backtrack_matches(self, dp_table: list[list[int]], 
                          text1: str, text2: str) -> list[tuple[int, int]]:
        """バックトラックでマッチ位置を取得"""
        pass
```

#### 1-4. 単体テスト作成（1時間）
```python
# tests/unit/domain/use_cases/test_text_difference_detector_lcs.py
- 基本的なLCS動作テスト
- フィラーを含むテキストのテスト
- 空文字列、同一文字列のエッジケース
```

### Day 2: グループ化と時間計算

#### 2-1. 差分グループ化実装（3時間）
```python
# domain/use_cases/difference_grouper.py
class DifferenceGrouper:
    def group_lcs_matches(self, matches: list[LCSMatch]) -> list[list[LCSMatch]]:
        """連続したマッチをグループ化"""
        pass
    
    def create_difference_blocks(self, groups: list[list[LCSMatch]], 
                               original_chars: list[CharacterWithTimestamp]) -> list[DifferenceBlock]:
        """グループから差分ブロックを作成"""
        pass
```

#### 2-2. 削除部分特定（2時間）
```python
# domain/use_cases/deletion_identifier.py
class DeletionIdentifier:
    def identify_deletions(self, original_chars: list[CharacterWithTimestamp],
                         lcs_matches: list[LCSMatch]) -> list[DifferenceBlock]:
        """削除された部分を特定"""
        pass
```

#### 2-3. 時間範囲計算（2時間）
```python
# domain/use_cases/time_range_calculator_lcs.py
class TimeRangeCalculatorLCS:
    def calculate_from_blocks(self, blocks: list[DifferenceBlock]) -> list[TimeRange]:
        """差分ブロックから時間範囲を計算"""
        pass
    
    def merge_adjacent_ranges(self, ranges: list[TimeRange], 
                            gap_threshold: float = 0.1) -> list[TimeRange]:
        """近接した範囲をマージ"""
        pass
```

#### 2-4. 統合テスト作成（1時間）
```python
# tests/integration/test_lcs_text_processing.py
- 実際のWhisperX出力を使ったテスト
- エンドツーエンドの処理フロー確認
```

### Day 3: ゲートウェイ統合とUI連携

#### 3-1. LCSゲートウェイ実装（3時間）
```python
# adapters/gateways/text_processing/lcs_text_processor_gateway.py
class LCSTextProcessorGateway(TextProcessingGateway):
    def find_differences(self, transcription_result: TranscriptionResult, 
                        edited_text: str) -> TextDifference:
        """LCSベースの差分検出を提供"""
        pass
    
    def get_highlight_data(self, transcription_result: TranscriptionResult,
                          edited_text: str) -> list[dict]:
        """UI用のハイライトデータを生成"""
        pass
```

#### 3-2. UI表示データ生成（2時間）
```python
# domain/use_cases/ui_data_generator.py
class UIDataGenerator:
    def generate_highlights(self, original_text: str, 
                          blocks: list[DifferenceBlock]) -> list[dict]:
        """ハイライト表示用データ生成"""
        pass
    
    def generate_deletion_summary(self, deletion_blocks: list[DifferenceBlock]) -> dict:
        """削除確認モーダル用データ生成"""
        pass
```

#### 3-3. フィーチャーフラグ実装（2時間）
```python
# infrastructure/containers/container.py
def get_text_processor_gateway():
    if settings.USE_LCS_TEXT_PROCESSOR:
        return LCSTextProcessorGateway()
    else:
        return SimpleTextProcessorGateway()
```

#### 3-4. UI統合（1時間）
```python
# ui/components.py
- ハイライト表示の実装
- 削除モーダルの追加
```

### Day 4: エクスポート連携と移行準備

#### 4-1. エクスポート連携（2時間）
```python
# domain/use_cases/export_time_range_extractor.py
class ExportTimeRangeExtractor:
    def extract_from_blocks(self, blocks: list[DifferenceBlock]) -> list[TimeRange]:
        """エクスポート用の時間範囲を抽出"""
        pass
```

#### 4-2. 既存システムとの互換性確保（2時間）
```python
# adapters/compatibility/lcs_compatibility_adapter.py
class LCSCompatibilityAdapter:
    def convert_to_legacy_format(self, lcs_result: TextDifference) -> dict:
        """旧形式への変換"""
        pass
    
    def convert_from_legacy_format(self, legacy_result: dict) -> TextDifference:
        """新形式への変換"""
        pass
```

#### 4-3. 移行スクリプト（2時間）
```python
# scripts/migrate_to_lcs.py
- 既存のキャッシュをLCS形式に変換
- 設定ファイルの更新
```

#### 4-4. E2Eテスト（2時間）
```python
# tests/e2e/test_lcs_full_workflow.py
- 文字起こし → 編集 → エクスポートの全フロー
- 新旧システムの結果比較
```

### Day 5: 最適化と仕上げ

#### 5-1. パフォーマンス最適化（3時間）
- 大規模テキスト用の分割処理実装
- メモリ効率的なLCS実装（Hirschberg法の検討）
- キャッシュ戦略の実装

#### 5-2. エラーハンドリング強化（2時間）
- wordsフィールドがない場合のフォールバック
- 文字エンコーディングの問題への対処
- タイムスタンプ不整合の検出と修正

#### 5-3. ドキュメント更新（2時間）
- README.mdへの新機能追加
- API仕様書の更新
- 移行ガイドの作成

#### 5-4. 最終テストと品質確認（1時間）
- 全テストスイートの実行
- パフォーマンステスト
- メモリリークチェック

## 実装の優先順位

1. **必須機能**（Day 1-2）
   - LCSコア実装
   - 文字配列構築
   - 基本的な差分検出

2. **統合機能**（Day 3-4）
   - ゲートウェイ実装
   - UI連携
   - エクスポート対応

3. **品質向上**（Day 5）
   - 最適化
   - エラー処理
   - ドキュメント

## リスクと対策

1. **パフォーマンス問題**
   - リスク：大規模テキストで処理が遅い
   - 対策：分割処理、キャッシュ、最適化アルゴリズム

2. **互換性問題**
   - リスク：既存機能が動作しなくなる
   - 対策：フィーチャーフラグ、段階的移行

3. **品質問題**
   - リスク：新しいバグの混入
   - 対策：充実したテスト、段階的リリース

## 成功指標

1. **機能面**
   - フィラーを含むテキストで95%以上の正確性
   - ミリ秒単位の時間精度

2. **性能面**
   - 30,000文字を5秒以内で処理
   - メモリ使用量50MB以下

3. **品質面**
   - テストカバレッジ90%以上
   - エラー率0.1%以下