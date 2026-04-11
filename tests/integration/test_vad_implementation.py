"""
VADベース実装の統合テスト
実際のワークフローでの動作を確認
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from config import Config
from core.auto_optimizer import AutoOptimizer
from core.memory_monitor import MemoryMonitor
from core.transcription_smart_boundary import SmartBoundaryTranscriber
from worker_transcribe import main as worker_main


class TestVADImplementationIntegration(unittest.TestCase):
    """VADベース実装の統合テスト"""

    def setUp(self):
        """テストのセットアップ"""
        self.temp_dir = tempfile.mkdtemp()
        self.config = Config()
        self.config.transcription.use_api = False
        self.config.transcription.language = "ja"
        self.config.transcription.compute_type = "int8"
        self.config.transcription.model_size = "medium"

    def tearDown(self):
        """テストのクリーンアップ"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_vad_based_transcription_flow(self):
        """VADベースの文字起こしフロー全体のテスト"""
        # テスト用の設定ファイルを作成
        config_data = {
            "video_path": "/tmp/test_video.mp4",
            "model_size": "medium",
            "use_cache": False,
            "save_cache": False,
            "config": {
                "transcription": {
                    "use_api": False,
                    "language": "ja",
                    "compute_type": "int8",
                    "model_size": "medium",
                    "sample_rate": 16000,
                    "isolation_mode": "none",
                }
            },
            "task_type": "separated_mode",
        }

        config_path = os.path.join(self.temp_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # SmartBoundaryTranscriberのモック
        with (
            patch("core.transcription_smart_boundary.SmartBoundaryTranscriber") as mock_transcriber_class,
            patch("core.auto_optimizer.AutoOptimizer") as mock_optimizer_class,
            patch("core.memory_monitor.MemoryMonitor") as mock_monitor_class,
            patch("core.alignment_processor.AlignmentProcessor") as mock_alignment_class,
            patch("subprocess.run"),
            patch("config.Config") as mock_config_class,
        ):

            # Configのモック
            mock_config = MagicMock()
            mock_config.transcription.use_api = False
            mock_config.transcription.api_provider = "openai"
            mock_config.transcription.api_key = None
            mock_config.transcription.model_size = "medium"
            mock_config.transcription.language = "ja"
            mock_config.transcription.compute_type = "int8"
            mock_config.transcription.sample_rate = 16000
            mock_config.transcription.isolation_mode = "none"
            mock_config_class.return_value = mock_config

            # オプティマイザのモック
            mock_optimizer = MagicMock()
            mock_optimizer.get_optimal_params.return_value = {
                "chunk_seconds": 30,
                "align_chunk_seconds": 60,
                "max_workers": 1,
                "batch_size": 8,
                "compute_type": "int8",
            }
            mock_optimizer.diagnostic_mode = False
            mock_optimizer_class.return_value = mock_optimizer

            # メモリモニターのモック
            mock_monitor = MagicMock()
            mock_monitor.get_memory_usage.return_value = 65.0
            mock_monitor.get_average_usage.return_value = 70.0
            mock_monitor_class.return_value = mock_monitor

            # AlignmentProcessorのモック
            mock_alignment = MagicMock()
            mock_alignment.run_diagnostic.return_value = {
                "diagnostic_completed": True,
                "optimal_batch_size": 8,
                "model_memory": 30.0,
                "audio_memory": 10.0,
                "batch_memory_per_segment": 5.0,
            }
            aligned_segment = MagicMock(text="テスト", words=[{"word": "テスト", "start": 0.0, "end": 1.0}])
            mock_alignment.align.return_value = [aligned_segment]
            mock_alignment_class.return_value = mock_alignment

            # トランスクライバーのモック
            mock_transcriber = MagicMock()
            mock_result = MagicMock()
            mock_result.segments = [
                MagicMock(
                    text="テストセグメント1", start=0.0, end=10.0, words=[{"word": "テスト", "start": 0.0, "end": 1.0}]
                ),
                MagicMock(
                    text="テストセグメント2",
                    start=10.0,
                    end=20.0,
                    words=[{"word": "セグメント", "start": 10.0, "end": 11.0}],
                ),
            ]
            mock_result.language = "ja"
            mock_result.processing_time = 5.0
            mock_result.to_dict.return_value = {"segments": [], "language": "ja"}
            mock_result.validate_has_words.return_value = (True, [])
            mock_transcriber.transcribe.return_value = mock_result
            mock_transcriber_class.return_value = mock_transcriber

            # worker_transcribeを実行
            import sys

            orig_argv = sys.argv
            sys.argv = ["worker_transcribe.py", config_path]

            try:
                worker_main()
            except SystemExit as e:
                # 正常終了（exit(0)）を確認
                self.assertEqual(e.code, 0)
            finally:
                sys.argv = orig_argv

            # オプティマイザが正しく使用されたことを確認
            mock_optimizer_class.assert_called_once_with("medium")
            mock_optimizer.reset_diagnostic_mode.assert_called_once()

            # メモリモニターが使用されたことを確認
            mock_monitor_class.assert_called_once()

            # トランスクライバーが正しく初期化されたことを確認
            mock_transcriber_class.assert_called_once()
            # config is the first positional arg, optimizer and memory_monitor are keyword args
            self.assertEqual(mock_transcriber_class.call_args[1]["optimizer"], mock_optimizer)
            self.assertEqual(mock_transcriber_class.call_args[1]["memory_monitor"], mock_monitor)

            # transcribeが正しく呼ばれたことを確認
            mock_transcriber.transcribe.assert_called_once()
            call_args = mock_transcriber.transcribe.call_args
            self.assertEqual(call_args[1]["skip_alignment"], True)  # separated_modeなのでTrue

    def test_memory_based_compute_type_selection(self):
        """メモリ使用率に基づくcompute_type選択のテスト"""
        optimizer = AutoOptimizer("medium")

        # 診断フェーズを完了させる
        for i in range(3):
            optimizer.get_optimal_params(50.0 + i * 5)

        # CPU環境（torch.cuda.is_available() == False）では常にint8が返される
        test_cases = [
            (85.0, "int8"),  # 高メモリ使用率
            (75.0, "int8"),  # 中メモリ使用率 - CPU環境ではint8
            (65.0, "int8"),  # 通常使用率 - CPU環境ではint8
            (50.0, "int8"),  # 低使用率 - CPU環境ではint8
        ]

        for memory_percent, expected_compute_type in test_cases:
            params = optimizer.get_optimal_params(memory_percent)
            self.assertEqual(
                params["compute_type"],
                expected_compute_type,
                f"メモリ使用率 {memory_percent}% での compute_type が期待値と異なります",
            )

    def test_api_mode_with_alignment(self):
        """APIモードでのアライメント処理のテスト"""
        config_data = {
            "video_path": "/tmp/test_video.mp4",
            "model_size": "medium",
            "use_cache": False,
            "save_cache": False,
            "config": {
                "transcription": {
                    "use_api": True,
                    "api_provider": "openai",
                    "api_key": "test-key",
                    "language": "ja",
                    "compute_type": "int8",
                    "model_size": "medium",
                    "sample_rate": 16000,
                    "isolation_mode": "none",
                }
            },
            "task_type": "full",  # APIモードでも内部的にseparated_modeになる
        }

        config_path = os.path.join(self.temp_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        with (
            patch("core.transcription.Transcriber") as mock_transcriber_class,
            patch("core.alignment_processor.AlignmentProcessor") as mock_alignment_class,
            patch("config.Config") as mock_config_class,
        ):

            # Configのモック
            mock_config = MagicMock()
            mock_config.transcription.use_api = True
            mock_config.transcription.api_provider = "openai"
            mock_config.transcription.api_key = "test-key"
            mock_config.transcription.model_size = "medium"
            mock_config.transcription.language = "ja"
            mock_config.transcription.compute_type = "int8"
            mock_config.transcription.sample_rate = 16000
            mock_config.transcription.isolation_mode = "none"
            mock_config_class.return_value = mock_config

            # Transcriberのモック
            mock_transcriber = MagicMock()
            mock_result = MagicMock()
            mock_result.segments = [MagicMock(text="テスト", words=None)]
            mock_result.language = "ja"
            mock_result.processing_time = 5.0
            mock_result.to_v2_format.return_value = MagicMock(segments=mock_result.segments)
            mock_result.validate_has_words.return_value = (False, ["No words"])
            mock_result.to_dict.return_value = {"segments": [], "language": "ja"}
            mock_transcriber.transcribe.return_value = mock_result
            mock_transcriber_class.return_value = mock_transcriber

            # AlignmentProcessorのモック
            mock_alignment = MagicMock()
            mock_alignment.run_diagnostic.return_value = {
                "diagnostic_completed": True,
                "optimal_batch_size": 8,
                "model_memory": 30.0,
                "audio_memory": 10.0,
                "batch_memory_per_segment": 5.0,
            }
            aligned_segment = MagicMock(text="テスト", words=[{"word": "テスト", "start": 0.0, "end": 1.0}])
            mock_alignment.align.return_value = [aligned_segment]
            mock_alignment_class.return_value = mock_alignment

            import sys

            orig_argv = sys.argv
            sys.argv = ["worker_transcribe.py", config_path]

            try:
                worker_main()
            except SystemExit as e:
                self.assertEqual(e.code, 0)
            finally:
                sys.argv = orig_argv

            # APIモードでTranscriberが使用されたことを確認
            mock_transcriber_class.assert_called_once()

            # アライメント処理が実行されたことを確認
            mock_alignment_class.assert_called()
            mock_alignment.align.assert_called_once()

    def test_vad_segment_30_second_constraint(self):
        """VADセグメントが30秒制約を守ることのテスト"""
        transcriber = SmartBoundaryTranscriber(self.config)

        # 長い音声区間（60秒）のモック
        with patch("subprocess.run") as mock_run:
            # ffprobeの結果（60秒の音声）
            mock_duration = MagicMock()
            mock_duration.stdout = "60.0"
            mock_duration.returncode = 0

            # ffmpegの結果（無音なし = 全体が音声）
            mock_silence = MagicMock()
            mock_silence.stdout = ""  # 無音検出なし
            mock_silence.returncode = 0

            mock_run.side_effect = [mock_duration, mock_silence]

            segments = transcriber._find_vad_based_segments("/tmp/test.wav")

        # 各セグメントが30秒以内であることを確認
        for start, end in segments:
            duration = end - start
            self.assertLessEqual(
                duration, 30.0, f"セグメント ({start:.1f}-{end:.1f}) が30秒を超えています: {duration:.1f}秒"
            )

        # 全体の時間が保持されていることを確認
        total_duration = sum(end - start for start, end in segments)
        self.assertAlmostEqual(total_duration, 60.0, places=1)


if __name__ == "__main__":
    unittest.main()
