"""
バージョンヘルパー関数のユニットテスト
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from utils.version_helpers import format_version_display, get_app_version, parse_version


class TestGetAppVersion:
    """get_app_version関数のテスト"""

    def test_read_existing_version_file(self):
        """存在するバージョンファイルを読み込む"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("v1.2.3")
            temp_path = Path(f.name)

        try:
            result = get_app_version(temp_path)
            assert result == "v1.2.3"
        finally:
            temp_path.unlink()

    def test_non_existing_file_returns_default(self):
        """存在しないファイルの場合はデフォルトを返す"""
        non_existing = Path("/path/that/does/not/exist/VERSION.txt")
        result = get_app_version(non_existing)
        assert result == "v1.0.0"

    def test_custom_default_version(self):
        """カスタムデフォルトバージョンを指定"""
        non_existing = Path("/path/that/does/not/exist/VERSION.txt")
        result = get_app_version(non_existing, "v2.0.0")
        assert result == "v2.0.0"

    def test_empty_file_returns_default(self):
        """空のファイルの場合はデフォルトを返す"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            result = get_app_version(temp_path)
            assert result == "v1.0.0"
        finally:
            temp_path.unlink()

    @patch("__main__.__file__", "/path/to/app/main.py", create=True)
    def test_default_path_with_main_file(self):
        """デフォルトパス使用時（__main__.__file__が存在）"""
        # VERSION.txtが存在しない想定
        with patch("pathlib.Path.exists", return_value=False):
            result = get_app_version()
            assert result == "v1.0.0"

    def test_default_path_without_main_file(self):
        """デフォルトパス使用時（__main__.__file__が存在しない）"""
        # __main__モジュールに__file__がない状況をシミュレート
        import sys

        old_main = sys.modules.get("__main__")
        fake_main = type(sys)("__main__")
        fake_main.__name__ = "__main__"
        sys.modules["__main__"] = fake_main

        try:
            result = get_app_version()
            assert result == "v1.0.0"
        finally:
            if old_main:
                sys.modules["__main__"] = old_main

    def test_io_error_returns_default(self):
        """IOエラーの場合はデフォルトを返す"""
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = OSError("Read error")

        result = get_app_version(mock_path)
        assert result == "v1.0.0"


class TestFormatVersionDisplay:
    """format_version_display関数のテスト"""

    def test_add_prefix(self):
        """プレフィックスなしの場合に追加"""
        result = format_version_display("1.0.0")
        assert result == "v1.0.0"

    def test_keep_existing_prefix(self):
        """既存のプレフィックスは保持"""
        result = format_version_display("v1.0.0")
        assert result == "v1.0.0"

    def test_remove_prefix(self):
        """プレフィックスを除去"""
        result = format_version_display("v1.0.0", include_prefix=False)
        assert result == "1.0.0"

    def test_no_prefix_without_prefix(self):
        """プレフィックスなしでプレフィックス除去"""
        result = format_version_display("1.0.0", include_prefix=False)
        assert result == "1.0.0"


class TestParseVersion:
    """parse_version関数のテスト"""

    def test_parse_with_prefix(self):
        """プレフィックス付きバージョンのパース"""
        result = parse_version("v1.2.3")
        assert result == (1, 2, 3)

    def test_parse_without_prefix(self):
        """プレフィックスなしバージョンのパース"""
        result = parse_version("2.4.6")
        assert result == (2, 4, 6)

    def test_parse_zero_version(self):
        """ゼロバージョンのパース"""
        result = parse_version("0.0.0")
        assert result == (0, 0, 0)

    def test_invalid_format_raises_error(self):
        """不正な形式でエラー"""
        with pytest.raises(ValueError, match="不正なバージョン文字列"):
            parse_version("1.2")

    def test_non_numeric_raises_error(self):
        """数値以外でエラー"""
        with pytest.raises(ValueError, match="不正なバージョン文字列"):
            parse_version("1.a.3")

    def test_empty_string_raises_error(self):
        """空文字列でエラー"""
        with pytest.raises(ValueError):
            parse_version("")
