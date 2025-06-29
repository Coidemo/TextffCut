"""
UIスタイルのユニットテスト
"""

import pytest

from ui.styles import get_custom_css, get_font_sizes, get_image_optimization_css


class TestGetCustomCss:
    """get_custom_css関数のテスト"""
    
    def test_returns_css_string(self):
        """CSS文字列を返すことを確認"""
        css = get_custom_css()
        assert isinstance(css, str)
        assert len(css) > 0
    
    def test_contains_style_tags(self):
        """<style>タグが含まれているか"""
        css = get_custom_css()
        assert "<style>" in css
        assert "</style>" in css
    
    def test_contains_main_styles(self):
        """主要なスタイル定義が含まれているか"""
        css = get_custom_css()
        
        # 全体的なフォントサイズ
        assert ".stApp" in css
        assert "font-size: 14px" in css
        
        # 見出しのスタイル
        assert "h1" in css
        assert "h2" in css
        assert "font-size: 2rem" in css
        
        # ボタンのスタイル
        assert ".stButton" in css
        
        # サイドバーのスタイル
        assert ".sidebar" in css
    
    def test_contains_image_optimization(self):
        """画像最適化のスタイルが含まれているか"""
        css = get_custom_css()
        assert "img {" in css
        assert "image-rendering" in css
        assert "max-width: 100%" in css


class TestGetFontSizes:
    """get_font_sizes関数のテスト"""
    
    def test_returns_dict(self):
        """辞書を返すことを確認"""
        sizes = get_font_sizes()
        assert isinstance(sizes, dict)
        assert len(sizes) > 0
    
    def test_contains_expected_keys(self):
        """期待されるキーが含まれているか"""
        sizes = get_font_sizes()
        expected_keys = ["body", "h1", "h2", "h3", "h4", "button", "caption", "sidebar"]
        
        for key in expected_keys:
            assert key in sizes
    
    def test_font_size_values(self):
        """フォントサイズの値が正しいか"""
        sizes = get_font_sizes()
        
        assert sizes["body"] == "14px"
        assert sizes["h1"] == "2rem"
        assert sizes["h2"] == "1.5rem"
        assert sizes["button"] == "14px"
        assert sizes["sidebar"] == "13px"
    
    def test_all_values_are_strings(self):
        """すべての値が文字列であることを確認"""
        sizes = get_font_sizes()
        
        for value in sizes.values():
            assert isinstance(value, str)
            # サイズ単位が含まれているか
            assert "px" in value or "rem" in value


class TestGetImageOptimizationCss:
    """get_image_optimization_css関数のテスト"""
    
    def test_returns_css_string(self):
        """CSS文字列を返すことを確認"""
        css = get_image_optimization_css()
        assert isinstance(css, str)
        assert len(css) > 0
    
    def test_contains_img_styles(self):
        """img要素のスタイルが含まれているか"""
        css = get_image_optimization_css()
        
        assert "img {" in css
        assert "image-rendering: auto" in css
        assert "image-rendering: -webkit-optimize-contrast" in css
        assert "max-width: 100%" in css
        assert "height: auto" in css
    
    def test_no_style_tags(self):
        """<style>タグが含まれていないことを確認（部分的なCSSのため）"""
        css = get_image_optimization_css()
        assert "<style>" not in css
        assert "</style>" not in css