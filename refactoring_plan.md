# TextffCut リファクタリング実施計画

## 概要
メンテナビリティ向上のための大規模リファクタリングを実施します。
新たなバグを発生させないよう、段階的かつ慎重に進めます。

## 基本方針
1. **既存機能を保護** - すべての変更前に現状の動作を記録
2. **段階的実施** - 小さな変更を積み重ねる
3. **テストファースト** - 変更前にテストを作成
4. **後方互換性** - 既存のインターフェースを維持
5. **ロールバック可能** - 各段階で元に戻せる状態を維持

## Phase 1: 基盤整備（緊急度：高）

### 1-1. マジックナンバーの設定化
**目的**: コード全体に散在する数値定数を一元管理

**変更対象**:
- メモリ閾値（70%, 75%, 80%, 85%, 90%）
- バッチサイズ（1, 2, 4, 8, 16, 32）
- チャンクサイズ（180, 300, 600秒など）

**テスト方法**:
1. 既存の動作を記録
2. 定数置換後、同じ動作を確認
3. 境界値テスト

### 1-2. worker_transcribe.pyのクラス化

**現状の問題**:
- main関数が400行以上
- 複数の責任が混在
- テストが困難

**新設計**:
```python
# worker_transcribe.py
class TranscriptionWorker:
    """ワーカープロセスのメインクラス"""
    
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.optimizer = None
        self.memory_monitor = None
        
    def execute(self) -> None:
        """メイン実行"""
        handler = self._create_task_handler()
        handler.process()

# タスク別ハンドラー
class BaseTaskHandler(ABC):
    @abstractmethod
    def process(self) -> TranscriptionResult:
        pass

class TranscribeOnlyHandler(BaseTaskHandler):
    """文字起こしのみ"""
    
class SeparatedModeHandler(BaseTaskHandler):
    """分離モード（文字起こし→アライメント）"""
    
class FullProcessHandler(BaseTaskHandler):
    """フル処理"""
```

**移行戦略**:
1. 新クラスを作成（既存コードと並行）
2. 既存のmain関数から新クラスを呼び出す
3. 動作確認後、古いコードを削除

## Phase 2: アーキテクチャ改善（緊急度：中）

### 2-1. サービス層の導入

**目的**: UIとビジネスロジックの分離

**新アーキテクチャ**:
```
┌─────────────┐
│   UI層      │ (main.py - Streamlit部分のみ)
├─────────────┤
│ サービス層   │ (新規作成)
├─────────────┤
│  コア層     │ (既存のcore/*)
└─────────────┘
```

**新規作成ファイル**:
- `services/transcription_service.py`
- `services/video_processing_service.py`
- `services/alignment_service.py`

### 2-2. アライメント診断の独立

**現状**: worker_transcribe.pyに100行以上の診断ロジック

**新設計**:
```python
# core/alignment_diagnostics.py
class AlignmentDiagnostics:
    def run(self, audio_path: str, segments: List) -> DiagnosticResult:
        """診断を実行"""
        
    def calculate_optimal_batch_size(self, result: DiagnosticResult) -> int:
        """診断結果から最適なバッチサイズを計算"""
```

## Phase 3: 品質向上（緊急度：低）

### 3-1. エラーハンドリングの統一
- 共通エラーハンドラークラスの作成
- エラーメッセージの標準化

### 3-2. 型ヒントの強化
- すべての関数に型ヒントを追加
- mypy導入の検討

## テスト戦略

### 単体テスト
```python
# tests/test_worker_refactored.py
class TestTranscriptionWorker:
    def test_config_loading(self):
        """設定読み込みのテスト"""
    
    def test_task_handler_selection(self):
        """タスクハンドラー選択のテスト"""
    
    def test_memory_thresholds(self):
        """メモリ閾値の動作テスト"""
```

### 統合テスト
```python
# tests/test_integration_refactored.py
class TestRefactoredIntegration:
    def test_full_transcription_flow(self):
        """文字起こし全体フローのテスト"""
    
    def test_separated_mode_flow(self):
        """分離モードのテスト"""
```

### リグレッションテスト
1. 現在の動作を記録
2. リファクタリング後に同じ入力で同じ出力を確認

## 実施スケジュール

### Week 1: Phase 1
- Day 1-2: マジックナンバーの設定化
- Day 3-4: worker_transcribe.pyの設計
- Day 5-7: 実装とテスト

### Week 2: Phase 2
- Day 1-3: サービス層の実装
- Day 4-5: アライメント診断の分離
- Day 6-7: 統合テスト

### Week 3: Phase 3 & 仕上げ
- Day 1-2: エラーハンドリング統一
- Day 3-4: 型ヒント強化
- Day 5-7: 最終テストとドキュメント

## リスク管理

### 主なリスク
1. **既存機能の破壊**
   - 対策: 包括的なテストスイート
   
2. **パフォーマンス劣化**
   - 対策: ベンチマークテスト
   
3. **後方互換性の喪失**
   - 対策: 段階的移行

### ロールバック計画
- 各Phaseごとにタグを作成
- 問題発生時は前のタグに戻す

## 成功基準
1. すべての既存テストがパス
2. 新規テストカバレッジ80%以上
3. パフォーマンス劣化なし
4. コード行数の削減（重複除去により）

## 次のステップ
1. この計画のレビューと承認
2. refactoring/phase1ブランチの作成
3. Phase 1-1の実施開始