"""
TranscriptionGatewayAdapterのテスト
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from core.transcription import TranscriptionResult as LegacyResult
from core.transcription import TranscriptionSegment as LegacySegment
from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.value_objects import FilePath
from use_cases.exceptions import TranscriptionError


class TestTranscriptionGatewayAdapter:
    """TranscriptionGatewayAdapterのテスト"""

    @pytest.fixture
    def mock_config(self):
        """モック設定"""
        config = Mock()
        config.transcription.use_api = False
        config.transcription.language = "ja"
        return config

    @pytest.fixture
    def mock_legacy_transcriber(self):
        """モックレガシーTranscriber"""
        with patch("adapters.gateways.transcription.transcription_gateway.LegacyTranscriber") as mock:
            yield mock

    @pytest.fixture
    def legacy_result(self):
        """テスト用レガシー結果"""
        # レガシーセグメント
        segments = [
            LegacySegment(
                start=0.0,
                end=2.5,
                text="これはテストです",
                words=[
                    {"word": "これは", "start": 0.0, "end": 1.0, "confidence": 0.95},
                    {"word": "テストです", "start": 1.0, "end": 2.5, "confidence": 0.93},
                ],
                chars=[
                    {"char": "こ", "start": 0.0, "end": 0.25, "confidence": 0.95},
                    {"char": "れ", "start": 0.25, "end": 0.5, "confidence": 0.95},
                    {"char": "は", "start": 0.5, "end": 1.0, "confidence": 0.95},
                ],
            ),
            LegacySegment(start=3.0, end=5.0, text="文字起こしのテスト", words=None, chars=None),
        ]

        # レガシー結果
        result = LegacyResult(
            language="ja",
            segments=segments,
            original_audio_path="/test/video.mp4",
            model_size="large-v3",
            processing_time=10.5,
        )

        return result

    def test_transcribe_success(self, mock_config, mock_legacy_transcriber, legacy_result):
        """正常な文字起こし"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.transcribe.return_value = legacy_result
        mock_legacy_transcriber.return_value = mock_instance

        # ゲートウェイの作成
        gateway = TranscriptionGatewayAdapter(mock_config)

        # 実行
        video_path = FilePath("/test/video.mp4")
        result = gateway.transcribe(video_path, model_size="large-v3")

        # 検証
        assert isinstance(result, TranscriptionResult)
        assert result.language == "ja"
        assert len(result.segments) == 2

        # 最初のセグメントの詳細確認
        segment = result.segments[0]
        assert segment.text == "これはテストです"
        assert segment.start == 0.0
        assert segment.end == 2.5
        assert len(segment.words) == 2
        assert len(segment.chars) == 3

        # Word情報の確認
        assert segment.words[0].word == "これは"
        assert segment.words[0].confidence == 0.95

        # レガシーメソッドが呼ばれたことを確認
        mock_instance.transcribe.assert_called_once_with(
            video_path="/test/video.mp4", model_size="large-v3", progress_callback=None
        )

    def test_transcribe_with_progress_callback(self, mock_config, mock_legacy_transcriber, legacy_result):
        """進捗コールバック付き文字起こし"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.transcribe.return_value = legacy_result
        mock_legacy_transcriber.return_value = mock_instance

        # 進捗コールバック
        progress_values = []

        def progress_callback(value):
            progress_values.append(value)

        # ゲートウェイの作成と実行
        gateway = TranscriptionGatewayAdapter(mock_config)
        gateway.transcribe(FilePath("/test/video.mp4"), progress_callback=progress_callback)

        # コールバックが渡されたことを確認
        mock_instance.transcribe.assert_called_once()
        call_args = mock_instance.transcribe.call_args
        assert call_args[1]["progress_callback"] == progress_callback

    def test_transcribe_error_handling(self, mock_config, mock_legacy_transcriber):
        """エラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.transcribe.side_effect = Exception("Transcription failed")
        mock_legacy_transcriber.return_value = mock_instance

        # ゲートウェイの作成
        gateway = TranscriptionGatewayAdapter(mock_config)

        # エラーが適切に変換されることを確認
        with pytest.raises(TranscriptionError, match="Failed to transcribe"):
            gateway.transcribe(FilePath("/test/video.mp4"))

    def test_load_cache_success(self, mock_config, mock_legacy_transcriber, legacy_result):
        """キャッシュ読み込み成功"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.get_cache_path.return_value = Path("/cache/large-v3.json")
        mock_instance.load_from_cache.return_value = legacy_result
        mock_legacy_transcriber.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = TranscriptionGatewayAdapter(mock_config)
        result = gateway.load_cache(FilePath("/test/video.mp4"), model_size="large-v3")

        # 検証
        assert result is not None
        assert isinstance(result, TranscriptionResult)
        assert result.language == "ja"
        assert len(result.segments) == 2

    def test_load_cache_not_found(self, mock_config, mock_legacy_transcriber):
        """キャッシュが見つからない場合"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.get_cache_path.return_value = Path("/cache/large-v3.json")
        mock_instance.load_from_cache.return_value = None
        mock_legacy_transcriber.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = TranscriptionGatewayAdapter(mock_config)
        result = gateway.load_cache(FilePath("/test/video.mp4"), model_size="large-v3")

        # キャッシュが見つからない場合はNone
        assert result is None

    def test_save_cache_success(self, mock_config, mock_legacy_transcriber):
        """キャッシュ保存成功"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.get_cache_path.return_value = Path("/cache/large-v3.json")
        mock_legacy_transcriber.return_value = mock_instance

        # ドメインの文字起こし結果
        domain_result = TranscriptionResult(
            id="test-id",
            language="ja",
            segments=[TranscriptionSegment(id="seg1", text="テスト", start=0.0, end=1.0, words=[], chars=[])],
            original_audio_path="/test/video.mp4",
            model_size="large-v3",
            processing_time=5.0,
        )

        # from_dictメソッドのモック
        with patch.object(LegacyResult, "from_dict") as mock_from_dict:
            mock_from_dict.return_value = Mock()

            # ゲートウェイの作成と実行
            gateway = TranscriptionGatewayAdapter(mock_config)
            gateway.save_cache(domain_result, FilePath("/test/video.mp4"), "large-v3")

            # 保存が呼ばれたことを確認
            mock_instance.save_to_cache.assert_called_once()

    def test_list_available_caches(self, mock_config, mock_legacy_transcriber):
        """利用可能なキャッシュのリスト取得"""
        # モックの設定
        mock_instance = Mock()
        cache_list = [
            {"model": "large-v3", "modified_time": 1234567890},
            {"model": "medium", "modified_time": 1234567800},
        ]
        mock_instance.get_available_caches.return_value = cache_list
        mock_legacy_transcriber.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = TranscriptionGatewayAdapter(mock_config)
        caches = gateway.list_available_caches(FilePath("/test/video.mp4"))

        # 検証
        assert len(caches) == 2
        assert caches[0]["model"] == "large-v3"

    def test_is_model_available(self, mock_config, mock_legacy_transcriber):
        """モデル利用可能性チェック"""
        # ローカルモード
        gateway = TranscriptionGatewayAdapter(mock_config)

        assert gateway.is_model_available("large-v3") is True
        assert gateway.is_model_available("tiny") is True
        assert gateway.is_model_available("invalid-model") is False

        # APIモード
        mock_config.transcription.use_api = True
        gateway_api = TranscriptionGatewayAdapter(mock_config)

        # APIモードでは常にTrue
        assert gateway_api.is_model_available("invalid-model") is True

    def test_estimate_processing_time(self, mock_config, mock_legacy_transcriber):
        """処理時間の推定"""
        gateway = TranscriptionGatewayAdapter(mock_config)

        # 60秒の動画でlarge-v3モデル
        estimate = gateway.estimate_processing_time(60.0, "large-v3")
        assert 30 < estimate < 60  # 概算で30-60秒

        # tinyモデルは高速
        estimate_tiny = gateway.estimate_processing_time(60.0, "tiny")
        assert estimate_tiny < estimate

    def test_supports_parallel_processing(self, mock_config, mock_legacy_transcriber):
        """並列処理サポートのチェック"""
        # CPUモード
        mock_instance = Mock()
        mock_instance.device = "cpu"
        mock_legacy_transcriber.return_value = mock_instance

        gateway = TranscriptionGatewayAdapter(mock_config)
        assert gateway.supports_parallel_processing() is False

        # GPUモード
        mock_instance.device = "cuda"
        assert gateway.supports_parallel_processing() is True

        # APIモード
        mock_config.transcription.use_api = True
        gateway_api = TranscriptionGatewayAdapter(mock_config)
        assert gateway_api.supports_parallel_processing() is True
