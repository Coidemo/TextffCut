#!/usr/bin/env python
"""
リファクタリングされたworker_transcribe_v2の単体テスト
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worker_transcribe_v2 import (
    ConfigLoader,
    FullProcessHandler,
    MemoryManager,
    SeparatedModeHandler,
    TranscribeOnlyHandler,
    TranscriptionWorker,
    WorkerConfig,
)


class TestConfigLoader(unittest.TestCase):
    """ConfigLoaderのテスト"""

    def setUp(self):
        """テスト用の一時ファイルを作成"""
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.config_data = {
            "video_path": "/path/to/video.mp4",
            "model_size": "base",
            "use_cache": True,
            "save_cache": True,
            "task_type": "full",
            "config": {
                "transcription": {
                    "use_api": False,
                    "model_size": "base",
                    "language": "ja",
                    "compute_type": "int8",
                    "sample_rate": 16000,
                    "isolation_mode": "none",
                }
            },
        }
        json.dump(self.config_data, self.temp_file)
        self.temp_file.close()

    def tearDown(self):
        """一時ファイルを削除"""
        os.unlink(self.temp_file.name)

    def test_load_valid_config(self):
        """正常な設定ファイルの読み込み"""
        loader = ConfigLoader(self.temp_file.name)
        config = loader.load()

        self.assertIsInstance(config, WorkerConfig)
        self.assertEqual(config.video_path, "/path/to/video.mp4")
        self.assertEqual(config.model_size, "base")
        self.assertTrue(config.use_cache)
        self.assertTrue(config.save_cache)
        self.assertEqual(config.task_type, "full")

    def test_load_missing_file(self):
        """存在しないファイルの読み込み"""
        loader = ConfigLoader("/nonexistent/path.json")
        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_default_values(self):
        """デフォルト値の適用"""
        # use_cacheとtask_typeを削除
        del self.config_data["use_cache"]
        del self.config_data["task_type"]

        with open(self.temp_file.name, "w") as f:
            json.dump(self.config_data, f)

        loader = ConfigLoader(self.temp_file.name)
        config = loader.load()

        self.assertFalse(config.use_cache)  # デフォルト: False
        self.assertEqual(config.task_type, "full")  # デフォルト: 'full'


class TestMemoryManager(unittest.TestCase):
    """MemoryManagerのテスト"""

    @patch("worker_transcribe_v2.AutoOptimizer")
    @patch("worker_transcribe_v2.MemoryMonitor")
    def test_initialization(self, mock_monitor_class, mock_optimizer_class):
        """初期化のテスト"""
        mock_optimizer = Mock()
        mock_monitor = Mock()
        mock_optimizer_class.return_value = mock_optimizer
        mock_monitor_class.return_value = mock_monitor

        MemoryManager("base")

        mock_optimizer_class.assert_called_once_with("base")
        mock_monitor_class.assert_called_once()
        mock_optimizer.reset_diagnostic_mode.assert_called_once()

    @patch("psutil.Process")
    def test_log_initial_memory(self, mock_process_class):
        """初期メモリログのテスト"""
        mock_process = Mock()
        mock_process.memory_info.return_value = Mock(rss=1024 * 1024 * 100)  # 100MB
        mock_process_class.return_value = mock_process

        manager = MemoryManager("base")
        manager.log_initial_memory()

        mock_process.memory_info.assert_called_once()

    def test_get_optimal_params(self):
        """最適パラメータ取得のテスト"""
        manager = MemoryManager("base")
        manager.monitor = Mock()
        manager.optimizer = Mock()

        manager.monitor.get_memory_usage.return_value = 50.0
        manager.optimizer.get_optimal_params.return_value = {"chunk_seconds": 600}

        params = manager.get_optimal_params()

        self.assertEqual(params, {"chunk_seconds": 600})
        manager.monitor.get_memory_usage.assert_called_once()
        manager.optimizer.get_optimal_params.assert_called_once_with(50.0)


class TestTaskHandlers(unittest.TestCase):
    """タスクハンドラーのテスト"""

    def setUp(self):
        """共通のセットアップ"""
        self.worker_config = WorkerConfig(
            video_path="/path/to/video.mp4",
            model_size="base",
            use_cache=False,
            save_cache=False,
            task_type="full",
            config_dict={
                "transcription": {
                    "use_api": False,
                    "model_size": "base",
                    "language": "ja",
                    "compute_type": "int8",
                    "sample_rate": 16000,
                    "isolation_mode": "none",
                }
            },
        )
        self.mock_optimizer = Mock()
        self.mock_monitor = Mock()

    @patch("core.transcription.Transcriber")
    def test_transcribe_only_handler(self, mock_transcriber_class):
        """TranscribeOnlyHandlerのテスト"""
        mock_transcriber = Mock()
        mock_result = Mock()
        mock_result.validate_has_words.return_value = (True, [])
        mock_transcriber.transcribe.return_value = mock_result
        mock_transcriber_class.return_value = mock_transcriber

        # APIモードで設定
        self.worker_config.config_dict["transcription"]["use_api"] = True

        handler = TranscribeOnlyHandler(self.worker_config, self.mock_optimizer, self.mock_monitor)

        result = handler.process()

        self.assertEqual(result, mock_result)
        mock_transcriber.transcribe.assert_called_once_with(
            video_path="/path/to/video.mp4",
            model_size="base",
            progress_callback=unittest.mock.ANY,
            use_cache=False,
            save_cache=False,
            skip_alignment=True,
        )

    def test_create_progress_callback(self):
        """プログレスコールバックの作成テスト"""
        handler = TranscribeOnlyHandler(self.worker_config, self.mock_optimizer, self.mock_monitor)

        callback = handler._create_progress_callback()

        # コールバックが関数であることを確認
        self.assertTrue(callable(callback))

        # 標準出力をキャプチャ
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            callback(0.5, "テストメッセージ")

        output = f.getvalue()
        self.assertIn("PROGRESS:0.5|テストメッセージ", output)


class TestTranscriptionWorker(unittest.TestCase):
    """TranscriptionWorkerのテスト"""

    def setUp(self):
        """テスト用の設定ファイルを作成"""
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.config_data = {
            "video_path": "/path/to/video.mp4",
            "model_size": "base",
            "task_type": "full",
            "config": {
                "transcription": {
                    "use_api": False,
                    "model_size": "base",
                    "language": "ja",
                    "compute_type": "int8",
                    "sample_rate": 16000,
                }
            },
        }
        json.dump(self.config_data, self.temp_file)
        self.temp_file.close()

    def tearDown(self):
        """一時ファイルを削除"""
        os.unlink(self.temp_file.name)

    @patch("worker_transcribe_v2.MemoryManager")
    @patch("worker_transcribe_v2.ConfigLoader")
    def test_initialization(self, mock_loader_class, mock_manager_class):
        """初期化のテスト"""
        mock_loader = Mock()
        mock_config = Mock(model_size="base")
        mock_loader.load.return_value = mock_config
        mock_loader_class.return_value = mock_loader

        TranscriptionWorker(self.temp_file.name)

        mock_loader_class.assert_called_once_with(self.temp_file.name)
        mock_loader.load.assert_called_once()
        mock_manager_class.assert_called_once_with("base")

    def test_create_task_handler_api_mode(self):
        """APIモードでのタスクハンドラー作成"""
        worker = TranscriptionWorker(self.temp_file.name)
        worker.worker_config.config_dict["transcription"]["use_api"] = True

        handler = worker._create_task_handler()

        # APIモードではFullProcessHandlerが返される

        self.assertIsInstance(handler, FullProcessHandler)

    def test_create_task_handler_local_mode(self):
        """ローカルモードでのタスクハンドラー作成"""
        worker = TranscriptionWorker(self.temp_file.name)
        worker.worker_config.config_dict["transcription"]["use_api"] = False
        worker.worker_config.task_type = "full"

        handler = worker._create_task_handler()

        # ローカルモードではSeparatedModeHandlerが返される

        self.assertIsInstance(handler, SeparatedModeHandler)

    def test_save_result(self):
        """結果保存のテスト"""
        worker = TranscriptionWorker(self.temp_file.name)

        # モック結果を作成
        mock_result = Mock()
        mock_result.to_dict.return_value = {"test": "data"}
        mock_result.segments = [Mock(text="テストテキスト")]

        # 結果を保存
        worker._save_result(mock_result)

        # 保存されたファイルを確認
        result_path = os.path.join(os.path.dirname(self.temp_file.name), "result.json")
        self.assertTrue(os.path.exists(result_path))

        with open(result_path) as f:
            saved_data = json.load(f)

        self.assertEqual(saved_data, {"test": "data"})

        # クリーンアップ
        os.unlink(result_path)

    def test_handle_memory_error(self):
        """メモリエラー処理のテスト"""
        worker = TranscriptionWorker(self.temp_file.name)

        with self.assertRaises(SystemExit) as cm:
            worker._handle_memory_error(MemoryError("Test memory error"))

        self.assertEqual(cm.exception.code, 1)

        # エラー結果が保存されたか確認
        result_path = os.path.join(os.path.dirname(self.temp_file.name), "result.json")
        self.assertTrue(os.path.exists(result_path))

        with open(result_path) as f:
            error_data = json.load(f)

        self.assertFalse(error_data["success"])
        self.assertEqual(error_data["error_type"], "MemoryError")
        self.assertIn("suggestion", error_data)

        # クリーンアップ
        os.unlink(result_path)


if __name__ == "__main__":
    unittest.main()
