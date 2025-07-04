"""
UI定数のユニットテスト
"""

from unittest.mock import patch

from ui.constants import (
    BUTTON_PROCESS,
    DEFAULT_ICON,
    EMOJI_SUCCESS,
    EMOJI_VIDEO,
    ICON_SVG,
    MAX_FILE_SIZE_MB,
    MSG_PROCESSING,
    TAB_TRANSCRIPTION,
    TIME_FORMAT,
    get_app_icon,
)


class TestGetAppIcon:
    """get_app_icon関数のテスト"""

    @patch("pathlib.Path.exists")
    def test_icon_file_exists(self, mock_exists):
        """アイコンファイルが存在する場合"""
        mock_exists.return_value = True

        result = get_app_icon()

        # パスが返される（icon.pngで終わる）
        assert result.endswith("assets/icon.png")
        assert isinstance(result, str)

    @patch("pathlib.Path.exists")
    def test_icon_file_not_exists(self, mock_exists):
        """アイコンファイルが存在しない場合"""
        mock_exists.return_value = False

        result = get_app_icon()

        # デフォルトアイコンが返される
        assert result == DEFAULT_ICON
        assert result == "🎬"

    def test_icon_path_construction(self):
        """アイコンパスの構築が正しいか"""
        # get_app_icon内部でパスが正しく構築されているかを間接的に確認
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            result = get_app_icon()

            # Pathオブジェクトのexistsが呼ばれたことを確認
            assert mock_exists.called


class TestConstants:
    """定数定義のテスト"""

    def test_emoji_constants(self):
        """絵文字定数が定義されている"""
        assert DEFAULT_ICON == "🎬"
        assert EMOJI_VIDEO == "🎥"
        assert EMOJI_SUCCESS == "✅"

    def test_button_labels(self):
        """ボタンラベルが定義されている"""
        assert BUTTON_PROCESS == "処理を実行"
        assert isinstance(BUTTON_PROCESS, str)

    def test_tab_names(self):
        """タブ名が定義されている"""
        assert TAB_TRANSCRIPTION == "文字起こし"
        assert isinstance(TAB_TRANSCRIPTION, str)

    def test_messages(self):
        """メッセージテンプレートが定義されている"""
        assert MSG_PROCESSING == "処理中..."
        assert isinstance(MSG_PROCESSING, str)

    def test_size_constants(self):
        """サイズ定数が定義されている"""
        assert MAX_FILE_SIZE_MB == 2048
        assert isinstance(MAX_FILE_SIZE_MB, int)

    def test_format_strings(self):
        """フォーマット文字列が定義されている"""
        assert TIME_FORMAT == "%H:%M:%S"
        assert isinstance(TIME_FORMAT, str)


class TestConstantUsage:
    """定数の使用例のテスト"""

    def test_file_size_calculation(self):
        """ファイルサイズ計算での使用例"""
        file_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        assert file_size_bytes == 2147483648  # 2GB in bytes

    def test_time_formatting(self):
        """時間フォーマットの使用例"""
        from datetime import datetime

        now = datetime.now()
        formatted = now.strftime(TIME_FORMAT)
        # HH:MM:SS形式であることを確認
        assert len(formatted.split(":")) == 3

    def test_icon_svg_content(self):
        """SVGアイコンの内容確認"""
        # SVGタグが含まれているか
        assert "<svg" in ICON_SVG
        assert "</svg>" in ICON_SVG

        # 必要なクラスが定義されているか
        assert "textffcut-logo" in ICON_SVG
        assert "icon-dark" in ICON_SVG
        assert "icon-red" in ICON_SVG

        # サイズ属性が含まれているか
        assert 'width="45"' in ICON_SVG
        assert 'height="50"' in ICON_SVG
