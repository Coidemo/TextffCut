"""
VideoProcessorGatewayAdapterのテスト
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adapters.gateways.video_processing.video_processor_gateway import VideoProcessorGatewayAdapter
from core.video import SilenceInfo as LegacySilenceInfo
from core.video import VideoInfo as LegacyVideoInfo
from domain.value_objects import Duration, FilePath, TimeRange
from use_cases.exceptions import AudioExtractionError, SegmentCombineError, SilenceDetectionError


class TestVideoProcessorGatewayAdapter:
    """VideoProcessorGatewayAdapterのテスト"""

    @pytest.fixture
    def gateway(self):
        """テスト用ゲートウェイ"""
        return VideoProcessorGatewayAdapter()

    @pytest.fixture
    def mock_legacy_processor(self):
        """モックレガシープロセッサー"""
        with patch("adapters.gateways.video_processing.video_processor_gateway.LegacyVideoProcessor") as mock:
            yield mock

    def test_extract_audio_segments_success(self, mock_legacy_processor):
        """音声セグメント抽出の成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.extract_audio_for_ranges.return_value = "/tmp/extracted_audio.wav"
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = VideoProcessorGatewayAdapter()
        video_path = FilePath("/test/video.mp4")
        time_ranges = [TimeRange(0.0, 10.0), TimeRange(20.0, 30.0)]

        result = gateway.extract_audio_segments(video_path, time_ranges)

        # 検証
        assert len(result) == 1
        assert isinstance(result[0], FilePath)
        assert str(result[0]) == "/tmp/extracted_audio.wav"

        # レガシーメソッドが正しく呼ばれたことを確認
        mock_instance.extract_audio_for_ranges.assert_called_once_with(
            video_path=str(video_path), time_ranges=[(0.0, 10.0), (20.0, 30.0)], output_path=None
        )

    def test_extract_audio_segments_with_output_dir(self, mock_legacy_processor):
        """出力ディレクトリ指定での音声セグメント抽出"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.extract_audio_for_ranges.return_value = "/output/extracted.wav"
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = VideoProcessorGatewayAdapter()
        video_path = FilePath("/test/video.mp4")
        time_ranges = [TimeRange(0.0, 10.0)]
        output_dir = FilePath("/output")

        result = gateway.extract_audio_segments(video_path, time_ranges, output_dir)

        # 検証
        assert len(result) == 1
        mock_instance.extract_audio_for_ranges.assert_called_once_with(
            video_path=str(video_path), time_ranges=[(0.0, 10.0)], output_path=Path("/output")
        )

    def test_extract_audio_segments_error_handling(self, mock_legacy_processor):
        """音声セグメント抽出のエラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.extract_audio_for_ranges.side_effect = Exception("Extraction failed")
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成
        gateway = VideoProcessorGatewayAdapter()
        video_path = FilePath("/test/video.mp4")
        time_ranges = [TimeRange(0.0, 10.0)]

        # エラーが適切に変換されることを確認
        with pytest.raises(AudioExtractionError, match="Failed to extract audio segments"):
            gateway.extract_audio_segments(video_path, time_ranges)

    def test_detect_silence_success(self, mock_legacy_processor):
        """無音検出の成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_silence1 = Mock(spec=LegacySilenceInfo)
        mock_silence1.start = 5.0
        mock_silence1.end = 8.0

        mock_silence2 = Mock(spec=LegacySilenceInfo)
        mock_silence2.start = 15.0
        mock_silence2.end = 18.0

        mock_instance.detect_silence_from_wav.return_value = [mock_silence1, mock_silence2]
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = VideoProcessorGatewayAdapter()
        audio_path = FilePath("/tmp/audio.wav")

        result = gateway.detect_silence(
            audio_path=audio_path, threshold=-40.0, min_silence_duration=0.5, min_segment_duration=0.5
        )

        # 検証
        assert len(result) == 2
        assert isinstance(result[0], TimeRange)
        assert result[0].start == 5.0
        assert result[0].end == 8.0
        assert result[1].start == 15.0
        assert result[1].end == 18.0

        # レガシーメソッドが正しく呼ばれたことを確認
        mock_instance.detect_silence_from_wav.assert_called_once_with(
            wav_path=str(audio_path), threshold=-40.0, min_silence_duration=0.5, min_segment_duration=0.5
        )

    def test_detect_silence_error_handling(self, mock_legacy_processor):
        """無音検出のエラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.detect_silence_from_wav.side_effect = Exception("Detection failed")
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成
        gateway = VideoProcessorGatewayAdapter()
        audio_path = FilePath("/tmp/audio.wav")

        # エラーが適切に変換されることを確認
        with pytest.raises(SilenceDetectionError, match="Failed to detect silence"):
            gateway.detect_silence(audio_path)

    def test_calculate_keep_ranges(self, mock_legacy_processor):
        """残す範囲計算のテスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance._calculate_keep_segments.return_value = [(0.0, 5.0), (8.0, 15.0), (18.0, 30.0)]
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = VideoProcessorGatewayAdapter()
        total_duration = Duration(30.0)
        silence_ranges = [TimeRange(5.0, 8.0), TimeRange(15.0, 18.0)]

        result = gateway.calculate_keep_ranges(
            total_duration=total_duration, silence_ranges=silence_ranges, padding_start=0.2, padding_end=0.2
        )

        # 検証
        assert len(result) == 3
        assert result[0].start == 0.0
        assert result[0].end == 5.0
        assert result[1].start == 8.0
        assert result[1].end == 15.0
        assert result[2].start == 18.0
        assert result[2].end == 30.0

    def test_extract_segments_success(self, mock_legacy_processor):
        """セグメント抽出の成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.extract_segment.return_value = True
        mock_legacy_processor.return_value = mock_instance

        # ファイル存在チェックとディレクトリ作成のモック
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("adapters.gateways.video_processing.video_processor_gateway.ensure_directory"),
        ):
            # ゲートウェイの作成と実行
            gateway = VideoProcessorGatewayAdapter()
            video_path = FilePath("/test/video.mp4")
            time_ranges = [TimeRange(0.0, 10.0), TimeRange(20.0, 30.0)]
            output_dir = FilePath("/output")

            # 進捗コールバックのモック
            progress_callback = Mock()

            result = gateway.extract_segments(
                video_path=video_path,
                time_ranges=time_ranges,
                output_dir=output_dir,
                progress_callback=progress_callback,
            )

            # 検証
            assert len(result) == 2
            assert str(result[0]).endswith("segment_0000.mp4")
            assert str(result[1]).endswith("segment_0001.mp4")

            # レガシーメソッドが2回呼ばれたことを確認
            assert mock_instance.extract_segment.call_count == 2

            # 進捗コールバックは内部でラッパーされるため、
            # 直接呼ばれることを確認するのは困難。
            # 代わりにextract_segmentの呼び出しを詳細に確認
            first_call = mock_instance.extract_segment.call_args_list[0]
            assert first_call[1]["start"] == 0.0
            assert first_call[1]["end"] == 10.0
            assert "progress_callback" in first_call[1]

    def test_combine_segments_success(self, mock_legacy_processor):
        """セグメント結合の成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.combine_videos.return_value = True
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = VideoProcessorGatewayAdapter()
        segment_paths = [FilePath("/tmp/seg1.mp4"), FilePath("/tmp/seg2.mp4"), FilePath("/tmp/seg3.mp4")]
        output_path = FilePath("/output/combined.mp4")

        gateway.combine_segments(segment_paths, output_path)

        # レガシーメソッドが正しく呼ばれたことを確認
        mock_instance.combine_videos.assert_called_once()
        call_args = mock_instance.combine_videos.call_args
        assert call_args[1]["segments"] == ["/tmp/seg1.mp4", "/tmp/seg2.mp4", "/tmp/seg3.mp4"]
        assert call_args[1]["output"] == "/output/combined.mp4"

    def test_combine_segments_error_handling(self, mock_legacy_processor):
        """セグメント結合のエラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.combine_videos.return_value = False
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成
        gateway = VideoProcessorGatewayAdapter()
        segment_paths = [FilePath("/tmp/seg1.mp4")]
        output_path = FilePath("/output/combined.mp4")

        # エラーが適切に変換されることを確認
        with pytest.raises(SegmentCombineError, match="Failed to combine"):
            gateway.combine_segments(segment_paths, output_path)

    def test_get_video_info_success(self):
        """動画情報取得の成功テスト"""
        # モックの設定
        with patch("adapters.gateways.video_processing.video_processor_gateway.LegacyVideoInfo") as mock_info:
            mock_video_info = Mock(spec=LegacyVideoInfo)
            mock_video_info.path = "/test/video.mp4"
            mock_video_info.duration = 120.0
            mock_video_info.fps = 30.0
            mock_video_info.width = 1920
            mock_video_info.height = 1080
            mock_video_info.codec = "h264"

            mock_info.from_file.return_value = mock_video_info

            # ゲートウェイの作成と実行
            gateway = VideoProcessorGatewayAdapter()
            video_path = FilePath("/test/video.mp4")

            result = gateway.get_video_info(video_path)

            # 検証
            assert result["path"] == "/test/video.mp4"
            assert result["duration"] == 120.0
            assert result["fps"] == 30.0
            assert result["width"] == 1920
            assert result["height"] == 1080
            assert result["codec"] == "h264"

    def test_get_video_info_error_handling(self):
        """動画情報取得のエラーハンドリング"""
        # モックの設定
        with patch("adapters.gateways.video_processing.video_processor_gateway.LegacyVideoInfo") as mock_info:
            mock_info.from_file.side_effect = Exception("Failed to read video")

            # ゲートウェイの作成と実行
            gateway = VideoProcessorGatewayAdapter()
            video_path = FilePath("/test/video.mp4")

            result = gateway.get_video_info(video_path)

            # エラー時も最小限の情報を返すことを確認
            assert result["path"] == "/test/video.mp4"
            assert "error" in result
            assert "Failed to read video" in result["error"]

    def test_create_thumbnail_success(self):
        """サムネイル作成の成功テスト"""
        # subprocessとensure_directoryのモック
        with (
            patch("subprocess.run") as mock_run,
            patch("adapters.gateways.video_processing.video_processor_gateway.ensure_directory"),
        ):
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            # ゲートウェイの作成と実行
            gateway = VideoProcessorGatewayAdapter()
            video_path = FilePath("/test/video.mp4")
            output_path = FilePath("/output/thumb.jpg")

            gateway.create_thumbnail(video_path=video_path, time=10.0, output_path=output_path, width=320, height=240)

            # FFmpegコマンドが正しく構築されたことを確認
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "ffmpeg"
            assert "-ss" in cmd
            assert "10.0" in cmd
            assert "-vf" in cmd
            assert "scale=w=320:h=240" in cmd

    def test_create_thumbnail_error_handling(self):
        """サムネイル作成のエラーハンドリング"""
        # subprocessとensure_directoryのモック
        with (
            patch("subprocess.run") as mock_run,
            patch("adapters.gateways.video_processing.video_processor_gateway.ensure_directory"),
        ):
            from subprocess import CalledProcessError

            mock_run.side_effect = CalledProcessError(1, "ffmpeg", stderr="FFmpeg error")

            # ゲートウェイの作成
            gateway = VideoProcessorGatewayAdapter()
            video_path = FilePath("/test/video.mp4")
            output_path = FilePath("/output/thumb.jpg")

            # エラーが発生することを確認
            with pytest.raises(RuntimeError, match="Failed to create thumbnail"):
                gateway.create_thumbnail(video_path=video_path, time=10.0, output_path=output_path)
