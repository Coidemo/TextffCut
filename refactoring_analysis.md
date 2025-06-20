# TextffCut リファクタリング分析レポート

## 概要

TextffCutプロジェクトのメンテナビリティ向上のため、コード分析を実施しました。特に最近の変更（診断フェーズ、アライメント最適化）に関連する箇所を中心に、リファクタリングが必要な箇所を特定しました。

## 主要ファイル分析

### 1. worker_transcribe.py (430行)

#### 問題点
- **main()関数が400行以上**と非常に長い
- **責任の分離が不明確**: 文字起こし、アライメント、診断、エラーハンドリングが1つの関数に混在
- **重複したロジック**: アライメント処理が複数箇所に分散
- **深いネスト**: 最大5レベルのネストで可読性が低い

#### 複雑性が高い箇所
- `main()` 関数（33-431行）- 複雑度が非常に高い
- 診断フェーズの処理（178-226行）
- アライメント処理の分岐（141-286行）

#### 改善提案
```python
# リファクタリング例
class TranscriptionWorker:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.optimizer = None
        self.memory_monitor = None
    
    def run(self):
        """メイン処理"""
        try:
            self._initialize_components()
            result = self._process_transcription()
            self._save_result(result)
        except MemoryError as e:
            self._handle_memory_error(e)
        except Exception as e:
            self._handle_general_error(e)
    
    def _process_transcription(self):
        """文字起こし処理の実行"""
        if self.config.task_type == 'transcribe_only':
            return self._process_transcribe_only()
        elif self.config.task_type == 'separated_mode':
            return self._process_separated_mode()
        else:
            return self._process_full_mode()
```

### 2. core/alignment_processor.py (687行)

#### 問題点
- **巨大な診断メソッド**: `run_diagnostic()` が200行以上
- **重複コード**: メモリ計測ロジックが複数箇所に存在
- **マジックナンバー**: ハードコードされた数値が多数
- **エラーハンドリングの一貫性不足**

#### 複雑性が高い箇所
- `run_diagnostic()` メソッド（61-258行）
- `_process_batch()` メソッド（528-545行）
- `_post_process_alignment()` メソッド（547-564行）

#### 改善提案
```python
class AlignmentDiagnostic:
    """診断処理を専門に扱うクラス"""
    def __init__(self, memory_monitor):
        self.memory_monitor = memory_monitor
        self.diagnostic_result = DiagnosticResult()
    
    def run(self, audio_path: str, language: str, 
            sample_segments: List[TranscriptionSegmentV2]) -> DiagnosticResult:
        """診断を実行"""
        self._measure_model_memory()
        self._measure_audio_memory(audio_path)
        self._test_batch_processing(sample_segments)
        return self.diagnostic_result

class AlignmentProcessor:
    def __init__(self, config: Config, batch_size: Optional[int] = None):
        self.config = config
        self.diagnostic = AlignmentDiagnostic(MemoryMonitor())
        # ...
```

### 3. core/auto_optimizer.py (453行)

#### 問題点
- **巨大な設定辞書**: MODEL_PROFILESが読みにくい
- **複雑な条件分岐**: `_adjust_parameters()` が非常に複雑
- **状態管理の複雑さ**: 診断モードと通常モードの切り替えロジック

#### 複雑性が高い箇所
- `_adjust_parameters()` メソッド（222-295行）
- `_handle_diagnostic_phase()` メソッド（297-354行）
- `_predict_optimal_params()` メソッド（356-398行）

#### 改善提案
```python
@dataclass
class ModelProfile:
    """モデルプロファイルのデータクラス"""
    base_memory_gb: float
    initial_chunk_seconds: int
    initial_align_chunk_seconds: int
    initial_max_workers: int
    initial_batch_size: int

class AdjustmentStrategy(ABC):
    """パラメータ調整戦略の基底クラス"""
    @abstractmethod
    def adjust(self, current_params: Dict) -> Dict:
        pass

class EmergencyDecreaseStrategy(AdjustmentStrategy):
    """緊急時のパラメータ削減戦略"""
    def adjust(self, current_params: Dict) -> Dict:
        return {
            'chunk_seconds': int(current_params['chunk_seconds'] * 0.5),
            'max_workers': max(1, current_params['max_workers'] - 2),
            'batch_size': max(1, int(current_params['batch_size'] * 0.25))
        }
```

### 4. core/transcription_smart_boundary.py (384行)

#### 問題点
- **責任の混在**: 境界検出と文字起こし処理が同一クラス
- **一時ファイル管理の散在**: 複数箇所で同様の処理
- **エラーハンドリングの重複**

#### 改善提案
```python
class BoundaryDetector:
    """境界検出専用クラス"""
    def __init__(self, config):
        self.config = config
        self.silence_detector = SilenceDetector()
    
    def find_boundaries(self, video_path: str, duration: float) -> List[float]:
        """最適な分割境界を検出"""
        ideal_points = self._calculate_ideal_points(duration)
        return self._find_silence_boundaries(video_path, ideal_points)

class SmartBoundaryTranscriber(Transcriber):
    def __init__(self, config, optimizer=None, memory_monitor=None):
        super().__init__(config)
        self.boundary_detector = BoundaryDetector(config)
        self.segment_processor = SegmentProcessor(config)
```

### 5. main.py (1177行)

#### 問題点
- **巨大なmain関数**: 1000行以上の単一関数
- **UI定義とビジネスロジックの混在**
- **重複したStreamlit設定**

#### 改善提案
```python
class TextffCutApp:
    """メインアプリケーションクラス"""
    def __init__(self):
        self.config = Config()
        self.setup_page()
        self.initialize_state()
    
    def run(self):
        """アプリケーションのメインループ"""
        self.show_header()
        self.show_sidebar()
        self.process_workflow()
```

## 共通の問題点

### 1. エラーハンドリングの一貫性不足
```python
# 現状: 各所でバラバラなエラーハンドリング
try:
    # 処理
except Exception as e:
    logger.error(f"エラー: {e}")
    # 時には再スロー、時にはデフォルト値返却

# 改善案: 統一的なエラーハンドラー
class ErrorHandler:
    @staticmethod
    def handle_transcription_error(e: Exception, context: Dict) -> None:
        """文字起こしエラーの統一処理"""
        logger.error(f"Transcription error in {context}: {e}")
        if isinstance(e, MemoryError):
            raise TranscriptionMemoryError(str(e))
        elif isinstance(e, AlignmentError):
            raise TranscriptionAlignmentError(str(e))
```

### 2. 設定値のハードコーディング
```python
# 現状: マジックナンバーが散在
if memory_percent > 85:
    batch_size = 4

# 改善案: 設定クラスに集約
@dataclass
class MemoryThresholds:
    CRITICAL: float = 90.0
    HIGH: float = 85.0
    MEDIUM: float = 75.0
    LOW: float = 60.0
```

### 3. ログ出力の不統一
```python
# 改善案: 構造化ログ
class StructuredLogger:
    def log_transcription_start(self, video_path: str, model_size: str):
        self.logger.info("Transcription started", extra={
            'event': 'transcription_start',
            'video_path': video_path,
            'model_size': model_size,
            'timestamp': datetime.now().isoformat()
        })
```

## 優先度別改善提案

### 高優先度
1. **worker_transcribe.py のmain関数を分割**
   - TranscriptionWorkerクラスの作成
   - タスクタイプ別の処理メソッド分離
   - エラーハンドリングの統一

2. **AlignmentProcessorの診断処理を別クラスに分離**
   - AlignmentDiagnosticクラスの作成
   - メモリ計測ロジックの共通化

3. **設定値の一元管理**
   - すべてのマジックナンバーをconfigに移動
   - 環境別設定の明確化

### 中優先度
1. **AutoOptimizerのリファクタリング**
   - 調整戦略のStrategy Pattern化
   - プロファイル管理の改善

2. **エラーハンドリングフレームワークの構築**
   - 統一的なエラーハンドラー
   - カスタム例外クラスの整理

### 低優先度
1. **UI/ビジネスロジックの分離（main.py）**
   - MVCパターンの適用
   - Streamlit依存部分の抽象化

2. **ユニットテストの追加**
   - 各コンポーネントの単体テスト
   - モックを使用した統合テスト

## メトリクス

- **総LOC**: 20,777行（Pythonファイルのみ）
- **最大ファイル**: main.py (1,177行)
- **平均複雑度**: 高（特にworker_transcribe.py、alignment_processor.py）
- **重複コード**: エラーハンドリング、メモリ計測、ファイル操作で顕著

## 結論

TextffCutプロジェクトは機能的には充実していますが、メンテナビリティの観点から改善の余地があります。特に最近追加された診断フェーズとアライメント最適化のコードは、既存のコードに追加される形で実装されており、責任の分離が不明確になっています。

優先的に取り組むべきは：
1. 巨大な関数の分割（特にworker_transcribe.py）
2. 診断処理の独立したモジュール化
3. 設定値の一元管理

これらの改善により、コードの可読性、テスタビリティ、保守性が大幅に向上することが期待されます。