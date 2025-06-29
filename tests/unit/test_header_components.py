"""
ヘッダーコンポーネントのユニットテスト
"""

from unittest.mock import patch, call, MagicMock

import pytest

from ui.components_modules.header import show_app_title, show_simple_title, show_version_info


class TestShowAppTitle:
    """show_app_title関数のテスト"""
    
    @patch('streamlit.markdown')
    def test_displays_title_with_version(self, mock_markdown):
        """タイトルとバージョンが表示される"""
        show_app_title("v1.2.3")
        
        # markdownが2回呼ばれる（タイトルとサブタイトル）
        assert mock_markdown.call_count == 2
        
        # 最初の呼び出し（タイトル）
        first_call = mock_markdown.call_args_list[0]
        first_html = first_call[0][0]
        assert "Text" in first_html and "ff" in first_html and "Cut" in first_html
        assert "v1.2.3" in first_html
        assert 'style="color: red; font-style: italic;">ff</span>' in first_html
        assert "unsafe_allow_html" in first_call[1]
        assert first_call[1]["unsafe_allow_html"] is True
        
        # 2番目の呼び出し（サブタイトル）
        second_call = mock_markdown.call_args_list[1]
        second_html = second_call[0][0]
        assert "切り抜き動画編集支援ツール" in second_html
    
    @patch('streamlit.markdown')
    def test_default_version(self, mock_markdown):
        """デフォルトバージョンでの表示"""
        show_app_title()
        
        first_call = mock_markdown.call_args_list[0]
        first_html = first_call[0][0]
        assert "v1.0.0" in first_html
    
    @patch('streamlit.markdown')
    def test_includes_svg_icon(self, mock_markdown):
        """SVGアイコンが含まれる"""
        show_app_title("v2.0.0")
        
        first_call = mock_markdown.call_args_list[0]
        first_html = first_call[0][0]
        # SVGタグが含まれることを確認
        assert "<svg" in first_html
        assert "textffcut-logo" in first_html


class TestShowSimpleTitle:
    """show_simple_title関数のテスト"""
    
    @patch('streamlit.markdown')
    def test_title_without_icon(self, mock_markdown):
        """アイコンなしのタイトル"""
        show_simple_title("設定画面")
        
        mock_markdown.assert_called_once_with("# 設定画面")
    
    @patch('streamlit.markdown')
    def test_title_with_icon(self, mock_markdown):
        """アイコン付きのタイトル"""
        show_simple_title("設定", "⚙️")
        
        mock_markdown.assert_called_once_with("# ⚙️ 設定")
    
    @patch('streamlit.markdown')
    def test_empty_icon_string(self, mock_markdown):
        """空文字のアイコン"""
        show_simple_title("タイトル", "")
        
        mock_markdown.assert_called_once_with("# タイトル")


class TestShowVersionInfo:
    """show_version_info関数のテスト"""
    
    @patch('streamlit.caption')
    def test_basic_version_display(self, mock_caption):
        """基本的なバージョン表示"""
        show_version_info("v1.2.3")
        
        mock_caption.assert_called_once_with("Version: v1.2.3")
    
    @patch('streamlit.caption')
    def test_version_without_prefix(self, mock_caption):
        """プレフィックスなしのバージョン"""
        show_version_info("1.2.3")
        
        mock_caption.assert_called_once_with("Version: 1.2.3")
    
    @patch('streamlit.caption')
    def test_show_details_false(self, mock_caption):
        """詳細表示なし（デフォルト）"""
        show_version_info("v1.0.0", show_details=False)
        
        # captionは1回だけ呼ばれる
        assert mock_caption.call_count == 1
    
    @patch('streamlit.caption')
    def test_show_details_true(self, mock_caption):
        """詳細表示あり（将来の拡張用）"""
        show_version_info("v1.0.0", show_details=True)
        
        # 現在は詳細表示の実装がないので、captionは1回だけ
        assert mock_caption.call_count == 1