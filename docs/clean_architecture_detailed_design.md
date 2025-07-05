# TextffCut クリーンアーキテクチャ詳細設計書（簡素化版）

## 1. Infrastructure層 詳細設計

### 1.1 Gateway Adapters

#### 1.1.1 バランスの取れた設計パターン

レガシー依存を戦略的に活用する3つのパターン：

**パターンA: 完全新規実装**
```python
class FileGatewayAdapter(IFileGateway):
    def __init__(self):
        # シンプルなファイル操作は新規実装
        pass
    
    def read(self, path: FilePath) -> bytes:
        return Path(str(path)).read_bytes()
```

**パターンB: 既存コードの薄いラッパー**
```python
class FFmpegGatewayAdapter(IVideoGateway):
    def __init__(self, config: Config):
        # 複雑で実績のあるFFmpeg操作をラップ
        from core.video import VideoProcessor
        self.processor = VideoProcessor(config)
    
    def extract_audio(self, video: FilePath) -> AudioPath:
        # シンプルな委譲
        result = self.processor.extract_audio(str(video))
        return AudioPath(result)
```

**パターンC: 部分的な既存活用**
```python
class SilenceDetectionGateway(ISilenceDetectionGateway):
    def __init__(self, config: Config):
        # 無音検出アルゴリズムのみ既存活用
        from core.video import VideoProcessor
        self.processor = VideoProcessor(config)
    
    def detect_silence(self, audio_path: FilePath) -> List[TimeRange]:
        # 実績のあるアルゴリズムを活用
        return self.processor.detect_silence_from_wav(str(audio_path))
```

**戦略**: 実装の複雑性と実績を基準に判断

#### 1.1.2 新規実装のGateway（シンプル）

```python
class FileGatewayAdapter(IFileGateway):
    """完全新規実装でシンプル"""
    def __init__(self):
        pass
    
    def exists(self, path: FilePath) -> bool:
        return Path(str(path)).exists()
    
    def read(self, path: FilePath) -> bytes:
        return Path(str(path)).read_bytes()
    
    def write(self, path: FilePath, content: bytes) -> None:
        Path(str(path)).write_bytes(content)

class TextProcessorGateway(ITextProcessorGateway):
    """テキスト処理は既存活用を検討"""
    def __init__(self, config: Config):
        # 既存のtext_processor.pyには細かいノウハウがある
        from core.text_processor import TextProcessor
        self.processor = TextProcessor(config)
    
    def find_differences(self, original: str, edited: str) -> List[TextDifference]:
        # 既存の差分検出ロジックを活用
        return self.processor.find_differences(original, edited)

class SRTExportGateway(ISRTExportGateway):
    """SRTエクスポートは新規実装（シンプルなため）"""
    def export_srt(self, subtitles: List[Subtitle], output_path: FilePath) -> None:
        # シンプルなテキスト形式なので新規実装
        with open(str(output_path), 'w', encoding='utf-8') as f:
            for i, subtitle in enumerate(subtitles, 1):
                f.write(f"{i}\n")
                f.write(f"{subtitle.start_time} --> {subtitle.end_time}\n")
                f.write(f"{subtitle.text}\n\n")
```

#### 1.1.3 既存活用のGateway（最小限）

```python
class WhisperXGateway(ITranscriptionGateway):
    """WhisperXのみ既存コード活用"""
    def __init__(self, config: Config):
        # 既存のWhisperX連携部分のみ使用
        from core.transcription import Transcriber
        self.transcriber = Transcriber(config)
    
    def transcribe(self, audio_path: FilePath) -> TranscriptionResult:
        # 最小限の委譲
        legacy_result = self.transcriber.transcribe(str(audio_path))
        # シンプルな変換（必要最小限）
        return TranscriptionResult(
            segments=[self._convert_segment(s) for s in legacy_result['segments']],
            language=legacy_result['language']
        )

class FFmpegGateway(IVideoGateway):
    """FFmpegのみ既存コード活用"""
    def __init__(self, config: Config):
        # 既存のFFmpeg操作部分のみ使用
        from core.video import VideoProcessor
        self.processor = VideoProcessor(config)
    
    def extract_audio(self, video_path: FilePath) -> FilePath:
        # 最小限の委譲
        result = self.processor.extract_audio(str(video_path))
        return FilePath(result)
```

### 1.2 バランスの取れたDI Container設定

#### 1.2.1 GatewayContainer（実用版）
```python
class GatewayContainer(containers.DeclarativeContainer):
    # 設定
    config = providers.Configuration()
    
    # 新規実装のゲートウェイ（設定不要）
    file_gateway = providers.Singleton(
        FileGatewayAdapter
    )
    
    srt_export_gateway = providers.Singleton(
        SRTExportGateway
    )
    
    # 既存活用のゲートウェイ（設定必要）
    text_processor_gateway = providers.Singleton(
        TextProcessorGateway,
        config=config
    )
    
    whisperx_gateway = providers.Singleton(
        WhisperXGateway,
        config=config
    )
    
    ffmpeg_gateway = providers.Singleton(
        FFmpegGateway,
        config=config
    )
    
    silence_detection_gateway = providers.Singleton(
        SilenceDetectionGateway,
        config=config
    )
    
    fcpxml_export_gateway = providers.Singleton(
        FCPXMLExportGateway,
        config=config
    )
    
    edl_export_gateway = providers.Singleton(
        EDLExportGateway,
        config=config
    )
```

## 2. Domain層 詳細設計

### 2.1 Entity設計（簡素化版）

#### 2.1.1 TranscriptionResult
```python
@dataclass
class TranscriptionResult:
    """レガシー形式を考慮しないクリーンな設計"""
    id: str
    language: str
    segments: List[TranscriptionSegment]
    original_audio_path: str
    model_size: str
    processing_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def text(self) -> str:
        """全セグメントのテキストを結合"""
        return " ".join(seg.text for seg in self.segments)
    
    @property
    def duration(self) -> float:
        """全体の継続時間"""
        return max(seg.end for seg in self.segments) if self.segments else 0.0
    
    # レガシー変換メソッドは削除（不要な複雑性）
```

### 2.2 Value Object設計

#### 2.2.1 TimeRange
```python
@dataclass(frozen=True)
class TimeRange:
    start: float
    end: float
    
    def __post_init__(self):
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be after start time")
    
    @property
    def duration(self) -> float:
        return self.end - self.start
    
    def overlaps(self, other: 'TimeRange') -> bool:
        return self.start < other.end and other.start < self.end
```

## 3. Application層（Use Cases）詳細設計

### 3.1 Use Case インターフェース

#### 3.1.1 基本パターン
```python
@dataclass
class UseCaseRequest:
    """ユースケースリクエストの基底クラス"""
    pass

@dataclass
class UseCaseResponse:
    """ユースケースレスポンスの基底クラス"""
    success: bool
    error_message: Optional[str] = None

class UseCase(ABC, Generic[TRequest, TResponse]):
    @abstractmethod
    def execute(self, request: TRequest) -> TResponse:
        pass
```

### 3.2 具体的なUse Case実装

#### 3.2.1 TranscribeVideoUseCase
```python
@dataclass
class TranscribeVideoRequest(UseCaseRequest):
    video_path: FilePath
    model_size: str
    language: str
    progress_callback: Optional[Callable[[str], None]] = None

@dataclass
class TranscribeVideoResponse(UseCaseResponse):
    result: Optional[TranscriptionResult] = None

class TranscribeVideoUseCase(UseCase[TranscribeVideoRequest, TranscribeVideoResponse]):
    def __init__(self, transcription_gateway: ITranscriptionGateway):
        self.transcription_gateway = transcription_gateway
    
    def execute(self, request: TranscribeVideoRequest) -> TranscribeVideoResponse:
        try:
            result = self.transcription_gateway.transcribe(
                request.video_path,
                request.model_size,
                request.language,
                request.progress_callback
            )
            return TranscribeVideoResponse(success=True, result=result)
        except Exception as e:
            return TranscribeVideoResponse(success=False, error_message=str(e))
```

## 4. Presentation層 詳細設計

### 4.1 MVP パターン実装

#### 4.1.1 ViewModel基底クラス
```python
@dataclass
class BaseViewModel(ABC):
    _observers: List[ViewModelObserver] = field(default_factory=list, init=False)
    _is_dirty: bool = field(default=False, init=False)
    
    def subscribe(self, observer: ViewModelObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)
    
    def notify(self) -> None:
        self._is_dirty = True
        for observer in self._observers:
            observer.update(self)
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def validate(self) -> Optional[str]:
        """検証エラーがある場合はエラーメッセージを返す"""
        pass
```

#### 4.1.2 Presenter基底クラス
```python
class BasePresenter(ABC, Generic[T]):
    def __init__(self, view_model: T):
        self.view_model = view_model
    
    @abstractmethod
    def initialize(self) -> None:
        """初期化処理"""
        pass
    
    @abstractmethod
    def handle_error(self, error: Exception, context: str) -> None:
        """エラーハンドリング"""
        pass
```

#### 4.1.3 View基底クラス
```python
class BaseView(ABC, Generic[T]):
    def __init__(self, view_model: T):
        self.view_model = view_model
        self.view_model.subscribe(self)
    
    @abstractmethod
    def render(self) -> None:
        """UIをレンダリング"""
        pass
    
    def update(self, view_model: BaseViewModel) -> None:
        """ViewModelの変更通知を受け取る"""
        # Streamlitは自動的に再描画されるため、通常は空実装
        pass
```

### 4.2 簡素化されたMVP実装例

#### 4.2.1 TranscriptionのMVP（シンプル版）
```python
# ViewModel（シンプルなデータ構造）
@dataclass
class TranscriptionViewModel(BaseViewModel):
    video_path: Optional[Path] = None
    transcription_result: Optional[TranscriptionResult] = None
    is_processing: bool = False
    progress: float = 0.0
    error_message: Optional[str] = None

# Presenter（簡素化されたロジック）
class TranscriptionPresenter(BasePresenter[TranscriptionViewModel]):
    def __init__(self, view_model: TranscriptionViewModel,
                 transcribe_use_case: TranscribeVideoUseCase):
        super().__init__(view_model)
        self.transcribe_use_case = transcribe_use_case
    
    def start_transcription(self) -> bool:
        """文字起こしを開始"""
        self.view_model.is_processing = True
        
        request = TranscribeVideoRequest(
            video_path=FilePath(str(self.view_model.video_path))
        )
        
        response = self.transcribe_use_case.execute(request)
        
        if response.success:
            # 直接結果を保存（変換不要）
            self.view_model.transcription_result = response.result
            self.view_model.is_processing = False
            return True
        else:
            self.view_model.error_message = response.error_message
            self.view_model.is_processing = False
            return False

# View（シンプルなUI）
class TranscriptionView(BaseView[TranscriptionViewModel]):
    def render(self) -> None:
        st.subheader("📝 文字起こし")
        
        # 実行ボタン
        if st.button("文字起こし開始"):
            self.presenter.start_transcription()
        
        # 結果表示
        if self.view_model.transcription_result:
            st.text_area("結果", self.view_model.transcription_result.text)
        
        # エラー表示
        if self.view_model.error_message:
            st.error(self.view_model.error_message)
```

## 5. 改善されたSessionManager設計

### 5.1 責務と設計方針
- Streamlitのセッション状態の型安全なラッパー
- セッションキーの一元管理
- テスト可能な設計
- レガシー互換は考慮しない

### 5.2 セッションキーの定義
```python
@dataclass(frozen=True)
class SessionKeys:
    """セッションキーの一元管理（型安全）"""
    TRANSCRIPTION_RESULT = 'transcription_result'
    EDITED_TEXT = 'edited_text'
    VIDEO_PATH = 'video_path'
    TIME_RANGES = 'time_ranges'
    ADJUSTED_TIME_RANGES = 'adjusted_time_ranges'
    EXPORT_SETTINGS = 'export_settings'
    SILENCE_THRESHOLD = 'silence_threshold'
    MIN_SILENCE_DURATION = 'min_silence_duration'
```

### 5.3 SessionManagerの実装
```python
class SessionManager:
    """型安全で保守的なセッション状態管理"""
    
    def __init__(self, session_keys: SessionKeys = SessionKeys()):
        self.keys = session_keys
        self._session = None
    
    @property
    def session(self):
        """遅延評価でst.session_stateを取得"""
        if self._session is None:
            import streamlit as st
            self._session = st.session_state
        return self._session
    
    # ドメインモデル専用の型安全なメソッド
    def get_transcription_result(self) -> Optional[TranscriptionResult]:
        return self.session.get(self.keys.TRANSCRIPTION_RESULT)
    
    def set_transcription_result(self, result: TranscriptionResult) -> None:
        self.session[self.keys.TRANSCRIPTION_RESULT] = result
    
    def get_edited_text(self) -> Optional[str]:
        return self.session.get(self.keys.EDITED_TEXT)
    
    def set_edited_text(self, text: str) -> None:
        self.session[self.keys.EDITED_TEXT] = text
    
    def get_time_ranges(self) -> Optional[List[TimeRange]]:
        return self.session.get(self.keys.TIME_RANGES)
    
    def set_time_ranges(self, ranges: List[TimeRange]) -> None:
        self.session[self.keys.TIME_RANGES] = ranges
    
    def clear_all(self) -> None:
        """すべてのデータをクリア"""
        for key in list(self.session.keys()):
            del self.session[key]
```

### 5.3 設計のポイント
- 汎用的なget/setメソッドは提供しない（型安全性のため）
- ドメインモデルを直接扱う（変換不要）
- シンプルで理解しやすい

## 6. エラーハンドリング詳細

### 6.1 ErrorHandler設計
```python
class ErrorHandler:
    def handle_error(self, error: Exception, context: str) -> str:
        """
        エラーを処理してユーザーフレンドリーなメッセージを返す
        
        Args:
            error: 発生したエラー
            context: エラーのコンテキスト（例: "文字起こし処理"）
            
        Returns:
            ユーザー向けエラーメッセージ
        """
        # エラーをログ
        logger.error(f"{context}でエラーが発生: {error}", exc_info=True)
        
        # エラータイプに応じてメッセージを生成
        if isinstance(error, FileNotFoundError):
            return "ファイルが見つかりません"
        elif isinstance(error, PermissionError):
            return "ファイルへのアクセス権限がありません"
        # ... 他のエラータイプ
        else:
            return f"{context}でエラーが発生しました"
```

### 6.2 Gateway層でのエラー変換パターン

#### 6.2.1 統一的なエラー変換
```python
class GatewayErrorTransformer:
    """外部システムのエラーをドメインエラーに変換"""
    
    @staticmethod
    def transform(error: Exception, operation: str) -> DomainError:
        """
        外部エラーをドメインエラーに変換
        
        Args:
            error: 外部システムのエラー
            operation: 実行中の操作
            
        Returns:
            ドメイン層で理解できるエラー
        """
        if isinstance(error, ConnectionError):
            return NetworkError(f"{operation}中にネットワークエラーが発生しました")
        elif isinstance(error, TimeoutError):
            return TimeoutError(f"{operation}がタイムアウトしました")
        elif "permission" in str(error).lower():
            return PermissionError(f"{operation}に必要な権限がありません")
        else:
            return UnknownError(f"{operation}中に予期しないエラーが発生しました")
```

#### 6.2.2 Gateway Adapterでの使用例
```python
class VideoProcessorGatewayAdapter:
    def extract_audio(self, video_path: FilePath) -> AudioPath:
        try:
            # レガシーコードを呼び出し
            result = self.legacy_processor.extract_audio(str(video_path))
            return AudioPath(result)
        except Exception as e:
            # 統一的なエラー変換
            domain_error = GatewayErrorTransformer.transform(
                e, "音声抽出"
            )
            raise domain_error
```

## 7. DIコンテナの詳細設計

### 7.1 コンテナ間の連携パターン

#### 7.1.1 親子コンテナの関係
```python
class ApplicationContainer(containers.DeclarativeContainer):
    """ルートコンテナ"""
    
    # 設定
    config = providers.Singleton(DIConfig)
    
    # 子コンテナをprovidersとして定義
    gateways = providers.Container(
        GatewayContainer,
        config=providers.DependenciesContainer(
            legacy_config=legacy_config
        )
    )
    
    use_cases = providers.Container(
        UseCaseContainer,
        gateways=gateways
    )
    
    presentation = providers.Container(
        PresentationContainer,
        gateways=gateways,
        use_cases=use_cases,
        services=services
    )
```

#### 7.1.2 コンテナの取得方法
```python
# 正しい方法：親コンテナから子コンテナのインスタンスを取得
app_container = bootstrap_di()
presentation_container = app_container.presentation()

# 間違った方法：別々にインスタンス化してoverride
# presentation_container = PresentationContainer()
# presentation_container.gateways.override(app_container.gateways)  # エラー
```

### 7.2 MVP起動手順

#### 7.2.1 main_mvp.pyの正しい実装
```python
def main() -> None:
    """MVPアプリケーションのエントリーポイント"""
    try:
        # 1. アプリケーションコンテナを初期化
        app_container = bootstrap_di()
        
        # 2. Presentationコンテナを取得（既に依存関係が注入済み）
        presentation_container = app_container.presentation()
        
        # 3. 必要なPresenterとViewを取得
        main_presenter = presentation_container.main_presenter()
        sidebar_presenter = presentation_container.sidebar_presenter()
        
        # 4. 初期化とレンダリング
        sidebar_presenter.initialize()
        main_presenter.initialize()
        
        # 5. UIを表示
        sidebar_view = SidebarView(sidebar_presenter)
        show_main_view(main_presenter, sidebar_view)
        
    except Exception as e:
        logger.error(f"アプリケーションエラー: {e}", exc_info=True)
        st.error(f"エラーが発生しました: {str(e)}")
```

### 7.3 Gateway Adapterの統一設計

#### 7.3.1 設定が必要なGateway Adapter
以下のアダプターは必ずconfigを受け取る：
- VideoProcessorGatewayAdapter
- TranscriptionGatewayAdapter  
- VideoExportGatewayAdapter
- FCPXMLExportGatewayAdapter
- EDLExportGatewayAdapter
- SRTExportGatewayAdapter

#### 7.3.2 設定が不要なGateway Adapter
以下のアダプターは設定を必要としない：
- FileGatewayAdapter（ファイルシステムアクセスのみ）
- TextProcessorGatewayAdapter（ステートレスな処理のみ）

## 8. 移行時の注意点

### 8.1 レガシーコードとの統合
1. **アダプターパターン**: レガシーコードは必ずGateway Adapterでラップ
2. **設定の注入**: DIコンテナから設定を注入（内部生成禁止）
3. **形式変換**: ドメインエンティティとレガシー形式の相互変換

### 8.2 簡素化された移行アプローチ
1. **最小限の並行稼働**: 移行期間を最短に
2. **レガシー依存の最小化**: FFmpegとWhisperXのみ
3. **早期の完全切り替え**: 複雑な互換性維持を避ける

### 8.3 テスト戦略
1. **単体テスト**: 各クラスを独立してテスト
2. **統合テスト**: レイヤー間の連携をテスト
3. **E2Eテスト**: ユーザーシナリオ全体をテスト

### 8.4 よくある実装ミス
1. **DependenciesContainerのoverride**: DependenciesContainerは直接overrideできない
2. **設定の内部生成**: Gateway Adapter内でConfigを生成してはいけない
3. **コンテナの重複生成**: 子コンテナを別途インスタンス化してはいけない

## 9. パフォーマンス最適化

### 9.1 SingletonとFactoryの使い分け

#### 9.1.1 Singletonを使うべきケース
```python
# 状態を持たない、または共有状態を持つコンポーネント
gateway = providers.Singleton(
    FileGatewayAdapter
)

# リソースを多く使うコンポーネント
transcription_gateway = providers.Singleton(
    TranscriptionGatewayAdapter,
    config=config.legacy_config
)
```

**Singletonの利点**:
- メモリ効率が良い（インスタンスが1つだけ）
- 初期化コストが1回だけ
- 状態を共有できる

#### 9.1.2 Factoryを使うべきケース
```python
# リクエストごとに新しい状態が必要なコンポーネント
use_case = providers.Factory(
    TranscribeVideoUseCase,
    gateway=transcription_gateway
)

# UIコンポーネント（画面ごとに独立した状態）
view_model = providers.Factory(
    TranscriptionViewModel
)
```

**Factoryの利点**:
- 各リクエストで独立した状態
- 並行処理で安全
- テストしやすい

### 9.2 遅延初期化パターン

#### 9.2.1 重いリソースの遅延読み込み
```python
class TranscriptionGatewayAdapter:
    def __init__(self, config: Config):
        self.config = config
        self._model = None  # 遅延初期化
    
    @property
    def model(self):
        """モデルを初めて使用する時に読み込む"""
        if self._model is None:
            self._model = self._load_model()
        return self._model
    
    def _load_model(self):
        """重いモデルの読み込み処理"""
        # 実際に使用される時まで遅延
        return WhisperModel(self.config.model_size)
```

### 9.3 リソース管理のベストプラクティス

#### 9.3.1 コンテナのシャットダウン
```python
def cleanup():
    """アプリケーション終了時のクリーンアップ"""
    try:
        if app_container:
            # すべてのリソースを解放
            app_container.shutdown_resources()
            
            # 特定のリソースの明示的なクリーンアップ
            if hasattr(app_container, 'gateways'):
                gateways = app_container.gateways()
                if hasattr(gateways, 'transcription_gateway'):
                    gateways.transcription_gateway.cleanup()
    except Exception as e:
        logger.error(f"クリーンアップ中にエラー: {e}")
```

## 10. テスト戦略の詳細

### 10.1 DIコンテナを使った単体テスト

#### 10.1.1 テスト用コンテナの作成
```python
class TestContainer(containers.DeclarativeContainer):
    """テスト用のDIコンテナ"""
    
    # モックゲートウェイ
    mock_transcription_gateway = providers.Singleton(
        MockTranscriptionGateway
    )
    
    # テスト対象のユースケース
    transcribe_use_case = providers.Factory(
        TranscribeVideoUseCase,
        gateway=mock_transcription_gateway
    )
```

#### 10.1.2 モックの作成方法
```python
class MockTranscriptionGateway(ITranscriptionGateway):
    """テスト用のモックゲートウェイ"""
    
    def __init__(self):
        self.call_count = 0
        self.last_params = None
    
    def transcribe(self, video_path: FilePath, **kwargs):
        self.call_count += 1
        self.last_params = {'video_path': video_path, **kwargs}
        
        # テスト用の固定レスポンス
        return TranscriptionResult(
            id="test-id",
            language="ja",
            segments=[],
            # ... 他のフィールド
        )
```

### 10.2 統合テストのパターン

#### 10.2.1 部分的な実装の置き換え
```python
def test_with_partial_mocks():
    """一部だけモックに置き換えたテスト"""
    # 本番用コンテナを作成
    container = create_container()
    
    # 外部APIだけモックに置き換え
    container.gateways.transcription_gateway.override(
        providers.Singleton(MockTranscriptionGateway)
    )
    
    # テスト実行
    presenter = container.presentation.transcription_presenter()
    result = presenter.start_transcription()
    
    assert result is True
```

## 11. 実装の段階的アプローチ

### 11.1 フェーズ別実装順序

#### Phase 1: 文字起こし機能（Week 2）
```python
# 必要なコンポーネント
- WhisperXGateway（既存活用）
- TranscribeVideoUseCase
- TranscriptionViewModel/Presenter/View
- 基本的なSessionManager
```

#### Phase 2: テキスト編集機能（Week 3）
```python
# 追加コンポーネント
- TextProcessorGateway（既存活用）
- TextEditUseCase
- TextEditorViewModel/Presenter/View
```

#### Phase 3: エクスポート機能（Week 4-4.5）
```python
# 追加コンポーネント（優先順）
1. SilenceDetectionGateway（既存活用）
2. FCPXMLExportGateway（既存活用）
3. EDLExportGateway（既存活用）
4. SRTExportGateway（新規実装）
```

### 11.2 リスク管理と対策

#### 11.2.1 技術的リスク
| リスク | 対策 | フォールバック |
|--------|------|----------------|
| 新規実装のバグ | 十分なテスト期間 | 既存実装への切り替え |
| パフォーマンス問題 | 早期の性能測定 | アルゴリズム最適化 |
| 既存コードの不具合 | ラッパーでの隔離 | 代替実装の準備 |

#### 11.2.2 スケジュールリスク
- マイルストーンごとのGo/No-Go判定
- バッファ期間の確保（各フェーズ+0.5週）
- 段階的リリースによる早期フィードバック

### 11.3 技術的負債の管理

#### 11.3.1 負債の記録
```yaml
# tech_debt.yaml
debt_items:
  - id: TD001
    description: "Gateway Adapterの暫定実装"
    impact: "中"
    planned_resolution: "Phase 5"
  
  - id: TD002
    description: "エラーハンドリングの統一化未完"
    impact: "低"
    planned_resolution: "次四半期"
```

#### 11.3.2 返済計画
1. **即時対応**: セキュリティや重大バグ
2. **計画的対応**: 四半期ごとのリファクタリング
3. **機会的対応**: 機能追加時の改善

## 12. パフォーマンス監視と最適化

### 12.1 メトリクス収集
```python
class PerformanceMonitor:
    """パフォーマンス監視"""
    
    @contextmanager
    def measure(self, operation: str):
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            logger.info(f"{operation}: {duration:.2f}秒")
            
            # 閾値チェック
            if operation == "transcription" and duration > 600:
                logger.warning(f"文字起こしが目標時間を超過: {duration}秒")
```

### 12.2 最適化の優先順位
1. **文字起こし処理**: バッチ処理の導入
2. **無音検出**: 並列処理の検討
3. **エクスポート**: ストリーミング書き込み

## 13. まとめ

### 13.1 調整後の主な変更点
1. **既存活用を7つに拡大**（複雑で実績のある部分）
2. **実装期間を5週間に延長**（現実的な見積もり）
3. **段階的リリース**（リスク軽減）
4. **技術的負債の明示的管理**（長期保守性）
5. **パフォーマンス目標の明確化**（品質保証）

### 13.2 成功の鍵
- **バランスの取れたアプローチ**: 理想と現実の調和
- **段階的な実装**: 早期のフィードバック獲得
- **明確な目標**: 測定可能な成功基準
- **柔軟な対応**: 問題発生時の代替案

作成日: 2025-01-01  
更新日: 2025-01-30  
バージョン: 2.1（現実的な調整版）