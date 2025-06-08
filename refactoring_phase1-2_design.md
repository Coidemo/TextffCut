# Phase 1-2: worker_transcribe.pyのクラス化設計書

## 現状分析

### 問題点
1. **main関数が430行** - 単一の関数に多くの責任が集中
2. **責任の混在**:
   - 設定ファイルの読み込み
   - メモリ監視の初期化
   - タスクタイプによる分岐処理（3つのモード）
   - アライメント診断の実行
   - エラーハンドリング
   - プロファイル保存
3. **テストが困難** - 巨大な関数で単体テストが書きにくい
4. **再利用性が低い** - 個別の処理を他から呼び出せない

## 新しい設計

### クラス構造
```
TranscriptionWorker（メインクラス）
├── ConfigLoader（設定管理）
├── MemoryManager（メモリ監視管理）
└── TaskHandlers（タスク処理）
    ├── BaseTaskHandler（抽象基底クラス）
    ├── TranscribeOnlyHandler（文字起こしのみ）
    ├── SeparatedModeHandler（分離モード）
    └── FullProcessHandler（フル処理）
```

### 詳細設計

#### 1. TranscriptionWorker（メインクラス）
```python
class TranscriptionWorker:
    """ワーカープロセスのメインクラス"""
    
    def __init__(self, config_path: str):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス
        """
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.load()
        self.memory_manager = MemoryManager(self.config.model_size)
        
    def execute(self) -> None:
        """メイン実行メソッド"""
        try:
            # 初期メモリ使用量を記録
            self.memory_manager.log_initial_memory()
            
            # タスクハンドラーを取得して実行
            handler = self._create_task_handler()
            result = handler.process()
            
            # 結果を保存
            self._save_result(result)
            
            # 成功時の後処理
            self._handle_success(result)
            
        except MemoryError as e:
            self._handle_memory_error(e)
        except Exception as e:
            self._handle_general_error(e)
    
    def _create_task_handler(self) -> BaseTaskHandler:
        """タスクタイプに応じたハンドラーを作成"""
        task_type = self.config.task_type
        
        handlers = {
            'transcribe_only': TranscribeOnlyHandler,
            'separated_mode': SeparatedModeHandler,
            'full': FullProcessHandler
        }
        
        handler_class = handlers.get(task_type, FullProcessHandler)
        return handler_class(
            self.config,
            self.memory_manager.optimizer,
            self.memory_manager.monitor
        )
```

#### 2. ConfigLoader（設定管理）
```python
class ConfigLoader:
    """設定ファイルの読み込みと検証"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        
    def load(self) -> WorkerConfig:
        """設定を読み込み、検証して返す"""
        self._validate_path()
        config_data = self._read_json()
        return self._build_config(config_data)
    
    def _validate_path(self) -> None:
        """パスの存在確認"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"設定ファイルが見つかりません: {self.config_path}")
```

#### 3. MemoryManager（メモリ監視管理）
```python
class MemoryManager:
    """メモリ監視と最適化の管理"""
    
    def __init__(self, model_size: str):
        self.optimizer = AutoOptimizer(model_size)
        self.monitor = MemoryMonitor()
        self.optimizer.reset_diagnostic_mode()
        
    def log_initial_memory(self) -> None:
        """初期メモリ使用量を記録"""
        try:
            import psutil
            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"初期メモリ使用量: {mem_mb:.1f}MB")
        except Exception:
            logger.debug("メモリ情報取得をスキップ")
    
    def get_optimal_params(self) -> Dict:
        """現在のメモリ状況から最適なパラメータを取得"""
        current_memory = self.monitor.get_memory_usage()
        return self.optimizer.get_optimal_params(current_memory)
```

#### 4. BaseTaskHandler（抽象基底クラス）
```python
from abc import ABC, abstractmethod

class BaseTaskHandler(ABC):
    """タスクハンドラーの基底クラス"""
    
    def __init__(self, config: WorkerConfig, optimizer: AutoOptimizer, 
                 memory_monitor: MemoryMonitor):
        self.config = config
        self.optimizer = optimizer
        self.memory_monitor = memory_monitor
        self.progress_callback = self._create_progress_callback()
        
    @abstractmethod
    def process(self) -> TranscriptionResult:
        """タスクを処理（サブクラスで実装）"""
        pass
    
    def _create_progress_callback(self):
        """進捗報告用コールバックを作成"""
        def callback(progress: float, message: str):
            logger.info(f"進捗: {progress:.1%} - {message}")
            send_progress(progress, message)
        return callback
```

#### 5. 具体的なタスクハンドラー

##### TranscribeOnlyHandler
```python
class TranscribeOnlyHandler(BaseTaskHandler):
    """文字起こしのみのハンドラー"""
    
    def process(self) -> TranscriptionResult:
        logger.info("文字起こしのみモード（アライメントなし）")
        
        transcriber = self._create_transcriber()
        
        result = transcriber.transcribe(
            video_path=self.config.video_path,
            model_size=self.config.model_size,
            progress_callback=self.progress_callback,
            use_cache=False,
            save_cache=False,
            skip_alignment=True
        )
        
        logger.info("文字起こしのみ完了（アライメント処理は別途実行）")
        return result
```

##### SeparatedModeHandler
```python
class SeparatedModeHandler(BaseTaskHandler):
    """分離モード（文字起こし→アライメント）のハンドラー"""
    
    def process(self) -> TranscriptionResult:
        logger.info("分離モード: 文字起こしフェーズ開始")
        
        # ステップ1: 文字起こし
        transcription_result = self._process_transcription()
        
        # ステップ2: アライメント
        aligned_result = self._process_alignment(transcription_result)
        
        return aligned_result
    
    def _process_transcription(self) -> TranscriptionResult:
        """文字起こしフェーズ"""
        # 実装...
        
    def _process_alignment(self, result: TranscriptionResult) -> TranscriptionResult:
        """アライメントフェーズ"""
        # アライメント診断の実行を含む
        # 実装...
```

## 移行戦略

### Phase A: 並行実装（既存コードを保持）
1. 新しいクラス構造を`worker_transcribe_v2.py`として実装
2. 既存の`main()`関数から新クラスを呼び出すラッパーを作成
3. 動作確認

### Phase B: 統合
1. テストが完全にパスすることを確認
2. `worker_transcribe.py`の`main()`を新クラスを使うように変更
3. 古い実装をコメントアウト

### Phase C: クリーンアップ
1. 古い実装を削除
2. ファイル名を整理

## テスト計画

### 単体テスト
- ConfigLoader: 設定ファイルの読み込みテスト
- MemoryManager: メモリ監視のテスト
- 各TaskHandler: 個別のタスク処理テスト

### 統合テスト
- 全タスクタイプでの動作確認
- エラーハンドリングの確認
- メモリ管理の確認

## リスクと対策

### リスク1: 既存の動作を破壊
**対策**: 並行実装により、既存コードを保持しながら開発

### リスク2: パフォーマンス劣化
**対策**: 各フェーズでベンチマークを実施

### リスク3: 複雑性の増加
**対策**: シンプルで明確な責任分離を維持

## 期待される効果

1. **保守性の向上**: 各クラスが単一の責任を持つ
2. **テスタビリティ**: 各部分を独立してテスト可能
3. **拡張性**: 新しいタスクタイプの追加が容易
4. **可読性**: コードの意図が明確に

## 次のステップ

1. この設計のレビューと承認
2. worker_transcribe_v2.pyの実装開始
3. 各クラスの単体テスト作成