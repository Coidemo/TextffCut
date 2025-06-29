"""
動画処理ユースケースのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock, call, patch
from pathlib import Path

from domain.value_objects import FilePath, TimeRange, Duration
from use_cases.video import (
    DetectSilenceUseCase,
    DetectSilenceRequest,
    ExtractVideoSegmentsUseCase,
    ExtractSegmentsRequest,
)
from use_cases.exceptions import (
    VideoProcessingError,
    AudioExtractionError,
    SegmentCombineError,
)


class TestDetectSilenceUseCase:
    """DetectSilenceUseCaseのテスト"""
    
    @pytest.fixture
    def mock_video_gateway(self):
        """モック動画ゲートウェイ"""
        gateway = Mock()
        gateway.extract_audio_segments.return_value = [
            FilePath("/temp/audio1.wav"),
            FilePath("/temp/audio2.wav")
        ]
        gateway.detect_silence.return_value = [
            TimeRange(0.5, 1.5),  # 1秒の無音
            TimeRange(3.0, 4.0)   # 1秒の無音
        ]
        gateway.calculate_keep_ranges.return_value = [
            TimeRange(0.0, 0.4),
            TimeRange(1.6, 2.9),
            TimeRange(4.1, 5.0)
        ]
        return gateway
    
    @pytest.fixture
    def mock_file_gateway(self):
        """モックファイルゲートウェイ"""
        gateway = Mock()
        gateway.create_temp_directory.return_value = FilePath("/temp/silence_detection_123")
        gateway.exists.return_value = True
        return gateway
    
    @pytest.fixture
    def time_ranges(self):
        """テスト用時間範囲"""
        return [
            TimeRange(0.0, 5.0),
            TimeRange(10.0, 15.0)
        ]
    
    def test_successful_silence_detection(self, mock_video_gateway, mock_file_gateway, time_ranges):
        """正常な無音検出"""
        # Arrange
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            # Act
            response = use_case(request)
        
        # Assert
        assert len(response.silence_ranges) == 4  # 各セグメントで2つずつ
        assert len(response.keep_ranges) == 3
        assert response.total_duration.seconds == 10.0  # 5 + 5
        assert response.silence_duration.seconds == 4.0  # 2 + 2
        assert response.keep_duration.seconds == pytest.approx(2.6)  # 0.4 + 1.3 + 0.9
        assert response.silence_ratio == pytest.approx(0.4)
        assert response.compression_ratio == pytest.approx(0.26)
    
    def test_with_progress_callback(self, mock_video_gateway, mock_file_gateway, time_ranges):
        """進捗コールバック付き"""
        # Arrange
        progress_values = []
        def progress_callback(value):
            progress_values.append(value)
        
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            progress_callback=progress_callback
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            # Act
            use_case(request)
        
        # Assert
        assert len(progress_values) > 0
        assert progress_values[0] == 0.1  # 開始時
        assert progress_values[-1] == 1.0  # 終了時
    
    def test_file_not_found(self, mock_video_gateway, mock_file_gateway, time_ranges):
        """ファイルが存在しない場合"""
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/nonexistent.mp4"),
            time_ranges=time_ranges
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: False)):
            with pytest.raises(VideoProcessingError, match="Video file not found"):
                use_case(request)
    
    def test_no_time_ranges(self, mock_video_gateway, mock_file_gateway):
        """時間範囲が空の場合"""
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=[]
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with pytest.raises(VideoProcessingError, match="No time ranges provided"):
                use_case(request)
    
    def test_invalid_threshold(self, mock_video_gateway, mock_file_gateway, time_ranges):
        """無効な閾値"""
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            threshold=-70.0  # 範囲外
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with pytest.raises(VideoProcessingError, match="Threshold must be between"):
                use_case(request)
    
    def test_cleanup_on_error(self, mock_video_gateway, mock_file_gateway, time_ranges):
        """エラー時のクリーンアップ"""
        # Arrange
        mock_video_gateway.detect_silence.side_effect = Exception("Detection failed")
        
        use_case = DetectSilenceUseCase(mock_video_gateway, mock_file_gateway)
        request = DetectSilenceRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            # Act & Assert
            with pytest.raises(VideoProcessingError):
                use_case(request)


class TestExtractVideoSegmentsUseCase:
    """ExtractVideoSegmentsUseCaseのテスト"""
    
    @pytest.fixture
    def mock_video_gateway(self):
        """モック動画ゲートウェイ"""
        gateway = Mock()
        gateway.get_video_info.return_value = {
            'duration': 60.0,
            'fps': 30.0,
            'width': 1920,
            'height': 1080
        }
        gateway.extract_segments.return_value = [
            FilePath("/temp/segment1.mp4"),
            FilePath("/temp/segment2.mp4")
        ]
        return gateway
    
    @pytest.fixture
    def mock_file_gateway(self):
        """モックファイルゲートウェイ"""
        gateway = Mock()
        gateway.create_temp_directory.return_value = FilePath("/temp/segments_123")
        gateway.exists.return_value = True
        gateway.get_size.return_value = 1024 * 1024  # 1MB
        return gateway
    
    def test_successful_extraction_with_combine(self, mock_video_gateway, mock_file_gateway):
        """正常な抽出（結合あり）"""
        # Arrange
        time_ranges = [
            TimeRange(0.0, 5.0),
            TimeRange(10.0, 15.0)
        ]
        
        use_case = ExtractVideoSegmentsUseCase(mock_video_gateway, mock_file_gateway)
        request = ExtractSegmentsRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            output_path=FilePath("/output/combined.mp4"),
            combine_segments=True
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with patch.object(FilePath, 'parent', property(lambda self: Mock(exists=True))):
                # Act
                response = use_case(request)
        
        # Assert
        assert response.output_path == FilePath("/output/combined.mp4")
        assert response.segment_count == 2
        assert response.total_duration.seconds == 60.0
        assert response.output_duration.seconds == 10.0  # 5 + 5
        assert response.compression_ratio == pytest.approx(0.16666666666666666)
        assert response.total_size_bytes == 2 * 1024 * 1024  # 2MB
        
        # 結合が呼ばれたことを確認
        mock_video_gateway.combine_segments.assert_called_once()
    
    def test_single_segment_no_combine(self, mock_video_gateway, mock_file_gateway):
        """単一セグメント（結合なし）"""
        # Arrange
        time_ranges = [TimeRange(0.0, 5.0)]
        mock_video_gateway.extract_segments.return_value = [
            FilePath("/temp/segment1.mp4")
        ]
        
        use_case = ExtractVideoSegmentsUseCase(mock_video_gateway, mock_file_gateway)
        request = ExtractSegmentsRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            output_path=FilePath("/output/single.mp4")
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with patch.object(FilePath, 'parent', property(lambda self: Mock(exists=True))):
                # Act
                response = use_case(request)
        
        # Assert
        assert response.segment_count == 1
        # 結合は呼ばれない
        mock_video_gateway.combine_segments.assert_not_called()
        # 代わりにファイル移動が呼ばれる
        mock_file_gateway.move_file.assert_called_once()
    
    def test_keep_temp_files(self, mock_video_gateway, mock_file_gateway):
        """一時ファイルを保持"""
        # Arrange
        time_ranges = [
            TimeRange(0.0, 5.0),
            TimeRange(10.0, 15.0)
        ]
        
        use_case = ExtractVideoSegmentsUseCase(mock_video_gateway, mock_file_gateway)
        request = ExtractSegmentsRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            output_path=FilePath("/output/combined.mp4"),
            keep_temp_files=True
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with patch.object(FilePath, 'parent', property(lambda self: Mock(exists=True))):
                # Act
                response = use_case(request)
        
        # Assert
        assert len(response.temp_files) == 2
        # クリーンアップが呼ばれないことを確認
        mock_file_gateway.delete_file.assert_not_called()
    
    def test_invalid_output_extension(self, mock_video_gateway, mock_file_gateway):
        """無効な出力拡張子"""
        use_case = ExtractVideoSegmentsUseCase(mock_video_gateway, mock_file_gateway)
        request = ExtractSegmentsRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=[TimeRange(0.0, 5.0)],
            output_path=FilePath("/output/result.txt")  # 無効な拡張子
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with patch.object(FilePath, 'extension', property(lambda self: ".txt")):
                with pytest.raises(VideoProcessingError, match="Invalid output format"):
                    use_case(request)
    
    def test_combine_error(self, mock_video_gateway, mock_file_gateway):
        """結合エラー"""
        # Arrange
        mock_video_gateway.combine_segments.side_effect = Exception("Combine failed")
        time_ranges = [
            TimeRange(0.0, 5.0),
            TimeRange(10.0, 15.0)
        ]
        
        use_case = ExtractVideoSegmentsUseCase(mock_video_gateway, mock_file_gateway)
        request = ExtractSegmentsRequest(
            video_path=FilePath("/test/video.mp4"),
            time_ranges=time_ranges,
            output_path=FilePath("/output/combined.mp4")
        )
        
        with patch.object(FilePath, 'exists', property(lambda self: True)):
            with patch.object(FilePath, 'parent', property(lambda self: Mock(exists=True))):
                # Act & Assert
                with pytest.raises(SegmentCombineError, match="Failed to combine segments"):
                    use_case(request)