"""
Phase 4 アダプター層の統合テスト

全てのゲートウェイが適切に連携して動作することを確認します。
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adapters.gateways.export.fcpxml_export_gateway import FCPXMLExportGatewayAdapter
from adapters.gateways.export.srt_export_gateway import SRTExportGatewayAdapter
from adapters.gateways.file.file_gateway import FileGatewayAdapter
from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter
from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from adapters.gateways.video_processing.video_processor_gateway import VideoProcessorGatewayAdapter
from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.value_objects import Duration, FilePath, TimeRange
from use_cases.interfaces import ExportSegment


class TestPhase4Integration:
    """Phase 4統合テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def file_gateway(self):
        """ファイルゲートウェイ"""
        return FileGatewayAdapter()

    def test_file_operations_integration(self, file_gateway, temp_dir):
        """ファイル操作の統合テスト"""
        # テストファイルのパスを設定
        test_file = FilePath(temp_dir / "test.txt")
        json_file = FilePath(temp_dir / "test.json")

        # テキストファイルの書き込みと読み込み
        test_content = "これは統合テストです"
        file_gateway.write_text(test_file, test_content)

        assert file_gateway.exists(test_file)
        read_content = file_gateway.read_text(test_file)
        assert read_content == test_content

        # JSONファイルの書き込みと読み込み
        test_data = {"name": "TextffCut", "version": "1.0"}
        file_gateway.write_json(json_file, test_data)

        read_data = file_gateway.read_json(json_file)
        assert read_data == test_data

        # ディレクトリ操作
        sub_dir = FilePath(temp_dir / "subdir")
        file_gateway.create_directory(sub_dir)
        assert file_gateway.exists(sub_dir)
        assert file_gateway.is_directory(sub_dir)

        # ファイル一覧
        files = file_gateway.list_files(FilePath(temp_dir))
        assert len(files) >= 2  # test.txt と test.json

    def test_transcription_and_text_processing_integration(self):
        """文字起こしとテキスト処理の統合テスト"""
        # モックの設定
        with (
            patch("core.transcription.Transcriber") as mock_transcriber,
            patch(
                "adapters.gateways.text_processing.text_processor_gateway.LegacyTextProcessor"
            ) as mock_text_processor,
        ):

            # 文字起こしゲートウェイの設定
            mock_transcriber_instance = Mock()
            mock_transcriber.return_value = mock_transcriber_instance

            # TranscriptionGatewayAdapterのインスタンス化前にモックを設定
            transcription_gateway = TranscriptionGatewayAdapter()

            # モック文字起こし結果
            mock_result = {
                "language": "ja",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "text": "これはテストです",
                        "words": [{"word": "これは", "start": 0.0, "end": 1.0, "confidence": 0.95}],
                    }
                ],
                "original_audio_path": "/test/audio.wav",
                "model_size": "large-v3",
                "processing_time": 5.0,
            }
            mock_transcriber_instance.transcribe.return_value = mock_result

            # 文字起こし実行
            audio_path = FilePath("/test/audio.wav")
            transcription_result = transcription_gateway.transcribe(audio_path)

            assert transcription_result.language == "ja"
            assert len(transcription_result.segments) == 1
            assert transcription_result.segments[0].text == "これはテストです"

            # テキスト処理ゲートウェイの設定
            text_gateway = TextProcessorGatewayAdapter()
            mock_text_instance = Mock()
            mock_text_processor.return_value = mock_text_instance

            # 差分検出の設定
            from core.text_processor import TextDifference as LegacyTextDifference
            from core.text_processor import TextPosition as LegacyTextPosition

            legacy_diff = LegacyTextDifference(
                original_text="これはテストです",
                edited_text="これはテスト",
                common_positions=[LegacyTextPosition(start=0, end=6, text="これはテスト")],
                added_chars=set(),
                added_positions=None,
            )
            mock_text_instance.find_differences.return_value = legacy_diff

            # 差分検出実行
            differences = text_gateway.find_differences("これはテストです", "これはテスト")

            assert differences.original_text == "これはテストです"
            assert differences.edited_text == "これはテスト"
            assert len(differences.differences) > 0

    def test_video_processing_integration(self):
        """動画処理の統合テスト"""
        with patch("adapters.gateways.video_processing.video_processor_gateway.LegacyVideoProcessor") as mock_processor:
            # ゲートウェイの設定
            video_gateway = VideoProcessorGatewayAdapter()
            mock_instance = Mock()
            mock_processor.return_value = mock_instance

            # 音声抽出のモック
            mock_instance.extract_audio_for_ranges.return_value = "/tmp/extracted.wav"

            video_path = FilePath("/test/video.mp4")
            time_ranges = [TimeRange(0.0, 10.0), TimeRange(20.0, 30.0)]

            audio_paths = video_gateway.extract_audio_segments(video_path, time_ranges)
            assert len(audio_paths) == 1
            # FilePathオブジェクトであることを確認
            assert isinstance(audio_paths[0], FilePath)

            # 無音検出のモック
            from core.video import SilenceInfo as LegacySilenceInfo

            mock_silence1 = Mock(spec=LegacySilenceInfo)
            mock_silence1.start = 5.0
            mock_silence1.end = 8.0

            mock_instance.detect_silence_from_wav.return_value = [mock_silence1]

            silence_ranges = video_gateway.detect_silence(audio_paths[0])
            assert len(silence_ranges) == 1
            assert silence_ranges[0].start == 5.0
            assert silence_ranges[0].end == 8.0

            # 残す範囲の計算
            mock_instance._calculate_keep_segments.return_value = [(0.0, 5.0), (8.0, 30.0)]

            keep_ranges = video_gateway.calculate_keep_ranges(Duration(30.0), silence_ranges)
            assert len(keep_ranges) == 2

    def test_export_integration(self, temp_dir):
        """エクスポート機能の統合テスト"""
        # FCPXMLエクスポートのテスト
        with patch("adapters.gateways.export.fcpxml_export_gateway.LegacyFCPXMLExporter") as mock_fcpxml:
            fcpxml_gateway = FCPXMLExportGatewayAdapter()
            mock_fcpxml_instance = Mock()
            mock_fcpxml.return_value = mock_fcpxml_instance
            mock_fcpxml_instance.export.return_value = True

            segments = [ExportSegment(video_path=FilePath("/test/video.mp4"), time_range=TimeRange(0.0, 10.0))]

            output_path = FilePath(temp_dir / "project.fcpxml")
            fcpxml_gateway.export(segments, output_path)

            # エクスポートが呼ばれたことを確認
            assert mock_fcpxml_instance.export.called

        # SRTエクスポートのテスト
        with patch("adapters.gateways.export.srt_export_gateway.LegacySRTExporter") as mock_srt:
            srt_gateway = SRTExportGatewayAdapter()
            mock_srt_instance = Mock()
            mock_srt.return_value = mock_srt_instance
            mock_srt_instance.export.return_value = True

            # テスト用文字起こし結果
            transcription = TranscriptionResult(
                id="test-id",
                language="ja",
                segments=[TranscriptionSegment(id="seg1", text="テスト字幕", start=0.0, end=2.0, words=[], chars=[])],
                original_audio_path="/test/audio.mp4",
                model_size="large-v3",
                processing_time=5.0,
            )

            srt_path = FilePath(temp_dir / "subtitles.srt")
            srt_gateway.export_from_transcription(transcription, srt_path)

            # エクスポートが呼ばれたことを確認
            mock_srt_instance.export.assert_called_once()

    def test_full_workflow_integration(self, temp_dir):
        """完全なワークフローの統合テスト"""
        # 全てのゲートウェイをモックで設定
        with (
            patch("core.transcription.Transcriber") as mock_transcriber,
            patch(
                "adapters.gateways.text_processing.text_processor_gateway.LegacyTextProcessor"
            ) as mock_text_processor,
            patch(
                "adapters.gateways.video_processing.video_processor_gateway.LegacyVideoProcessor"
            ) as mock_video_processor,
            patch("adapters.gateways.export.fcpxml_export_gateway.LegacyFCPXMLExporter") as mock_fcpxml,
        ):

            # ゲートウェイのインスタンス化
            file_gateway = FileGatewayAdapter()
            transcription_gateway = TranscriptionGatewayAdapter()
            text_gateway = TextProcessorGatewayAdapter()
            video_gateway = VideoProcessorGatewayAdapter()
            fcpxml_gateway = FCPXMLExportGatewayAdapter()

            # モックインスタンスの設定
            mock_transcriber_instance = Mock()
            mock_transcriber.return_value = mock_transcriber_instance

            mock_text_instance = Mock()
            mock_text_processor.return_value = mock_text_instance

            mock_video_instance = Mock()
            mock_video_processor.return_value = mock_video_instance

            mock_fcpxml_instance = Mock()
            mock_fcpxml.return_value = mock_fcpxml_instance

            # ワークフローのシミュレーション
            # 1. 設定ファイルの作成
            config_path = FilePath(temp_dir / "config.json")
            config_data = {"project_name": "Integration Test", "fps": 30.0, "silence_threshold": -35.0}
            file_gateway.write_json(config_path, config_data)

            # 2. 文字起こし
            mock_result = {
                "language": "ja",
                "segments": [
                    {"start": 0.0, "end": 30.0, "text": "これは統合テストの完全なワークフローです", "words": []}
                ],
                "original_audio_path": "/test/video.mp4",
                "model_size": "large-v3",
                "processing_time": 10.0,
            }
            mock_transcriber_instance.transcribe.return_value = mock_result

            video_path = FilePath("/test/video.mp4")
            transcription_result = transcription_gateway.transcribe(video_path)

            # 3. テキスト処理（差分なしと仮定）
            from core.text_processor import TextDifference as LegacyTextDifference
            from core.text_processor import TextPosition as LegacyTextPosition

            legacy_diff = LegacyTextDifference(
                original_text=transcription_result.full_text,
                edited_text=transcription_result.full_text,
                common_positions=[
                    LegacyTextPosition(
                        start=0, end=len(transcription_result.full_text), text=transcription_result.full_text
                    )
                ],
                added_chars=set(),
                added_positions=None,
            )
            mock_text_instance.find_differences.return_value = legacy_diff

            differences = text_gateway.find_differences(transcription_result.full_text, transcription_result.full_text)

            # 4. 動画処理
            mock_video_instance.extract_audio_for_ranges.return_value = "/tmp/full_audio.wav"
            mock_video_instance.detect_silence_from_wav.return_value = []  # 無音なし

            time_ranges = [TimeRange(0.0, 30.0)]
            audio_paths = video_gateway.extract_audio_segments(video_path, time_ranges)
            silence_ranges = video_gateway.detect_silence(audio_paths[0])

            # 5. エクスポート
            mock_fcpxml_instance.export.return_value = True

            segments = [ExportSegment(video_path=video_path, time_range=TimeRange(0.0, 30.0))]

            output_path = FilePath(temp_dir / "final_project.fcpxml")
            fcpxml_gateway.export(
                segments, output_path, project_name=config_data["project_name"], fps=config_data["fps"]
            )

            # 全ての処理が実行されたことを確認
            mock_transcriber_instance.transcribe.assert_called_once()
            mock_text_instance.find_differences.assert_called_once()
            mock_video_instance.extract_audio_for_ranges.assert_called_once()
            mock_fcpxml_instance.export.assert_called_once()

            # 設定ファイルが存在することを確認
            assert file_gateway.exists(config_path)
            loaded_config = file_gateway.read_json(config_path)
            assert loaded_config["project_name"] == "Integration Test"
