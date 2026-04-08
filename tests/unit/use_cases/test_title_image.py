"""タイトル画像生成のユニットテスト"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from use_cases.ai.title_image_generator import (
    TitleImageDesign,
    TitleLine,
    TitleTextSegment,
    _hex_to_rgb,
    _parse_design_json,
    _split_title,
    create_fallback_design,
    extract_frame_colors,
    find_font,
    generate_title_image,
    render_title_image,
)


class TestDataStructures:
    def test_title_text_segment_defaults(self):
        seg = TitleTextSegment(text="テスト")
        assert seg.text == "テスト"
        assert seg.font_size == 72
        assert seg.color == "#FFFFFF"
        assert seg.gradient is None
        assert seg.weight == "Eb"

    def test_title_line_defaults(self):
        seg = TitleTextSegment(text="テスト")
        line = TitleLine(segments=[seg])
        assert line.outer_outline_color == "#000000"
        assert line.outer_outline_width == 8
        assert line.inner_outline_width == 0

    def test_title_image_design_defaults(self):
        seg = TitleTextSegment(text="テスト")
        line = TitleLine(segments=[seg])
        design = TitleImageDesign(lines=[line])
        assert design.line_spacing == 10
        assert design.padding_top == 60
        assert design.background_color is None


class TestFontSearch:
    def test_find_font_returns_string(self):
        result = find_font("Eb")
        assert isinstance(result, str)
        assert result.endswith(".otf") or result.endswith(".ttc")

    def test_find_font_with_dir(self, tmp_path):
        # フォントファイルが存在しないディレクトリ
        result = find_font("Eb", font_dir=tmp_path)
        # フォールバックパスが返される
        assert isinstance(result, str)

    def test_find_font_weight_map(self):
        for weight in ["Th", "Rg", "Bd", "Eb"]:
            result = find_font(weight)
            assert isinstance(result, str)


class TestHexToRgb:
    def test_valid_hex(self):
        assert _hex_to_rgb("#FF0000") == (255, 0, 0)
        assert _hex_to_rgb("#00FF00") == (0, 255, 0)
        assert _hex_to_rgb("#0000FF") == (0, 0, 255)
        assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)
        assert _hex_to_rgb("#000000") == (0, 0, 0)

    def test_invalid_hex(self):
        assert _hex_to_rgb("invalid") == (255, 255, 255)
        assert _hex_to_rgb("#FFF") == (255, 255, 255)


class TestSplitTitle:
    def test_short_title(self):
        result = _split_title("短い")
        assert result == ["短い"]

    def test_split_on_punctuation(self):
        result = _split_title("これは長い文章で「テスト」を含む例です")
        assert len(result) >= 2

    def test_max_lines(self):
        result = _split_title("とても長いタイトルの文字列を分割するテスト", max_lines=2)
        assert len(result) <= 2


class TestParseDesignJson:
    def test_valid_json(self):
        raw = {
            "lines": [
                {
                    "segments": [
                        {"text": "テスト", "font_size": 80, "color": "#FFFFFF", "weight": "Eb"}
                    ],
                    "outer_outline_color": "#000000",
                    "outer_outline_width": 8,
                }
            ],
            "line_spacing": 12,
            "padding_top": 60,
        }
        design = _parse_design_json(raw)
        assert len(design.lines) == 1
        assert design.lines[0].segments[0].text == "テスト"
        assert design.lines[0].segments[0].font_size == 80

    def test_gradient_parsing(self):
        raw = {
            "lines": [
                {
                    "segments": [
                        {"text": "グラデ", "gradient": ["#FFD700", "#FF6600"]}
                    ]
                }
            ]
        }
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].gradient == ("#FFD700", "#FF6600")

    def test_clamp_values(self):
        raw = {
            "lines": [
                {
                    "segments": [
                        {"text": "大きすぎ", "font_size": 200}
                    ],
                    "outer_outline_width": 50,
                }
            ],
            "padding_top": 999,
        }
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].font_size == 120  # clamped
        assert design.lines[0].outer_outline_width == 10  # clamped
        assert design.padding_top == 200  # clamped

    def test_empty_lines_raises(self):
        with pytest.raises(ValueError):
            _parse_design_json({"lines": []})


class TestFallbackDesign:
    def test_creates_valid_design(self):
        design = create_fallback_design("AIは使えないと思ってる人危険です")
        assert len(design.lines) >= 1
        assert all(len(line.segments) > 0 for line in design.lines)

    def test_short_title(self):
        design = create_fallback_design("短い")
        assert len(design.lines) == 1
        assert design.lines[0].segments[0].text == "短い"


class TestRenderTitleImage:
    def test_basic_render(self, tmp_path):
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[TitleTextSegment(text="Hello", font_size=72)],
                    outer_outline_width=4,
                )
            ]
        )
        output = tmp_path / "test.png"
        result = render_title_image(design, output, width=540, height=960)
        assert result.exists()

        img = Image.open(result)
        assert img.size == (540, 960)
        assert img.mode == "RGBA"

    def test_multi_segment_render(self, tmp_path):
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(text="Big", font_size=90, weight="Eb"),
                        TitleTextSegment(text="Small", font_size=50, weight="Rg"),
                    ],
                    outer_outline_width=6,
                    inner_outline_width=3,
                    inner_outline_color="#FFFFFF",
                )
            ]
        )
        output = tmp_path / "multi.png"
        result = render_title_image(design, output, width=540, height=960)
        assert result.exists()

    def test_gradient_render(self, tmp_path):
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(
                            text="Gradient",
                            font_size=72,
                            gradient=("#FFD700", "#FF6600"),
                        )
                    ],
                    outer_outline_width=4,
                )
            ]
        )
        output = tmp_path / "grad.png"
        result = render_title_image(design, output, width=540, height=960)
        assert result.exists()

    def test_auto_shrink_wide_text(self, tmp_path):
        """幅を超えるテキストが自動縮小されること"""
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(text="あ" * 30, font_size=120)
                    ]
                )
            ]
        )
        output = tmp_path / "shrink.png"
        result = render_title_image(design, output, width=300, height=500)
        assert result.exists()


class TestExtractFrameColors:
    def test_solid_color_image(self, tmp_path):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        path = tmp_path / "red.png"
        img.save(str(path))

        colors = extract_frame_colors(path)
        assert len(colors) >= 1
        assert colors[0] == "#ff0000"

    def test_transparent_image(self, tmp_path):
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        path = tmp_path / "transparent.png"
        img.save(str(path))

        colors = extract_frame_colors(path)
        assert colors == []

    def test_nonexistent_file(self, tmp_path):
        colors = extract_frame_colors(tmp_path / "missing.png")
        assert colors == []


class TestGenerateTitleImage:
    def test_without_client(self, tmp_path):
        """AI無しでフォールバックデザインが使われること"""
        output = tmp_path / "title.png"
        result = generate_title_image(
            title="テストタイトル",
            keywords=["テスト"],
            output_path=output,
            client=None,
        )
        assert result is not None
        assert result.exists()

    def test_with_cache(self, tmp_path):
        """キャッシュからデザインが読み込まれること"""
        output = tmp_path / "title.png"
        cache_path = output.with_suffix(".title.json")

        cache_data = {
            "lines": [
                {
                    "segments": [
                        {"text": "キャッシュ", "font_size": 72, "color": "#FFFFFF", "weight": "Eb"}
                    ],
                    "outer_outline_width": 4,
                }
            ],
            "line_spacing": 10,
            "padding_top": 60,
        }
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False))

        result = generate_title_image(
            title="テスト",
            keywords=[],
            output_path=output,
            client=None,
        )
        assert result is not None

    def test_horizontal_orientation(self, tmp_path):
        output = tmp_path / "title_h.png"
        result = generate_title_image(
            title="横",
            keywords=[],
            output_path=output,
            orientation="horizontal",
            client=None,
        )
        assert result is not None
        img = Image.open(result)
        assert img.size == (1920, 1080)

    def test_vertical_orientation(self, tmp_path):
        output = tmp_path / "title_v.png"
        result = generate_title_image(
            title="縦",
            keywords=[],
            output_path=output,
            orientation="vertical",
            client=None,
        )
        assert result is not None
        img = Image.open(result)
        assert img.size == (1080, 1920)
