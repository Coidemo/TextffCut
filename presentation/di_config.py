"""
Presentation層のDI設定

Presentation層のコンポーネントをDIコンテナに登録します。
"""

from dependency_injector import containers, providers

from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.presenters.main import MainPresenter
from presentation.presenters.sidebar import SidebarPresenter
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.presenters.transcription import TranscriptionPresenter
from presentation.presenters.video_input import VideoInputPresenter
from presentation.presenters.youtube_download import YouTubeDownloadPresenter
from presentation.presenters.buzz_clip import BuzzClipPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel
from presentation.view_models.main import MainViewModel
from presentation.view_models.sidebar import SidebarViewModel
from presentation.view_models.text_editor import TextEditorViewModel
from presentation.view_models.transcription import TranscriptionViewModel
from presentation.view_models.video_input import VideoInputViewModel
from presentation.view_models.youtube_download import YouTubeDownloadViewModel
from presentation.view_models.buzz_clip import BuzzClipViewModel


class PresentationContainer(containers.DeclarativeContainer):
    """
    Presentation層のDIコンテナ

    ViewModelとPresenterを管理します。
    """

    # 依存関係
    gateways = providers.DependenciesContainer()
    use_cases = providers.DependenciesContainer()
    services = providers.DependenciesContainer()

    # SessionManager (シングルトン)
    session_manager = providers.Singleton(SessionManager)

    # ViewModels (ファクトリーパターン - 毎回新しいインスタンス)
    video_input_view_model = providers.Factory(VideoInputViewModel)

    transcription_view_model = providers.Factory(TranscriptionViewModel)

    text_editor_view_model = providers.Factory(TextEditorViewModel)

    export_settings_view_model = providers.Factory(ExportSettingsViewModel)

    main_view_model = providers.Factory(MainViewModel)

    sidebar_view_model = providers.Factory(SidebarViewModel)
    youtube_download_view_model = providers.Factory(YouTubeDownloadViewModel)
    buzz_clip_view_model = providers.Factory(BuzzClipViewModel)

    # Presenters (ファクトリーパターン)
    video_input_presenter = providers.Factory(
        VideoInputPresenter,
        view_model=video_input_view_model,
        file_gateway=gateways.file_gateway,
        video_gateway=gateways.video_processor_gateway,
    )

    transcription_presenter = providers.Factory(
        TranscriptionPresenter,
        view_model=transcription_view_model,
        transcribe_use_case=use_cases.transcribe_video,
        load_cache_use_case=use_cases.load_transcription_cache,
        file_gateway=gateways.file_gateway,
        transcription_gateway=gateways.transcription_gateway,
        error_handler=services.error_handler,
        session_manager=session_manager,
    )

    text_editor_presenter = providers.Factory(
        TextEditorPresenter,
        view_model=text_editor_view_model,
        text_processor_gateway=gateways.text_processor_gateway,
        video_processor_gateway=gateways.video_processor_gateway,
        error_handler=services.error_handler,
    )

    export_settings_presenter = providers.Factory(
        ExportSettingsPresenter,
        view_model=export_settings_view_model,
        video_processor_gateway=gateways.video_processor_gateway,
        video_export_gateway=gateways.video_export_gateway,
        fcpxml_export_gateway=gateways.fcpxml_export_gateway,
        edl_export_gateway=gateways.edl_export_gateway,
        srt_export_gateway=gateways.srt_export_gateway,
        session_manager=session_manager,
        error_handler=services.error_handler,
    )

    sidebar_presenter = providers.Factory(
        SidebarPresenter,
        view_model=sidebar_view_model,
        session_manager=session_manager,
        file_gateway=gateways.file_gateway,
        error_handler=services.error_handler,
    )
    
    youtube_download_presenter = providers.Factory(
        YouTubeDownloadPresenter,
        view_model=youtube_download_view_model,
        session_manager=session_manager,
        download_use_case=use_cases.download_youtube_video,
        get_info_use_case=providers.Factory(
            lambda gw: __import__('use_cases.youtube.download_youtube_video', fromlist=['GetVideoInfo']).GetVideoInfo(gw),
            gateways.youtube_download_gateway
        ),
        error_handler=services.error_handler,
    )
    
    buzz_clip_presenter = providers.Factory(
        BuzzClipPresenter,
        view_model=buzz_clip_view_model,
        generate_buzz_clips_use_case=providers.Arg('generate_buzz_clips_use_case'),
        session_manager=session_manager,
    )

    main_presenter = providers.Factory(
        MainPresenter,
        view_model=main_view_model,
        video_input_presenter=video_input_presenter,
        transcription_presenter=transcription_presenter,
        text_editor_presenter=text_editor_presenter,
        export_settings_presenter=export_settings_presenter,
        session_manager=session_manager,
        error_handler=services.error_handler,
    )
