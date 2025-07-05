"""
TranscriptionPresenterのテスト
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# InterruptedErrorは標準の例外を使用
from presentation.presenters.transcription import TranscriptionPresenter
from presentation.view_models.transcription import TranscriptionCache, TranscriptionViewModel


class TestTranscriptionPresenter:
    """TranscriptionPresenterのテスト"""

    @pytest.fixture
    def view_model(self):
        """テスト用ViewModel"""
        return TranscriptionViewModel()

    @pytest.fixture
    def mock_transcribe_use_case(self):
        """モックの文字起こしユースケース"""
        mock = Mock()
        mock.execute.return_value = Mock(segments=[])
        return mock

    @pytest.fixture
    def mock_load_cache_use_case(self):
        """モックのキャッシュ読み込みユースケース"""
        mock = Mock()
        mock.execute.return_value = Mock(segments=[])
        return mock

    @pytest.fixture
    def mock_file_gateway(self):
        """モックのファイルゲートウェイ"""
        return Mock()

    @pytest.fixture
    def mock_transcription_gateway(self):
        """モックの文字起こしゲートウェイ"""
        mock = Mock()
        # 動画情報のモック
        mock.get_video_info.return_value = Mock(duration=300.0)  # 5分
        # キャッシュ一覧のモック
        mock.get_available_caches.return_value = [
            {
                "file_path": "/path/to/cache1.json",
                "mode": "local",
                "model_size": "medium",
                "modified_time": 1234567890.0,
                "is_api": False,
            }
        ]
        return mock

    @pytest.fixture
    def mock_error_handler(self):
        """モックのエラーハンドラー"""
        mock = Mock()

        # handle_errorの振る舞いを設定
        def handle_error(error, context, raise_after=False):
            # エラーのタイプに応じて異なるメッセージを返す
            if isinstance(error, Exception) and "処理が中止されました" in str(error):
                return None  # InterruptedErrorの場合はNoneを返す
            # 通常のテスト実行では何もエラーを返さない
            return None

        mock.handle_error.side_effect = handle_error
        return mock

    @pytest.fixture
    def presenter(
        self,
        view_model,
        mock_transcribe_use_case,
        mock_load_cache_use_case,
        mock_file_gateway,
        mock_transcription_gateway,
        mock_error_handler,
    ):
        """テスト用Presenter"""
        presenter = TranscriptionPresenter(
            view_model=view_model,
            transcribe_use_case=mock_transcribe_use_case,
            load_cache_use_case=mock_load_cache_use_case,
            file_gateway=mock_file_gateway,
            transcription_gateway=mock_transcription_gateway,
            error_handler=mock_error_handler,
        )
        return presenter

    def test_initialize_with_video(self, presenter, mock_transcription_gateway):
        """動画での初期化のテスト"""
        video_path = Path("/test/video.mp4")

        with patch("utils.time_utils.format_time", return_value="5:00"):
            presenter.initialize_with_video(video_path)

        # 動画情報が設定されているか
        assert presenter.view_model.video_path == video_path
        assert presenter.view_model.video_duration_minutes == 5.0
        assert presenter.view_model.video_duration_text == "5:00"

        # キャッシュが読み込まれているか
        assert len(presenter.view_model.available_caches) == 1
        assert presenter.view_model.available_caches[0].mode == "local"

        # Gatewayが呼ばれているか
        mock_transcription_gateway.get_video_info.assert_called_once_with(str(video_path))
        mock_transcription_gateway.get_available_caches.assert_called_once_with(str(video_path))

    def test_set_processing_mode_api(self, presenter):
        """APIモード設定のテスト"""
        presenter.view_model.video_duration_minutes = 10.0

        presenter.set_processing_mode(use_api=True)

        assert presenter.view_model.use_api is True
        assert presenter.view_model.model_size == "whisper-1"
        # 料金が計算されているか（$0.006/分 * 10分 = $0.06）
        assert presenter.view_model.estimated_cost_usd == pytest.approx(0.06)
        assert presenter.view_model.estimated_cost_jpy == pytest.approx(9.0)

    def test_set_processing_mode_local(self, presenter):
        """ローカルモード設定のテスト"""
        presenter.set_processing_mode(use_api=False)

        assert presenter.view_model.use_api is False
        assert presenter.view_model.model_size == "medium"
        assert presenter.view_model.estimated_cost_usd == 0
        assert presenter.view_model.estimated_cost_jpy == 0

    def test_select_cache(self, presenter):
        """キャッシュ選択のテスト"""
        cache = TranscriptionCache(
            file_path=Path("/test/cache.json"),
            mode="local",
            model_size="medium",
            modified_time=1234567890.0,
            is_api=False,
        )

        presenter.select_cache(cache)

        assert presenter.view_model.selected_cache == cache
        assert presenter.view_model.use_cache is True

    def test_load_selected_cache_success(self, presenter, mock_transcription_gateway):
        """キャッシュ読み込み成功のテスト"""
        cache = TranscriptionCache(
            file_path=Path("/test/cache.json"),
            mode="local",
            model_size="medium",
            modified_time=1234567890.0,
            is_api=False,
        )
        presenter.view_model.selected_cache = cache

        # モックの設定
        mock_legacy_transcriber = Mock()
        mock_segment = Mock()
        mock_segment.text = "test"
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.words = []  # 空のリストでOK
        mock_segment.chars = []  # 空のリストでOK

        mock_legacy_result = Mock()
        mock_legacy_result.segments = [mock_segment]
        mock_legacy_result.language = "ja"
        mock_legacy_result.text = "test"
        mock_legacy_result.processing_time = 1.0
        mock_legacy_transcriber.load_from_cache.return_value = mock_legacy_result
        mock_transcription_gateway._legacy_transcriber = mock_legacy_transcriber

        result = presenter.load_selected_cache()

        assert result is True
        assert presenter.view_model.transcription_result is not None
        mock_legacy_transcriber.load_from_cache.assert_called_once_with(Path("/test/cache.json"))

    def test_load_selected_cache_no_cache(self, presenter):
        """キャッシュ未選択時のテスト"""
        result = presenter.load_selected_cache()

        assert result is False

    def test_start_transcription_success(self, presenter, mock_transcribe_use_case):
        """文字起こし成功のテスト"""
        presenter.view_model.video_path = Path("/test/video.mp4")
        presenter.view_model.use_api = False

        # モックが正しい結果を返すように修正
        mock_result = Mock(segments=[{"text": "test"}])
        mock_transcribe_use_case.execute.return_value = mock_result

        progress_callback = Mock()

        # デバッグ用にエラーメッセージを確認
        try:
            result = presenter.start_transcription(progress_callback)
        except Exception as e:
            print(f"Exception occurred: {e}")
            print(f"Error message: {presenter.view_model.error_message}")
            raise

        # デバッグ情報の出力
        if not result:
            print(f"Result is False. Error: {presenter.view_model.error_message}")
            print(f"Status: {presenter.view_model.status_message}")

        assert result is True
        assert presenter.view_model.transcription_result is not None
        assert presenter.view_model.is_processing is False
        assert presenter.view_model.progress == 1.0

        # ユースケースが呼ばれているか
        mock_transcribe_use_case.execute.assert_called_once()
        request = mock_transcribe_use_case.execute.call_args[0][0]
        assert str(request.video_path) == "/test/video.mp4"
        assert request.model_size == "medium"
        assert request.language == "ja"

    def test_start_transcription_cancelled(self, presenter, mock_transcribe_use_case):
        """文字起こしキャンセルのテスト"""
        presenter.view_model.video_path = Path("/test/video.mp4")

        # キャンセル時にInterruptedErrorを発生させる
        def execute_with_cancel(request):
            # progress_callbackを呼び出す（文字列のみ）
            request.progress_callback("処理中...")
            # ViewModelをキャンセル状態にする
            presenter.view_model.is_cancelled = True
            # 次のprogress_callbackでエラーが発生
            request.progress_callback("処理中...")
            return None

        mock_transcribe_use_case.execute.side_effect = execute_with_cancel

        result = presenter.start_transcription()

        assert result is False
        assert presenter.view_model.is_processing is False
        # キャンセル時はステータスメッセージが設定される
        assert presenter.view_model.status_message == "処理がキャンセルされました"

    def test_start_transcription_not_ready(self, presenter):
        """準備未完了時の文字起こしテスト"""
        # video_pathが未設定
        result = presenter.start_transcription()

        assert result is False
        assert presenter.view_model.error_message == "実行に必要な情報が不足しています"

    def test_cancel_transcription(self, presenter):
        """文字起こしキャンセルのテスト"""
        presenter.cancel_transcription()

        assert presenter.view_model.is_cancelled is True
        assert presenter.view_model.status_message == "処理をキャンセルしています..."

    def test_handle_error(self, presenter):
        """エラーハンドリングのテスト"""
        # エラーハンドラーをモックで置き換え
        mock_error_handler = Mock()
        mock_error_handler.handle_error.return_value = {"user_message": "テストエラー", "details": {"test": "error"}}
        presenter.error_handler = mock_error_handler

        error = Exception("テストエラー")
        presenter.handle_error(error, "テストコンテキスト")

        assert presenter.view_model.error_message == "テストエラー"
        assert presenter.view_model.error_details == {"test": "error"}
        assert presenter.view_model.is_processing is False

        mock_error_handler.handle_error.assert_called_once_with(error, context="テストコンテキスト", raise_after=False)

    def test_view_model_properties(self, presenter):
        """ViewModelのプロパティテスト"""
        vm = presenter.view_model

        # APIモード
        vm.use_api = True
        assert vm.mode_text == "API"
        assert vm.model_text == "whisper-1"

        # ローカルモード
        vm.use_api = False
        vm.model_size = "large"
        assert vm.mode_text == "ローカル"
        assert vm.model_text == "large"

        # 料金テキスト
        vm.use_api = True
        vm.estimated_cost_usd = 0.06
        vm.estimated_cost_jpy = 9.0
        assert vm.cost_text == "$0.060 (約9円)"

        vm.use_api = False
        assert vm.cost_text == "無料（ローカル処理）"

        # 準備状態
        vm.video_path = None
        vm.use_api = False
        assert vm.is_ready_to_run is False

        vm.video_path = Path("/test/video.mp4")
        assert vm.is_ready_to_run is True

        vm.use_api = True
        vm.api_key = None
        assert vm.is_ready_to_run is False

        vm.api_key = "sk-test"
        assert vm.is_ready_to_run is True
