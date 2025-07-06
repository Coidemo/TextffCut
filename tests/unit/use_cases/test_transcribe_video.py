"""
TranscribeVideoUseCaseの単体テスト

ユースケースのロジックを網羅的にテストします。
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.value_objects.duration import Duration
from use_cases.exceptions import ValidationError
from use_cases.transcription.transcribe_video import (
    TranscribeVideoRequest,
    TranscribeVideoUseCase,
    TranscriptionRequest,
)


class TestTranscribeVideoRequest:
    """TranscribeVideoRequestのテスト"""

    def test_valid_request_creation(self):
        """有効なリクエストが作成できることを確認"""
        request = TranscribeVideoRequest(
            video_path=Path("/path/to/video.mp4"),
            model_size="medium",
            language="ja",
            use_cache=True,
            save_cache=True,
            progress_callback=None,
        )
        assert request.video_path == Path("/path/to/video.mp4")
        assert request.model_size == "medium"
        assert request.language == "ja"
        assert request.use_cache is True
        assert request.save_cache is True
        assert request.progress_callback is None

    def test_request_with_callback(self):
        """コールバック付きリクエストが作成できることを確認"""
        callback = Mock()
        request = TranscribeVideoRequest(
            video_path=Path("/path/to/video.mp4"), model_size="large", progress_callback=callback
        )
        assert request.progress_callback == callback


class TestTranscribeVideoUseCase:
    """TranscribeVideoUseCaseのテスト"""

    @pytest.fixture
    def mock_transcription_gateway(self):
        """モックTranscriptionGatewayを作成"""
        gateway = Mock()
        gateway.get_available_models = Mock(return_value=["base", "small", "medium", "large"])
        gateway.transcribe = Mock()
        gateway.load_from_cache = Mock(return_value=None)
        gateway.save_to_cache = Mock()
        return gateway

    @pytest.fixture
    def use_case(self, mock_transcription_gateway):
        """テスト用のUseCaseインスタンスを作成"""
        return TranscribeVideoUseCase(transcription_gateway=mock_transcription_gateway)

    @pytest.fixture
    def sample_transcription_result(self):
        """サンプルの文字起こし結果を作成"""
        segments = [
            TranscriptionSegment(id="seg1", start=0.0, end=5.0, text="これはテストです。"),
            TranscriptionSegment(id="seg2", start=5.0, end=10.0, text="文字起こしのテスト。"),
        ]
        return TranscriptionResult(
            segments=segments, language="ja", duration=Duration(seconds=10.0), model_size="medium"
        )

    def test_validate_request_with_valid_input(self, use_case):
        """有効な入力でバリデーションが成功することを確認"""
        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")
        # エラーが発生しないことを確認
        use_case.validate_request(request)

    def test_validate_request_with_invalid_model(self, use_case):
        """無効なモデルサイズでエラーになることを確認"""
        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="invalid_model")
        with pytest.raises(ValidationError, match="Invalid model size"):
            use_case.validate_request(request)

    def test_validate_request_with_invalid_language(self, use_case):
        """無効な言語コードでエラーになることを確認"""
        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium", language="invalid")
        with pytest.raises(ValidationError, match="Invalid language code"):
            use_case.validate_request(request)

    def test_execute_successful_transcription(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """正常な文字起こし処理を確認"""
        # モックの設定
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        response = use_case.execute(request)

        # レスポンスの確認
        assert response.success is True
        assert response.result == sample_transcription_result
        assert response.error is None
        assert response.metadata["from_cache"] is False
        assert response.metadata["model_size"] == "medium"
        assert response.metadata["language"] == "ja"

        # ゲートウェイメソッドが呼ばれたことを確認
        mock_transcription_gateway.transcribe.assert_called_once()

    def test_execute_with_cache_hit(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """キャッシュヒット時の動作を確認"""
        # キャッシュから結果を返すように設定
        mock_transcription_gateway.load_from_cache.return_value = sample_transcription_result

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium", use_cache=True)

        response = use_case.execute(request)

        # レスポンスの確認
        assert response.success is True
        assert response.result == sample_transcription_result
        assert response.metadata["from_cache"] is True

        # transcribeが呼ばれていないことを確認
        mock_transcription_gateway.transcribe.assert_not_called()
        # キャッシュロードが呼ばれたことを確認
        mock_transcription_gateway.load_from_cache.assert_called_once()

    def test_execute_with_cache_miss(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """キャッシュミス時の動作を確認"""
        # キャッシュからNoneを返すように設定
        mock_transcription_gateway.load_from_cache.return_value = None
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result

        request = TranscribeVideoRequest(
            video_path=Path("/path/to/video.mp4"), model_size="medium", use_cache=True, save_cache=True
        )

        response = use_case.execute(request)

        # レスポンスの確認
        assert response.success is True
        assert response.result == sample_transcription_result
        assert response.metadata["from_cache"] is False

        # transcribeが呼ばれたことを確認
        mock_transcription_gateway.transcribe.assert_called_once()
        # キャッシュ保存が呼ばれたことを確認
        mock_transcription_gateway.save_to_cache.assert_called_once()

    def test_execute_without_cache(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """キャッシュを使用しない場合の動作を確認"""
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result

        request = TranscribeVideoRequest(
            video_path=Path("/path/to/video.mp4"), model_size="medium", use_cache=False, save_cache=False
        )

        response = use_case.execute(request)

        # レスポンスの確認
        assert response.success is True
        assert response.result == sample_transcription_result

        # キャッシュ関連メソッドが呼ばれていないことを確認
        mock_transcription_gateway.load_from_cache.assert_not_called()
        mock_transcription_gateway.save_to_cache.assert_not_called()

    def test_execute_with_progress_callback(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """プログレスコールバックが正しく渡されることを確認"""
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result
        progress_callback = Mock()

        request = TranscribeVideoRequest(
            video_path=Path("/path/to/video.mp4"), model_size="medium", progress_callback=progress_callback
        )

        response = use_case.execute(request)

        # transcribeに正しいリクエストが渡されたことを確認
        call_args = mock_transcription_gateway.transcribe.call_args[0][0]
        assert isinstance(call_args, TranscriptionRequest)
        assert call_args.progress_callback == progress_callback

    def test_execute_with_transcription_error(self, use_case, mock_transcription_gateway):
        """文字起こし中のエラーが適切に処理されることを確認"""
        mock_transcription_gateway.transcribe.side_effect = Exception("Transcription failed")

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        response = use_case.execute(request)

        # エラーレスポンスの確認
        assert response.success is False
        assert response.result is None
        assert response.error is not None
        assert "Transcription failed" in response.error

    def test_execute_with_cache_save_error(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """キャッシュ保存エラーが処理を妨げないことを確認"""
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result
        mock_transcription_gateway.save_to_cache.side_effect = Exception("Cache save failed")

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium", save_cache=True)

        response = use_case.execute(request)

        # 正常なレスポンスが返ることを確認（キャッシュエラーは無視）
        assert response.success is True
        assert response.result == sample_transcription_result
        assert "cache_save_error" in response.metadata

    def test_execute_with_empty_result(self, use_case, mock_transcription_gateway):
        """空の結果が返された場合の処理を確認"""
        # 空のセグメントを持つ結果
        empty_result = TranscriptionResult(
            segments=[], language="ja", duration=Duration(seconds=0), model_size="medium"
        )
        mock_transcription_gateway.transcribe.return_value = empty_result

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        response = use_case.execute(request)

        # 空でも成功として扱われることを確認
        assert response.success is True
        assert response.result == empty_result
        assert response.metadata["segments_count"] == 0

    def test_try_load_cache_success(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """_try_load_cacheメソッドが正常に動作することを確認"""
        mock_transcription_gateway.load_from_cache.return_value = sample_transcription_result

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        result = use_case._try_load_cache(request)

        assert result == sample_transcription_result
        mock_transcription_gateway.load_from_cache.assert_called_once_with(
            video_path=request.video_path, model_size=request.model_size, language=request.language
        )

    def test_try_load_cache_with_error(self, use_case, mock_transcription_gateway):
        """_try_load_cacheメソッドがエラーを適切に処理することを確認"""
        mock_transcription_gateway.load_from_cache.side_effect = Exception("Cache error")

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        result = use_case._try_load_cache(request)

        # エラーが発生してもNoneを返すことを確認
        assert result is None

    def test_metadata_generation(self, use_case, mock_transcription_gateway, sample_transcription_result):
        """メタデータが正しく生成されることを確認"""
        mock_transcription_gateway.transcribe.return_value = sample_transcription_result

        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="large", language="en")

        response = use_case.execute(request)

        # メタデータの内容を確認
        metadata = response.metadata
        assert metadata["from_cache"] is False
        assert metadata["model_size"] == "large"
        assert metadata["language"] == "en"
        assert metadata["segments_count"] == 2
        assert metadata["duration_seconds"] == 10.0
        assert metadata["video_path"] == str(request.video_path)

    def test_request_defaults(self):
        """TranscribeVideoRequestのデフォルト値を確認"""
        request = TranscribeVideoRequest(video_path=Path("/path/to/video.mp4"), model_size="medium")

        assert request.language == "ja"
        assert request.use_cache is True
        assert request.save_cache is True
        assert request.progress_callback is None
