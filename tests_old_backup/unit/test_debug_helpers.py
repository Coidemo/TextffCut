"""
デバッグヘルパー関数のユニットテスト
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils.debug_helpers import debug_file_info, debug_memory_usage, debug_words_status


class TestDebugWordsStatus:
    """debug_words_status関数のテスト"""

    @patch("utils.debug_helpers.get_logger")
    def test_with_segments_and_words(self, mock_get_logger):
        """正常なセグメント（wordsあり）の場合"""
        # モックロガーの設定
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # テスト用の結果オブジェクト
        segment1 = SimpleNamespace(
            words=["word1", "word2", "word3"], text="これはテスト用のセグメント1です。とても長い文章のテストです。"
        )
        segment2 = SimpleNamespace(words=["word4", "word5"], text="セグメント2のテキスト")
        result = SimpleNamespace(segments=[segment1, segment2])

        # 実行
        debug_words_status(result)

        # 検証
        assert mock_logger.info.call_count == 3
        mock_logger.info.assert_any_call("Words状態: 2/2 セグメント")
        mock_logger.info.assert_any_call(
            "  セグメント0: 3words - これはテスト用のセグメント1です。とても長い文章のテストです..."
        )
        mock_logger.info.assert_any_call("  セグメント1: 2words - セグメント2のテキスト...")

    @patch("utils.debug_helpers.get_logger")
    def test_with_segments_without_words(self, mock_get_logger):
        """wordsフィールドがないセグメントの場合"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # wordsフィールドがないセグメント
        segment1 = SimpleNamespace(text="wordsなしセグメント")
        segment2 = SimpleNamespace(words=[], text="空のwordsリストを持つセグメント")  # 空のwordsリスト
        result = SimpleNamespace(segments=[segment1, segment2])

        # 実行
        debug_words_status(result)

        # 検証
        assert mock_logger.warning.call_count == 2
        mock_logger.warning.assert_any_call("  セグメント0: wordsなし! - wordsなしセグメント...")
        mock_logger.warning.assert_any_call("  セグメント1: wordsなし! - 空のwordsリストを持つセグメント...")

    @patch("utils.debug_helpers.get_logger")
    def test_without_segments(self, mock_get_logger):
        """segmentsフィールドがない場合"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        result = SimpleNamespace()  # segmentsフィールドなし

        # 実行
        debug_words_status(result)

        # 検証
        mock_logger.warning.assert_called_once_with("結果オブジェクトにsegmentsフィールドがありません")

    @patch("utils.debug_helpers.get_logger")
    def test_custom_logger_name(self, mock_get_logger):
        """カスタムロガー名を指定した場合"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        result = SimpleNamespace(segments=[])

        # カスタムロガー名で実行
        debug_words_status(result, logger_name="custom.logger")

        # get_loggerがカスタム名で呼ばれたことを確認
        mock_get_logger.assert_called_once_with("custom.logger")


class TestDebugMemoryUsage:
    """debug_memory_usage関数のテスト"""

    @patch("psutil.virtual_memory")
    @patch("psutil.Process")
    @patch("utils.debug_helpers.get_logger")
    def test_memory_logging(self, mock_get_logger, mock_process_class, mock_virtual_memory):
        """メモリ使用状況のログ出力"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # プロセスメモリのモック
        mock_process = Mock()
        mock_process.memory_info.return_value = SimpleNamespace(rss=1024 * 1024 * 512)  # 512MB
        mock_process_class.return_value = mock_process

        # システムメモリのモック
        mock_virtual_memory.return_value = SimpleNamespace(percent=65.5)

        # 実行
        debug_memory_usage()

        # 検証
        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call("プロセスメモリ使用量: 512.0MB")
        mock_logger.info.assert_any_call("システムメモリ使用率: 65.5%")


class TestDebugFileInfo:
    """debug_file_info関数のテスト"""

    @patch("pathlib.Path")
    @patch("utils.debug_helpers.get_logger")
    def test_existing_file(self, mock_get_logger, mock_path_class):
        """存在するファイルの情報出力"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # Pathオブジェクトのモック
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_path.name = "test.mp4"
        mock_path.stat.return_value = SimpleNamespace(st_size=1024 * 1024 * 100, st_mtime=1234567890)  # 100MB
        mock_path_class.return_value = mock_path

        # 実行
        debug_file_info("/path/to/test.mp4")

        # 検証
        assert mock_logger.info.call_count == 3
        mock_logger.info.assert_any_call("ファイル: test.mp4")
        mock_logger.info.assert_any_call("  サイズ: 100.0MB")

    @patch("pathlib.Path")
    @patch("utils.debug_helpers.get_logger")
    def test_non_existing_file(self, mock_get_logger, mock_path_class):
        """存在しないファイルの場合"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_path_class.return_value = mock_path

        # 実行
        debug_file_info("/path/to/missing.mp4")

        # 検証
        mock_logger.warning.assert_called_once_with("ファイルが存在しません: /path/to/missing.mp4")
