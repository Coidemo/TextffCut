"""
DetectSilenceUseCaseの単体テスト

無音検出ユースケースのロジックを網羅的にテストします。
"""

import pytest
import tempfile
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from dataclasses import dataclass

from use_cases.video.detect_silence import (
    DetectSilenceUseCase,
    DetectSilenceRequest,
    DetectSilenceResponse,
    SilenceInfo
)
from use_cases.exceptions import ValidationError, ExecutionError
from domain.value_objects.time_range import TimeRange


class TestSilenceInfo:
    """SilenceInfoデータクラスのテスト"""

    def test_silence_info_creation(self):
        """SilenceInfoが正しく作成できることを確認"""
        silence = SilenceInfo(
            start=10.0,
            end=20.0,
            duration=10.0
        )
        assert silence.start == 10.0
        assert silence.end == 20.0
        assert silence.duration == 10.0

    def test_silence_info_to_time_range(self):
        """TimeRangeへの変換を確認"""
        silence = SilenceInfo(start=5.0, end=15.0, duration=10.0)
        time_range = TimeRange(start=silence.start, end=silence.end)
        assert time_range.start == 5.0
        assert time_range.end == 15.0
        assert time_range.duration == 10.0


class TestDetectSilenceRequest:
    """DetectSilenceRequestのテスト"""

    def test_valid_request_creation(self):
        """有効なリクエストが作成できることを確認"""
        time_ranges = [
            TimeRange(start=0.0, end=10.0),
            TimeRange(start=20.0, end=30.0)
        ]
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=time_ranges,
            threshold_db=-35.0,
            min_silence_duration=0.5,
            padding=0.1
        )
        assert request.video_path == Path("/path/to/video.mp4")
        assert len(request.time_ranges) == 2
        assert request.threshold_db == -35.0
        assert request.min_silence_duration == 0.5
        assert request.padding == 0.1

    def test_request_with_defaults(self):
        """デフォルト値が正しく設定されることを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        assert request.threshold_db == -40.0
        assert request.min_silence_duration == 0.3
        assert request.padding == 0.0


class TestDetectSilenceUseCase:
    """DetectSilenceUseCaseのテスト"""

    @pytest.fixture
    def mock_video_gateway(self):
        """モックVideoGatewayを作成"""
        gateway = Mock()
        gateway.extract_audio_segment = Mock()
        gateway.detect_silence_in_audio = Mock()
        return gateway

    @pytest.fixture
    def mock_file_gateway(self):
        """モックFileGatewayを作成"""
        gateway = Mock()
        gateway.create_temp_directory = Mock(return_value=Path("/tmp/test"))
        gateway.delete_directory = Mock()
        gateway.exists = Mock(return_value=True)
        return gateway

    @pytest.fixture
    def use_case(self, mock_video_gateway, mock_file_gateway):
        """テスト用のUseCaseインスタンスを作成"""
        return DetectSilenceUseCase(
            video_gateway=mock_video_gateway,
            file_gateway=mock_file_gateway
        )

    @pytest.fixture
    def sample_silence_data(self):
        """サンプルの無音検出結果を作成"""
        return [
            {"start": 2.0, "end": 3.5, "duration": 1.5},
            {"start": 7.0, "end": 8.0, "duration": 1.0}
        ]

    def test_validate_request_with_valid_input(self, use_case):
        """有効な入力でバリデーションが成功することを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        # エラーが発生しないことを確認
        use_case.validate_request(request)

    def test_validate_request_with_empty_time_ranges(self, use_case):
        """空の時間範囲でエラーになることを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[]
        )
        with pytest.raises(ValidationError, match="Time ranges cannot be empty"):
            use_case.validate_request(request)

    def test_validate_request_with_invalid_threshold(self, use_case):
        """無効な閾値でエラーになることを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)],
            threshold_db=10.0  # 正の値は無効
        )
        with pytest.raises(ValidationError, match="Threshold must be negative"):
            use_case.validate_request(request)

    def test_validate_request_with_invalid_duration(self, use_case):
        """無効な最小無音時間でエラーになることを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)],
            min_silence_duration=-0.1
        )
        with pytest.raises(ValidationError, match="Min silence duration must be positive"):
            use_case.validate_request(request)

    def test_validate_request_with_negative_padding(self, use_case):
        """負のパディングでエラーになることを確認"""
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)],
            padding=-0.1
        )
        with pytest.raises(ValidationError, match="Padding cannot be negative"):
            use_case.validate_request(request)

    def test_execute_successful_detection(self, use_case, mock_video_gateway, mock_file_gateway, sample_silence_data):
        """正常な無音検出処理を確認"""
        # モックの設定
        mock_video_gateway.detect_silence_in_audio.return_value = sample_silence_data
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        # レスポンスの確認
        assert response.success is True
        assert len(response.silences) == 2
        assert response.silences[0].start == 2.0
        assert response.silences[0].end == 3.5
        assert response.silences[1].start == 7.0
        assert response.silences[1].end == 8.0
        assert response.error is None
        
        # 有音範囲の確認
        assert len(response.sound_ranges) == 3
        assert response.sound_ranges[0] == TimeRange(start=0.0, end=2.0)
        assert response.sound_ranges[1] == TimeRange(start=3.5, end=7.0)
        assert response.sound_ranges[2] == TimeRange(start=8.0, end=10.0)

    def test_execute_with_multiple_time_ranges(self, use_case, mock_video_gateway, mock_file_gateway):
        """複数の時間範囲での無音検出を確認"""
        # 各範囲で異なる無音パターンを返す
        silence_data1 = [{"start": 2.0, "end": 3.0, "duration": 1.0}]
        silence_data2 = [{"start": 25.0, "end": 27.0, "duration": 2.0}]
        mock_video_gateway.detect_silence_in_audio.side_effect = [silence_data1, silence_data2]
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[
                TimeRange(start=0.0, end=10.0),
                TimeRange(start=20.0, end=30.0)
            ]
        )
        
        response = use_case.execute(request)
        
        # 両方の範囲の無音が統合されていることを確認
        assert response.success is True
        assert len(response.silences) == 2
        assert response.silences[0].start == 2.0
        assert response.silences[1].start == 25.0
        
        # extract_audio_segmentが2回呼ばれたことを確認
        assert mock_video_gateway.extract_audio_segment.call_count == 2

    def test_execute_with_no_silence_detected(self, use_case, mock_video_gateway, mock_file_gateway):
        """無音が検出されない場合の処理を確認"""
        mock_video_gateway.detect_silence_in_audio.return_value = []
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is True
        assert len(response.silences) == 0
        assert len(response.sound_ranges) == 1
        assert response.sound_ranges[0] == TimeRange(start=0.0, end=10.0)

    def test_execute_with_full_silence(self, use_case, mock_video_gateway, mock_file_gateway):
        """全体が無音の場合の処理を確認"""
        silence_data = [{"start": 0.0, "end": 10.0, "duration": 10.0}]
        mock_video_gateway.detect_silence_in_audio.return_value = silence_data
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is True
        assert len(response.silences) == 1
        assert len(response.sound_ranges) == 0

    def test_execute_with_padding(self, use_case, mock_video_gateway, mock_file_gateway):
        """パディング付きの無音検出を確認"""
        silence_data = [{"start": 5.0, "end": 6.0, "duration": 1.0}]
        mock_video_gateway.detect_silence_in_audio.return_value = silence_data
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)],
            padding=0.5
        )
        
        response = use_case.execute(request)
        
        # パディングが適用されていることを確認
        assert response.success is True
        assert len(response.sound_ranges) == 2
        # 前半: 0.0 - (5.0-0.5) = 0.0 - 4.5
        assert response.sound_ranges[0].start == 0.0
        assert response.sound_ranges[0].end == 4.5
        # 後半: (6.0+0.5) - 10.0 = 6.5 - 10.0
        assert response.sound_ranges[1].start == 6.5
        assert response.sound_ranges[1].end == 10.0

    def test_execute_with_extraction_error(self, use_case, mock_video_gateway, mock_file_gateway):
        """音声抽出エラーが適切に処理されることを確認"""
        mock_video_gateway.extract_audio_segment.side_effect = Exception("Extraction failed")
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is False
        assert response.silences == []
        assert response.sound_ranges == []
        assert "Extraction failed" in response.error

    def test_execute_with_detection_error(self, use_case, mock_video_gateway, mock_file_gateway):
        """無音検出エラーが適切に処理されることを確認"""
        mock_video_gateway.detect_silence_in_audio.side_effect = Exception("Detection failed")
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is False
        assert "Detection failed" in response.error

    def test_cleanup_on_success(self, use_case, mock_video_gateway, mock_file_gateway):
        """正常終了時にクリーンアップが実行されることを確認"""
        mock_video_gateway.detect_silence_in_audio.return_value = []
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is True
        # 一時ディレクトリが削除されたことを確認
        mock_file_gateway.delete_directory.assert_called_once()

    def test_cleanup_on_error(self, use_case, mock_video_gateway, mock_file_gateway):
        """エラー時にもクリーンアップが実行されることを確認"""
        mock_video_gateway.extract_audio_segment.side_effect = Exception("Error")
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        assert response.success is False
        # エラー時も一時ディレクトリが削除されたことを確認
        mock_file_gateway.delete_directory.assert_called_once()

    def test_extract_audio_segments_method(self, use_case, mock_video_gateway, mock_file_gateway):
        """_extract_audio_segmentsメソッドの動作を確認"""
        temp_dir = Path("/tmp/test")
        time_ranges = [
            TimeRange(start=0.0, end=10.0),
            TimeRange(start=20.0, end=30.0)
        ]
        
        audio_files = use_case._extract_audio_segments(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=time_ranges,
            temp_dir=temp_dir
        )
        
        # 正しい数のファイルが返されることを確認
        assert len(audio_files) == 2
        assert audio_files[0] == temp_dir / "audio_0.wav"
        assert audio_files[1] == temp_dir / "audio_1.wav"
        
        # extract_audio_segmentが正しく呼ばれたことを確認
        assert mock_video_gateway.extract_audio_segment.call_count == 2

    def test_metadata_in_response(self, use_case, mock_video_gateway, mock_file_gateway, sample_silence_data):
        """レスポンスにメタデータが含まれることを確認"""
        mock_video_gateway.detect_silence_in_audio.return_value = sample_silence_data
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)],
            threshold_db=-30.0,
            min_silence_duration=0.5
        )
        
        response = use_case.execute(request)
        
        assert response.success is True
        assert response.metadata["video_path"] == str(request.video_path)
        assert response.metadata["threshold_db"] == -30.0
        assert response.metadata["min_silence_duration"] == 0.5
        assert response.metadata["total_duration"] == 10.0
        assert response.metadata["silence_count"] == 2
        assert response.metadata["sound_ranges_count"] == 3

    def test_overlapping_silence_ranges(self, use_case, mock_video_gateway, mock_file_gateway):
        """重複する無音範囲が正しく処理されることを確認"""
        # 重複する無音データ
        silence_data = [
            {"start": 2.0, "end": 5.0, "duration": 3.0},
            {"start": 4.0, "end": 7.0, "duration": 3.0},  # 重複
            {"start": 8.0, "end": 9.0, "duration": 1.0}
        ]
        mock_video_gateway.detect_silence_in_audio.return_value = silence_data
        
        request = DetectSilenceRequest(
            video_path=Path("/path/to/video.mp4"),
            time_ranges=[TimeRange(start=0.0, end=10.0)]
        )
        
        response = use_case.execute(request)
        
        # 重複が適切に処理されていることを確認
        assert response.success is True
        # 有音範囲が正しく計算されていることを確認
        assert len(response.sound_ranges) == 3
        assert response.sound_ranges[0] == TimeRange(start=0.0, end=2.0)
        assert response.sound_ranges[1] == TimeRange(start=7.0, end=8.0)
        assert response.sound_ranges[2] == TimeRange(start=9.0, end=10.0)