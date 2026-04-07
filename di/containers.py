"""
DIコンテナ定義

アプリケーション全体の依存関係を管理するコンテナを定義します。
"""

from pathlib import Path

from dependency_injector import containers, providers

from adapters.error_handling import ErrorHandlerAdapter
from adapters.gateways.export.edl_export_gateway import EDLExportGatewayAdapter
from adapters.gateways.export.fcpxml_export_gateway import FCPXMLExportGatewayAdapter
from adapters.gateways.export.srt_export_gateway import SRTExportGatewayAdapter
from adapters.gateways.export.video_export_gateway import VideoExportGatewayAdapter

# アダプター層のインポート
from adapters.gateways.file.file_gateway import FileGatewayAdapter
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from adapters.gateways.transcription.optimized_transcription_gateway import OptimizedTranscriptionGatewayAdapter
from adapters.gateways.video_processing.video_processor_gateway import VideoProcessorGatewayAdapter
from di.config import DIConfig
from di.providers import StreamlitSessionProvider
from infrastructure.gateways.audio_optimizer_gateway_adapter import AudioOptimizerGatewayAdapter
from infrastructure.repositories.performance_profile_repository import FilePerformanceProfileRepository
from core.auto_optimizer import AutoOptimizer
from core.memory_monitor import MemoryMonitor

# Presentation層はStreamlit依存のため、インストールされていない場合はスキップ
try:
    from presentation.di_config import PresentationContainer
except ImportError:
    PresentationContainer = None

# サービス層のインポート（段階的移行用） - servicesパッケージ削除済み
# from services.configuration_service import ConfigurationService
# from services.text_editing_service import TextEditingService
# from services.transcription_service import TranscriptionService
# from services.video_processing_service import VideoProcessingService
from use_cases.editing.find_differences import FindTextDifferencesUseCase
from use_cases.export.export_fcpxml import ExportFCPXMLUseCase
from use_cases.export.export_srt import ExportSRTUseCase
from use_cases.transcription.load_cache import LoadTranscriptionCacheUseCase

# ユースケースのインポート
from use_cases.transcription.transcribe_video import TranscribeVideoUseCase
from use_cases.video.detect_silence import DetectSilenceUseCase
from application.use_cases.optimize_audio_use_case import OptimizeAudioUseCase
from utils.logging import get_logger

logger = get_logger(__name__)


class GatewayContainer(containers.DeclarativeContainer):
    """
    ゲートウェイのコンテナ

    アダプター層のゲートウェイ実装を管理します。
    """

    # 設定
    config = providers.DependenciesContainer()

    # ファイルゲートウェイ
    file_gateway = providers.Singleton(FileGatewayAdapter)

    # 音声最適化ゲートウェイ
    audio_optimizer_gateway = providers.Singleton(AudioOptimizerGatewayAdapter)

    # パフォーマンスプロファイルリポジトリ
    performance_profile_repository = providers.Singleton(FilePerformanceProfileRepository)

    # 文字起こしゲートウェイ（最適化版）
    transcription_gateway = providers.Factory(
        OptimizedTranscriptionGatewayAdapter,
        config=config.legacy_config,
        profile_repository=performance_profile_repository,
    )

    # テキスト処理ゲートウェイ
    text_processor_gateway = providers.Singleton(SequenceMatcherTextProcessorGateway)

    # 動画処理ゲートウェイ
    video_processor_gateway = providers.Singleton(VideoProcessorGatewayAdapter, config=config.legacy_config)

    # FCPXMLエクスポートゲートウェイ
    fcpxml_export_gateway = providers.Singleton(FCPXMLExportGatewayAdapter, config=config.legacy_config)

    # SRTエクスポートゲートウェイ
    srt_export_gateway = providers.Singleton(SRTExportGatewayAdapter, config=config.legacy_config)

    # EDLエクスポートゲートウェイ
    edl_export_gateway = providers.Singleton(EDLExportGatewayAdapter, config=config.legacy_config)

    # 動画エクスポートゲートウェイ
    video_export_gateway = providers.Singleton(VideoExportGatewayAdapter, config=config.legacy_config)

    # 注: AI ゲートウェイは実行時にAPIキーを必要とするため、main.pyで直接作成する


class UseCaseContainer(containers.DeclarativeContainer):
    """
    ユースケースのコンテナ

    ビジネスロジックを実行するユースケースを管理します。
    """

    # ゲートウェイコンテナ
    gateways = providers.DependenciesContainer()

    # 文字起こしユースケース
    transcribe_video = providers.Factory(TranscribeVideoUseCase, transcription_gateway=gateways.transcription_gateway)

    # キャッシュ読み込みユースケース
    load_transcription_cache = providers.Factory(
        LoadTranscriptionCacheUseCase, transcription_gateway=gateways.transcription_gateway
    )

    # テキスト差分検出ユースケース
    find_differences = providers.Factory(
        FindTextDifferencesUseCase, text_processor_gateway=gateways.text_processor_gateway
    )

    # 無音検出ユースケース
    detect_silence = providers.Factory(
        DetectSilenceUseCase, video_gateway=gateways.video_processor_gateway, file_gateway=gateways.file_gateway
    )

    # FCPXMLエクスポートユースケース
    export_fcpxml = providers.Factory(
        ExportFCPXMLUseCase, export_gateway=gateways.fcpxml_export_gateway, file_gateway=gateways.file_gateway
    )

    # SRT字幕エクスポートユースケース
    export_srt = providers.Factory(
        ExportSRTUseCase, srt_gateway=gateways.srt_export_gateway, file_gateway=gateways.file_gateway
    )

    # 音声最適化ユースケース
    optimize_audio = providers.Factory(
        OptimizeAudioUseCase,
        audio_optimizer_gateway=gateways.audio_optimizer_gateway,
        profile_repository=gateways.performance_profile_repository,
    )

    # 注: AI バズクリップ生成ユースケースは実行時にAI gatewayを必要とするため、main.pyで直接作成する


class ServiceContainer(containers.DeclarativeContainer):
    """
    サービス層のコンテナ（レガシー互換性のため）

    servicesパッケージが削除されたため、空のコンテナとして保持。
    """

    # 設定
    config = providers.DependenciesContainer()

    # エラーハンドラーのみ保持
    error_handler = providers.Singleton(
        ErrorHandlerAdapter, logger=providers.Callable(get_logger, name="error_handler")
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """
    アプリケーション全体のDIコンテナ

    全ての依存関係を管理するルートコンテナです。
    """

    # 設定
    config = providers.Singleton(DIConfig)

    # 既存のConfigインスタンス（レガシー互換性）
    legacy_config = providers.Callable(lambda di_config: di_config.get_legacy_config(), di_config=config)

    # ゲートウェイコンテナ
    gateways = providers.Container(
        GatewayContainer, config=providers.DependenciesContainer(legacy_config=legacy_config)
    )

    # ユースケースコンテナ
    use_cases = providers.Container(UseCaseContainer, gateways=gateways)

    # サービスコンテナ（レガシー互換性）
    services = providers.Container(
        ServiceContainer, config=providers.DependenciesContainer(legacy_config=legacy_config)
    )

    # Presentation層コンテナ（Streamlit がインストールされている場合のみ）
    if PresentationContainer is not None:
        presentation = providers.Container(PresentationContainer, gateways=gateways, use_cases=use_cases, services=services)

    # Streamlit連携用プロバイダー
    api_key_provider = providers.Singleton(
        StreamlitSessionProvider, session_key="api_key", default_factory=lambda: "default_api_key"
    )

    model_size_provider = providers.Singleton(
        StreamlitSessionProvider, session_key="model_size", default_factory=lambda: "base"
    )

    use_api_provider = providers.Singleton(
        StreamlitSessionProvider, session_key="use_api", default_factory=lambda: False
    )


def create_container(config: DIConfig | None = None, override_providers: dict | None = None) -> ApplicationContainer:
    """
    DIコンテナを作成

    Args:
        config: DI設定（Noneの場合はデフォルト設定）
        override_providers: オーバーライドするプロバイダーの辞書

    Returns:
        設定済みのApplicationContainer
    """
    container = ApplicationContainer()

    # 設定のオーバーライド
    if config:
        container.config.override(providers.Object(config))

    # プロバイダーのオーバーライド
    if override_providers:
        for name, provider in override_providers.items():
            if hasattr(container, name):
                getattr(container, name).override(provider)

    # 初期化ログ
    logger.info("DI container created successfully")

    return container


# グローバルコンテナインスタンス（オプション）
_global_container: ApplicationContainer | None = None


def get_container() -> ApplicationContainer:
    """
    グローバルコンテナを取得

    Returns:
        ApplicationContainerインスタンス
    """
    global _global_container
    if _global_container is None:
        _global_container = create_container()
    return _global_container


def reset_container():
    """グローバルコンテナをリセット"""
    global _global_container
    if _global_container:
        _global_container.shutdown_resources()
    _global_container = None
