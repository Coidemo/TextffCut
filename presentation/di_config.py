"""
Presentation層のDI設定

Presentation層のコンポーネントをDIコンテナに登録します。
"""

from dependency_injector import containers, providers

from presentation.view_models.video_input import VideoInputViewModel
from presentation.presenters.video_input import VideoInputPresenter
from presentation.view_models.transcription import TranscriptionViewModel
from presentation.presenters.transcription import TranscriptionPresenter


class PresentationContainer(containers.DeclarativeContainer):
    """
    Presentation層のDIコンテナ
    
    ViewModelとPresenterを管理します。
    """
    
    # 依存関係
    gateways = providers.DependenciesContainer()
    use_cases = providers.DependenciesContainer()
    services = providers.DependenciesContainer()
    
    # ViewModels (ファクトリーパターン - 毎回新しいインスタンス)
    video_input_view_model = providers.Factory(
        VideoInputViewModel
    )
    
    transcription_view_model = providers.Factory(
        TranscriptionViewModel
    )
    
    # Presenters (ファクトリーパターン)
    video_input_presenter = providers.Factory(
        VideoInputPresenter,
        view_model=video_input_view_model,
        file_gateway=gateways.file_gateway,
        video_gateway=gateways.video_processor_gateway
    )
    
    transcription_presenter = providers.Factory(
        TranscriptionPresenter,
        view_model=transcription_view_model,
        transcribe_use_case=use_cases.transcribe_video,
        load_cache_use_case=use_cases.load_transcription_cache,
        file_gateway=gateways.file_gateway,
        transcription_gateway=gateways.transcription_gateway,
        error_handler=services.error_handler
    )