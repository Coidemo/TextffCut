"""
文字起こしユースケースのテスト
"""

from unittest.mock import Mock, patch

import pytest

from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.value_objects import FilePath
from use_cases.exceptions import (
    CacheNotFoundError,
    ModelNotAvailableError,
    TranscriptionError,
)
from use_cases.transcription import (
    LoadCacheRequest,
    LoadTranscriptionCacheUseCase,
    ParallelTranscribeRequest,
    ParallelTranscribeUseCase,
    TranscribeVideoRequest,
    TranscribeVideoUseCase,
)


class TestTranscribeVideoUseCase:
    """TranscribeVideoUseCaseのテスト"""

    @pytest.fixture
    def mock_gateway(self):
        """モックゲートウェイ"""
        gateway = Mock()
        gateway.get_available_models.return_value = ["tiny", "base", "small", "medium", "large"]
        return gateway

    @pytest.fixture
    def mock_result(self):
        """モック結果"""
        segments = [TranscriptionSegment(id="1", text="テストセグメント", start=0.0, end=2.0)]
        return TranscriptionResult(
            id="test",
            language="ja",
            segments=segments,
            original_audio_path="/test/video.mp4",
            model_size="medium",
            processing_time=10.0,
        )

    def test_successful_transcription(self, mock_gateway, mock_result):
        """正常な文字起こし"""
        # Arrange
        mock_gateway.transcribe.return_value = mock_result
        mock_gateway.load_from_cache.return_value = None

        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(video_path=FilePath("/test/video.mp4"), model_size="medium")

        # ファイル存在チェックをモック
        with patch.object(FilePath, "exists", property(lambda self: True)):
            # Act
            result = use_case.execute(request)

        # Assert
        assert result == mock_result
        mock_gateway.transcribe.assert_called_once()

    def test_use_cached_result(self, mock_gateway, mock_result):
        """キャッシュを使用"""
        # Arrange
        mock_gateway.load_from_cache.return_value = mock_result

        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(video_path=FilePath("/test/video.mp4"), model_size="medium", use_cache=True)

        with patch.object(FilePath, "exists", property(lambda self: True)):
            # Act
            result = use_case.execute(request)

        # Assert
        assert result == mock_result
        mock_gateway.transcribe.assert_not_called()  # 新規文字起こしは実行されない

    def test_file_not_found(self, mock_gateway):
        """ファイルが存在しない場合"""
        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(video_path=FilePath("/test/nonexistent.mp4"))

        with patch.object(FilePath, "exists", property(lambda self: False)):
            with pytest.raises(TranscriptionError, match="Video file not found"):
                use_case(request)  # __call__メソッドを使用

    def test_invalid_file_extension(self, mock_gateway):
        """無効な拡張子"""
        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(video_path=FilePath("/test/document.pdf"))

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "extension", property(lambda self: ".pdf")):
                with pytest.raises(TranscriptionError, match="Invalid video/audio format"):
                    use_case(request)

    def test_model_not_available(self, mock_gateway):
        """利用できないモデル"""
        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(
            video_path=FilePath("/test/video.mp4"), model_size="ultra-large"  # 存在しないモデル
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with pytest.raises(ModelNotAvailableError, match="Model 'ultra-large' is not available"):
                use_case(request)

    def test_progress_callback(self, mock_gateway, mock_result):
        """進捗コールバック"""
        # Arrange
        mock_gateway.transcribe.return_value = mock_result
        mock_gateway.load_from_cache.return_value = None

        progress_messages = []

        def progress_callback(msg):
            progress_messages.append(msg)

        use_case = TranscribeVideoUseCase(mock_gateway)
        request = TranscribeVideoRequest(video_path=FilePath("/test/video.mp4"), progress_callback=progress_callback)

        with patch.object(FilePath, "exists", property(lambda self: True)):
            # Act
            use_case.execute(request)

        # Assert
        assert "Starting transcription..." in progress_messages


class TestLoadTranscriptionCacheUseCase:
    """LoadTranscriptionCacheUseCaseのテスト"""

    @pytest.fixture
    def mock_gateway(self):
        """モックゲートウェイ"""
        return Mock()

    @pytest.fixture
    def mock_caches(self):
        """モックキャッシュリスト"""
        return [
            {"path": "/cache/medium.json", "model_size": "medium", "created_at": 1000.0, "language": "ja"},
            {"path": "/cache/large.json", "model_size": "large", "created_at": 2000.0, "language": "ja"},
        ]

    def test_load_specific_model_cache(self, mock_gateway, mock_caches):
        """特定モデルのキャッシュ読み込み"""
        # Arrange
        mock_gateway.list_available_caches.return_value = mock_caches
        mock_result = Mock()
        mock_result.segments = [Mock()]
        mock_result.language = "ja"
        mock_gateway.load_from_cache.return_value = mock_result

        use_case = LoadTranscriptionCacheUseCase(mock_gateway)
        request = LoadCacheRequest(video_path=FilePath("/test/video.mp4"), model_size="large")

        # Act
        result = use_case.execute(request)

        # Assert
        assert result == mock_result
        mock_gateway.load_from_cache.assert_called_with(video_path=request.video_path, model_size="large")

    def test_load_latest_cache(self, mock_gateway, mock_caches):
        """最新のキャッシュを読み込み（モデル指定なし）"""
        # Arrange
        mock_gateway.list_available_caches.return_value = mock_caches
        mock_result = Mock()
        mock_result.segments = [Mock()]
        mock_result.language = "ja"
        mock_gateway.load_from_cache.return_value = mock_result

        use_case = LoadTranscriptionCacheUseCase(mock_gateway)
        request = LoadCacheRequest(video_path=FilePath("/test/video.mp4"), model_size=None)  # 最新を選択

        # Act
        result = use_case.execute(request)

        # Assert
        # 最初のキャッシュ（最新と仮定）が選択される
        mock_gateway.load_from_cache.assert_called_with(video_path=request.video_path, model_size="medium")

    def test_no_cache_found(self, mock_gateway):
        """キャッシュが見つからない"""
        # Arrange
        mock_gateway.list_available_caches.return_value = []

        use_case = LoadTranscriptionCacheUseCase(mock_gateway)
        request = LoadCacheRequest(video_path=FilePath("/test/video.mp4"))

        # Act & Assert
        with pytest.raises(CacheNotFoundError, match="No cache found"):
            use_case.execute(request)

    def test_list_available_caches_helper(self, mock_gateway, mock_caches):
        """利用可能なキャッシュ一覧の取得"""
        # Arrange
        mock_gateway.list_available_caches.return_value = mock_caches

        use_case = LoadTranscriptionCacheUseCase(mock_gateway)

        # Act
        cache_infos = use_case.list_available_caches(FilePath("/test/video.mp4"))

        # Assert
        assert len(cache_infos) == 2
        assert cache_infos[0].model_size == "medium"
        assert cache_infos[1].model_size == "large"


class TestParallelTranscribeUseCase:
    """ParallelTranscribeUseCaseのテスト"""

    @pytest.fixture
    def mock_transcription_gateway(self):
        """モック文字起こしゲートウェイ"""
        return Mock()

    @pytest.fixture
    def mock_video_gateway(self):
        """モック動画ゲートウェイ"""
        gateway = Mock()
        gateway.get_video_info.return_value = {"duration": 1200.0, "fps": 30.0, "width": 1920, "height": 1080}  # 20分
        return gateway

    def test_parallel_transcription(self, mock_transcription_gateway, mock_video_gateway):
        """並列文字起こし"""
        # Arrange
        mock_result = Mock()
        mock_result.segments = [Mock()]
        mock_result.duration = 1200.0
        mock_result.processing_time = 120.0  # 2分
        mock_transcription_gateway.transcribe_parallel.return_value = mock_result

        use_case = ParallelTranscribeUseCase(mock_transcription_gateway, mock_video_gateway)
        request = ParallelTranscribeRequest(video_path=FilePath("/test/long_video.mp4"), num_workers=4)

        with patch.object(FilePath, "exists", property(lambda self: True)):
            # Act
            result = use_case.execute(request)

        # Assert
        assert result == mock_result
        mock_transcription_gateway.transcribe_parallel.assert_called_once()

    def test_fallback_to_single_transcription(self, mock_transcription_gateway, mock_video_gateway):
        """短い動画は通常の文字起こしにフォールバック"""
        # Arrange
        mock_video_gateway.get_video_info.return_value = {
            "duration": 300.0,  # 5分（チャンク時間より短い）
        }
        mock_result = Mock()
        mock_result.segments = [Mock()]
        mock_transcription_gateway.transcribe.return_value = mock_result

        use_case = ParallelTranscribeUseCase(mock_transcription_gateway, mock_video_gateway)
        request = ParallelTranscribeRequest(video_path=FilePath("/test/short_video.mp4"), chunk_duration=600.0)  # 10分

        with patch.object(FilePath, "exists", property(lambda self: True)):
            # Act
            result = use_case.execute(request)

        # Assert
        mock_transcription_gateway.transcribe.assert_called_once()
        mock_transcription_gateway.transcribe_parallel.assert_not_called()

    def test_parameter_validation(self):
        """パラメータの検証"""
        request = ParallelTranscribeRequest(
            video_path="/test/video.mp4",
            num_workers=20,  # 大きすぎる
            chunk_duration=30.0,  # 小さすぎる
            min_chunk_duration=60.0,
        )

        # パラメータが調整される
        assert request.num_workers == 8  # 最大値に制限
        assert request.chunk_duration == 60.0  # 最小値に調整
