# Phase 2-3: アライメント診断の独立クラス化計画

## 現状分析

### 診断機能の場所
1. **worker_align.py (84-144行目)**
   - アライメント用の診断フェーズ実装
   - メモリ使用量測定とバッチサイズ最適化
   - モデルサイズに基づく推定

2. **auto_optimizer.py (302-403行目)**
   - 診断フェーズの処理 (`_handle_diagnostic_phase`)
   - メモリ増加率の計算
   - 最適パラメータの予測 (`_predict_optimal_params`)

### 問題点
- 診断ロジックが2箇所に分散
- worker_align.pyには簡易的な診断のみ
- auto_optimizer.pyには汎用的な診断機能
- 重複したロジックとメモリ測定

## 実装計画

### 1. AlignmentDiagnostics クラスの設計

```python
class AlignmentDiagnostics:
    """アライメント処理専用の診断クラス"""
    
    def __init__(self, model_size: str, config: Config):
        self.model_size = model_size
        self.config = config
        self.memory_monitor = MemoryMonitor()
        
    def run_diagnostics(self, segments: List[Segment], language: str) -> DiagnosticResult:
        """診断フェーズを実行"""
        pass
        
    def estimate_optimal_batch_size(self, available_memory_gb: float, segment_count: int) -> int:
        """利用可能メモリとセグメント数から最適なバッチサイズを推定"""
        pass
        
    def measure_model_memory_usage(self, language: str) -> float:
        """アライメントモデルのメモリ使用量を測定"""
        pass
```

### 2. DiagnosticResult データクラス

```python
@dataclass
class DiagnosticResult:
    """診断結果"""
    optimal_batch_size: int
    model_memory_usage_mb: float
    base_memory_percent: float
    estimated_memory_per_batch: float
    recommendations: List[str]
    warnings: List[str]
```

### 3. 移行ステップ

#### Step 1: AlignmentDiagnosticsクラスの作成
- core/alignment_diagnostics.py を新規作成
- 診断ロジックを統合

#### Step 2: worker_align.pyの簡略化
- 診断ロジックをAlignmentDiagnosticsに委譲
- シンプルな呼び出しに変更

#### Step 3: auto_optimizer.pyとの連携
- アライメント専用の診断は分離
- 汎用的な診断機能は維持

### 4. テスト計画

1. **単体テスト**
   - AlignmentDiagnosticsの各メソッド
   - メモリ測定の精度
   - バッチサイズ推定の妥当性

2. **統合テスト**
   - worker_align.pyからの呼び出し
   - 実際のアライメント処理での動作
   - メモリ使用量の予測精度

### 5. 期待される効果

- **保守性向上**: 診断ロジックの一元化
- **テスタビリティ向上**: 独立したテストが可能
- **拡張性**: 新しい診断機能の追加が容易
- **再利用性**: 他の処理でも診断機能を活用可能

## 実装順序

1. DiagnosticResultデータクラスの作成
2. AlignmentDiagnosticsクラスの実装
3. worker_align.pyのリファクタリング
4. テストの作成と実行
5. ドキュメントの更新