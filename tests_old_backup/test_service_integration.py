#!/usr/bin/env python3
"""
サービス層と実装層の統合テスト

パラメータ不一致やメソッド呼び出しの問題を検出します。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import config  # noqa: E402
from core.models import TranscriptionSegmentV2  # noqa: E402
from services.export_service import ExportService  # noqa: E402
from services.transcription_service import TranscriptionService  # noqa: E402
from services.video_processing_service import VideoProcessingService  # noqa: E402


class TestServiceIntegration(unittest.TestCase):
    """サービス層の統合テスト"""

    def setUp(self):
        """テストのセットアップ"""
        self.config = config
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テストのクリーンアップ"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_video_processing_service_remove_silence_params(self):
        """VideoProcessingService.remove_silence()のパラメータテスト"""
        print("\n=== VideoProcessingService.remove_silence()パラメータテスト ===")

        service = VideoProcessingService(self.config)

        # VideoProcessor.remove_silence_newをモック
        with patch.object(service.video_processor, "remove_silence_new") as mock_method:
            mock_method.return_value = [(0.0, 5.0), (10.0, 15.0)]

            # テスト用のセグメント
            segments = [
                TranscriptionSegmentV2(id=0, start=0.0, end=10.0, text="test", words=[]),
                TranscriptionSegmentV2(id=1, start=10.0, end=20.0, text="test2", words=[]),
            ]

            # サービスメソッドを呼び出し
            service.remove_silence(
                video_path="/tmp/test.mp4",
                segments=segments,
                threshold=-35.0,
                min_silence_duration=0.3,
                pad_start=0.1,
                pad_end=0.2,
                min_segment_duration=0.5,
            )

            # remove_silence_newが正しいパラメータで呼ばれたか確認
            mock_method.assert_called_once()
            call_args = mock_method.call_args[1]

            # パラメータ名の確認
            self.assertIn("input_path", call_args)
            self.assertIn("noise_threshold", call_args)
            self.assertIn("padding_start", call_args)
            self.assertIn("padding_end", call_args)
            self.assertIn("output_dir", call_args)

            # 値の確認
            self.assertEqual(call_args["input_path"], "/tmp/test.mp4")
            self.assertEqual(call_args["noise_threshold"], -35.0)
            self.assertEqual(call_args["padding_start"], 0.1)
            self.assertEqual(call_args["padding_end"], 0.2)

            print("✓ パラメータマッピング: OK")

    def test_video_processing_service_extract_segments_params(self):
        """VideoProcessingService.extract_segments()のパラメータテスト"""
        print("\n=== VideoProcessingService.extract_segments()パラメータテスト ===")

        service = VideoProcessingService(self.config)

        # VideoProcessor.extract_segmentをモック
        with patch.object(service.video_processor, "extract_segment") as mock_method:
            mock_method.return_value = True

            # テスト用のセグメント
            segments = [TranscriptionSegmentV2(id=0, start=0.0, end=5.0, text="test", words=[])]

            # サービスメソッドを呼び出し
            with patch("pathlib.Path.exists", return_value=True):
                service.extract_segments(video_path="/tmp/test.mp4", segments=segments, output_dir=self.temp_dir)

            # extract_segmentが正しいパラメータで呼ばれたか確認
            mock_method.assert_called_once()
            call_args = mock_method.call_args[1]

            # パラメータ名の確認
            self.assertIn("input_path", call_args)
            self.assertIn("start", call_args)
            self.assertIn("end", call_args)
            self.assertIn("output_path", call_args)

            # 旧パラメータ名が使われていないことを確認
            self.assertNotIn("start_time", call_args)
            self.assertNotIn("end_time", call_args)

            print("✓ パラメータマッピング: OK")

    def test_video_processing_service_merge_videos_method(self):
        """VideoProcessingService.merge_videos()のメソッド名テスト"""
        print("\n=== VideoProcessingService.merge_videos()メソッド名テスト ===")

        service = VideoProcessingService(self.config)

        # VideoProcessor.combine_videosをモック
        with patch.object(service.video_processor, "combine_videos") as mock_method:
            mock_method.return_value = True

            # 一時ファイルを作成
            video_files = []
            for i in range(2):
                temp_file = os.path.join(self.temp_dir, f"test{i}.mp4")
                Path(temp_file).touch()
                video_files.append(temp_file)

            # サービスメソッドを呼び出し
            with patch("pathlib.Path.exists", return_value=True):
                service.merge_videos(video_files=video_files, output_path=os.path.join(self.temp_dir, "output.mp4"))

            # combine_videosが呼ばれたことを確認
            mock_method.assert_called_once()

            print("✓ メソッド名: OK (combine_videos)")

    def test_transcription_service_params(self):
        """TranscriptionService.execute()のパラメータテスト"""
        print("\n=== TranscriptionService.execute()パラメータテスト ===")

        service = TranscriptionService(self.config)

        # Transcriber.transcribeをモック
        mock_result = MagicMock()
        mock_result.segments = []
        mock_result.to_dict.return_value = {"segments": []}

        # 検証をスキップするためにモック
        with patch.object(service, "validate_file_exists") as mock_validate:
            mock_validate.return_value = Path("/tmp/test.mp4")

            with patch.object(service, "_create_transcriber") as mock_create:
                mock_transcriber = MagicMock()
                mock_transcriber.transcribe.return_value = mock_result
                mock_create.return_value = mock_transcriber

                # サービスメソッドを呼び出し
                service.execute(
                    video_path="/tmp/test.mp4", model_size="base", language="ja"  # このパラメータは無視されるべき
                )

                # transcribeが呼ばれた際のパラメータを確認
                mock_transcriber.transcribe.assert_called_once()
                call_args = mock_transcriber.transcribe.call_args[1]

                # languageパラメータが渡されていないことを確認
                self.assertNotIn("language", call_args)

                print("✓ パラメータフィルタリング: OK")

    def test_export_service_fcpxml_params(self):
        """ExportService.export_fcpxml()のパラメータテスト"""
        print("\n=== ExportService.export_fcpxml()パラメータテスト ===")

        service = ExportService(self.config)

        # FCPXMLExporter.exportをモック
        with patch.object(service.fcpxml_exporter, "export") as mock_method:

            # テスト用のセグメント
            segments = [TranscriptionSegmentV2(id=0, start=0.0, end=5.0, text="test", words=[])]

            # サービスメソッドを呼び出し
            service.export_fcpxml(
                segments=segments,
                video_path="/tmp/test.mp4",
                output_path=os.path.join(self.temp_dir, "test.fcpxml"),
                project_name="Test Project",
                event_name="Test Event",
            )

            # exportが正しいパラメータで呼ばれたか確認
            mock_method.assert_called_once()
            call_args = mock_method.call_args[1]

            # 期待されるパラメータのみが渡されていることを確認
            self.assertIn("segments", call_args)
            self.assertIn("output_path", call_args)
            self.assertIn("project_name", call_args)

            # 不要なパラメータが渡されていないことを確認
            self.assertNotIn("video_path", call_args)
            self.assertNotIn("event_name", call_args)
            self.assertNotIn("video_info", call_args)

            print("✓ パラメータフィルタリング: OK")

    def test_export_service_xmeml_params(self):
        """ExportService.export_xmeml()のパラメータテスト"""
        print("\n=== ExportService.export_xmeml()パラメータテスト ===")

        service = ExportService(self.config)

        # XMEMLExporter.exportをモック
        with patch.object(service.xmeml_exporter, "export") as mock_method:

            # テスト用のセグメント
            segments = [TranscriptionSegmentV2(id=0, start=0.0, end=5.0, text="test", words=[])]

            # サービスメソッドを呼び出し
            service.export_xmeml(
                segments=segments,
                video_path="/tmp/test.mp4",
                output_path=os.path.join(self.temp_dir, "test.xml"),
                sequence_name="Test Sequence",
            )

            # exportが正しいパラメータで呼ばれたか確認
            mock_method.assert_called_once()
            call_args = mock_method.call_args[1]

            # 期待されるパラメータのみが渡されていることを確認
            self.assertIn("segments", call_args)
            self.assertIn("output_path", call_args)
            self.assertIn("project_name", call_args)

            # project_nameにsequence_nameが渡されていることを確認
            self.assertEqual(call_args["project_name"], "Test Sequence")

            # 不要なパラメータが渡されていないことを確認
            self.assertNotIn("video_path", call_args)
            self.assertNotIn("sequence_name", call_args)
            self.assertNotIn("video_info", call_args)

            print("✓ パラメータマッピング: OK")


def run_service_integration_tests():
    """サービス統合テストを実行"""
    print("=" * 60)
    print("サービス層統合テスト")
    print("=" * 60)

    # テストスイートを作成
    suite = unittest.TestLoader().loadTestsFromTestCase(TestServiceIntegration)

    # テストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    print(f"実行テスト数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ すべてのテストが成功しました！")
        print("サービス層と実装層の統合は正しく動作しています。")
    else:
        print("\n❌ 一部のテストが失敗しました。")
        print("上記のエラーを確認して修正してください。")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_service_integration_tests()
    sys.exit(0 if success else 1)
