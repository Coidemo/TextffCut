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
    _safe_int,
    _save_design_cache,
    _scale_outline,
    _split_title,
    create_fallback_design,
    design_title_layout,
    design_title_layout_candidates,
    design_title_layouts_batch,
    evaluate_candidates_with_vision,
    extract_frame_colors,
    filter_fitting_candidates,
    find_font,
    generate_title_image,
    generate_title_images_batch,
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

    def test_no_character_loss(self):
        """均等分割で文字が欠落しないこと（25文字・分割点なし）"""
        title = "あ" * 25
        result = _split_title(title)
        assert "".join(result) == title

    def test_no_character_loss_various_lengths(self):
        """様々な長さで文字欠落がないこと"""
        for length in [11, 15, 22, 25, 30, 40, 50]:
            title = "あ" * length
            result = _split_title(title)
            assert "".join(result) == title, f"Length {length}: expected {length} chars, got {len(''.join(result))}"

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
                        {"text": "大きすぎ", "font_size": 300}
                    ],
                    "outer_outline_width": 50,
                }
            ],
            "padding_top": 999,
        }
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].font_size == 220  # clamped
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

    def test_emphasis_on_longest_line(self):
        """複数行の場合、最長行が強調される"""
        design = create_fallback_design("これは長い文章で「テスト」を含む例です")
        assert len(design.lines) >= 2
        # 最長行はグラデーション付き
        sizes = [line.segments[0].font_size for line in design.lines]
        assert max(sizes) == 180  # 強調行
        assert min(sizes) == 130  # 非強調行


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
        result_path, img_w, img_h = render_title_image(design, output, width=540, height=960)
        assert result_path.exists()

        img = Image.open(result_path)
        assert img.width == 540  # 横幅はフル維持
        assert img_h == 960  # フルサイズ透過PNG（クロップなし）
        assert img.height == 960
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
        result_path, _, _ = render_title_image(design, output, width=540, height=960)
        assert result_path.exists()

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
        result_path, _, _ = render_title_image(design, output, width=540, height=960)
        assert result_path.exists()

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
        result_path, _, _ = render_title_image(design, output, width=300, height=500)
        assert result_path.exists()


class TestExtractFrameColors:
    def test_solid_color_image(self, tmp_path):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        path = tmp_path / "red.png"
        img.save(str(path))

        colors = extract_frame_colors(path)
        assert len(colors) >= 1
        # RGB量子化(32刻み): (255,0,0) → (224,0,0)
        assert colors[0] == "#e00000"

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
        assert img.width == 1920  # 横幅はフル維持
        assert img.height == 1080  # フルサイズ透過PNG

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
        assert img.width == 1080  # 横幅はフル維持
        assert img.height == 1920  # フルサイズ透過PNG

    def test_ai_failure_falls_back(self, tmp_path):
        """AI呼び出し失敗時にフォールバックデザインが使われること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        output = tmp_path / "fallback.png"
        result = generate_title_image(
            title="テスト",
            keywords=[],
            output_path=output,
            client=mock_client,
        )
        assert result is not None
        assert result.exists()

    def test_corrupted_cache_recovery(self, tmp_path):
        """キャッシュJSONが壊れている場合にフォールバックで回復すること"""
        output = tmp_path / "title.png"
        cache_path = output.with_suffix(".title.json")
        cache_path.write_text("{ invalid json !!!")
        result = generate_title_image(
            title="テスト",
            keywords=[],
            output_path=output,
            client=None,
        )
        assert result is not None
        assert result.exists()


class TestSafeInt:
    def test_normal_int(self):
        assert _safe_int(42, 0) == 42

    def test_float(self):
        assert _safe_int(72.5, 0) == 72

    def test_string_number(self):
        assert _safe_int("80", 0) == 80

    def test_none(self):
        assert _safe_int(None, 99) == 99

    def test_invalid_string(self):
        assert _safe_int("abc", 50) == 50

    def test_empty_string(self):
        assert _safe_int("", 50) == 50


class TestScaleOutline:
    def test_reference_size(self):
        """ref_size(90)で同じ値が返ること"""
        assert _scale_outline(8, 90) == 8

    def test_smaller_font(self):
        """小さいフォントでアウトラインが縮小されること"""
        result = _scale_outline(8, 60)
        assert result < 8
        assert result >= 2  # 最低2px

    def test_larger_font(self):
        """大きいフォントでアウトラインが拡大されること"""
        result = _scale_outline(8, 120)
        assert result > 8

    def test_zero_base_width(self):
        assert _scale_outline(0, 90) == 0

    def test_minimum_2px(self):
        """極小フォントでも最低2pxが確保されること"""
        result = _scale_outline(4, 10)
        assert result >= 2


class TestDesignTitleLayout:
    def _mock_response(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.choices[0].message.content = content
        return mock

    def test_successful_design(self):
        """正常なAIレスポンスでデザインが返ること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "lines": [{"segments": [{"text": "テスト", "font_size": 80}]}],
                "line_spacing": 10,
                "padding_top": 60,
            })
        )
        design = design_title_layout(
            client=mock_client, title="テスト", keywords=["AI"],
        )
        assert len(design.lines) == 1
        assert design.lines[0].segments[0].text == "テスト"
        mock_client.chat.completions.create.assert_called_once()

    def test_title_mismatch_raises_error(self):
        """AIがタイトル文字を変更した場合にValueErrorが発生すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "lines": [{"segments": [{"text": "改変された", "font_size": 80}]}],
            })
        )
        with pytest.raises(ValueError, match="AIがタイトル文字を変更"):
            design_title_layout(client=mock_client, title="テスト", keywords=[])

    def test_empty_response_raises(self):
        """AIレスポンスが空の場合にValueErrorが発生すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(None)
        # content=None → "AIレスポンスが空です"
        with pytest.raises(ValueError, match="AIレスポンスが空"):
            design_title_layout(client=mock_client, title="テスト", keywords=[])

    def test_uses_custom_prompt_template(self):
        """カスタムプロンプトテンプレートが使われること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "lines": [{"segments": [{"text": "OK", "font_size": 72}]}],
            })
        )
        design_title_layout(
            client=mock_client, title="OK", keywords=[],
            prompt_template="Custom: {TITLE} {KEYWORDS} {FRAME_COLORS} {JSON_SCHEMA} {ORIENTATION}",
        )
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Custom:" in prompt

    def test_frame_colors_in_prompt(self):
        """frame_colorsがプロンプトに含まれること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "lines": [{"segments": [{"text": "色", "font_size": 72}]}],
            })
        )
        design_title_layout(
            client=mock_client, title="色", keywords=[],
            frame_colors=["#FF0000", "#00FF00"],
            prompt_template="{TITLE}{KEYWORDS}{FRAME_COLORS}{JSON_SCHEMA}{ORIENTATION}",
        )
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "#FF0000" in prompt


class TestDesignTitleLayoutsBatch:
    def _mock_response(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.choices[0].message.content = content
        return mock

    def test_batch_success(self):
        """バッチAI呼び出しが正常に動作すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "タイトルA", "font_size": 80}]}]},
                    {"lines": [{"segments": [{"text": "タイトルB", "font_size": 72}]}]},
                ]
            })
        )
        results = design_title_layouts_batch(
            client=mock_client,
            titles=["タイトルA", "タイトルB"],
            keywords_list=[["AI"], ["テスト"]],
        )
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].lines[0].segments[0].text == "タイトルA"

    def test_partial_failure(self):
        """一部タイトルのパースが失敗してもNoneで返ること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "OK", "font_size": 80}]}]},
                    {"lines": []},  # 空行 → ValueError
                ]
            })
        )
        results = design_title_layouts_batch(
            client=mock_client,
            titles=["OK", "NG"],
            keywords_list=[[], []],
        )
        assert results[0] is not None
        assert results[1] is None  # パース失敗

    def test_title_mismatch_returns_none(self):
        """AIがタイトル文字を変更した場合にNoneが返ること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "改変", "font_size": 80}]}]},
                ]
            })
        )
        results = design_title_layouts_batch(
            client=mock_client,
            titles=["元テキスト"],
            keywords_list=[[]],
        )
        assert results[0] is None

    def test_empty_response(self):
        """空レスポンスで例外が発生すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(None)
        with pytest.raises(ValueError, match="AIレスポンスが空"):
            design_title_layouts_batch(
                client=mock_client, titles=["テスト"], keywords_list=[[]],
            )

    def test_fewer_designs_than_titles(self):
        """AIの返すデザイン数がタイトル数より少ない場合"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "A", "font_size": 72}]}]},
                ]
            })
        )
        results = design_title_layouts_batch(
            client=mock_client,
            titles=["A", "B", "C"],
            keywords_list=[[], [], []],
        )
        assert len(results) == 3
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is None


class TestGenerateTitleImagesBatch:
    def _make_suggestions(self, titles: list[str]) -> list:
        suggestions = []
        for t in titles:
            s = MagicMock()
            s.title = t
            s.keywords = []
            suggestions.append(s)
        return suggestions

    def test_without_client(self, tmp_path):
        """client無しでフォールバック画像が全候補分生成されること"""
        suggestions = self._make_suggestions(["タイトルA", "タイトルB"])
        results = generate_title_images_batch(
            suggestions=suggestions,
            output_dir=tmp_path / "titles",
            client=None,
        )
        assert len(results) == 2
        assert all(p.exists() for p in results.values())

    def test_with_cache(self, tmp_path):
        """キャッシュがある候補はAI呼び出しをスキップすること"""
        output_dir = tmp_path / "titles"
        output_dir.mkdir()
        # キャッシュを作成
        cache_data = json.dumps({
            "lines": [{"segments": [{"text": "キャッシュ済み", "font_size": 72}]}],
            "line_spacing": 10,
            "padding_top": 60,
        }, ensure_ascii=False)
        (output_dir / "01_キャッシュ済み.title.json").write_text(cache_data)

        suggestions = self._make_suggestions(["キャッシュ済み"])
        results = generate_title_images_batch(
            suggestions=suggestions,
            output_dir=output_dir,
            client=None,  # AI不使用でもキャッシュから描画
        )
        assert 1 in results
        assert results[1].exists()

    def test_batch_ai_failure_falls_back(self, tmp_path):
        """バッチAI呼び出し失敗時にフォールバックで全候補が生成されること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        suggestions = self._make_suggestions(["タイトルA", "タイトルB"])
        results = generate_title_images_batch(
            suggestions=suggestions,
            output_dir=tmp_path / "titles",
            client=mock_client,
        )
        assert len(results) == 2  # フォールバックで全候補生成
        assert all(p.exists() for p in results.values())


class TestDesignCacheRoundTrip:
    def test_basic_roundtrip(self, tmp_path):
        """保存→読み込みでデザインが復元されること"""
        design = TitleImageDesign(
            lines=[TitleLine(
                segments=[TitleTextSegment(text="テスト", font_size=80, color="#FF0000", weight="Bd")],
                outer_outline_width=6,
                inner_outline_width=3,
                inner_outline_color="#FFFFFF",
            )],
            line_spacing=15,
            padding_top=100,
        )
        cache_path = tmp_path / "test.title.json"
        _save_design_cache(design, cache_path)
        assert cache_path.exists()

        raw = json.loads(cache_path.read_text())
        reloaded = _parse_design_json(raw)

        assert reloaded.lines[0].segments[0].text == "テスト"
        assert reloaded.lines[0].segments[0].font_size == 80
        assert reloaded.lines[0].segments[0].color == "#FF0000"
        assert reloaded.lines[0].segments[0].weight == "Bd"
        assert reloaded.lines[0].outer_outline_width == 6
        assert reloaded.lines[0].inner_outline_width == 3
        assert reloaded.line_spacing == 15
        assert reloaded.padding_top == 100

    def test_gradient_roundtrip(self, tmp_path):
        """gradient tuple→list→tupleの変換が正しいこと"""
        design = TitleImageDesign(
            lines=[TitleLine(
                segments=[TitleTextSegment(text="グラデ", gradient=("#FFD700", "#FF6600"))]
            )]
        )
        cache_path = tmp_path / "grad.title.json"
        _save_design_cache(design, cache_path)

        raw = json.loads(cache_path.read_text())
        reloaded = _parse_design_json(raw)
        assert reloaded.lines[0].segments[0].gradient == ("#FFD700", "#FF6600")

    def test_null_gradient_roundtrip(self, tmp_path):
        """gradient=Noneがラウンドトリップで保持されること"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="普通")])]
        )
        cache_path = tmp_path / "null.title.json"
        _save_design_cache(design, cache_path)

        raw = json.loads(cache_path.read_text())
        reloaded = _parse_design_json(raw)
        assert reloaded.lines[0].segments[0].gradient is None


class TestRenderImageAssertions:
    """画像の内容を検証する強化テスト"""

    def test_fallback_renders_content(self, tmp_path):
        """フォールバックデザインが実際にピクセルを描画すること"""
        output = tmp_path / "fb.png"
        result = generate_title_image(
            title="テストタイトル", keywords=[], output_path=output, client=None,
        )
        assert result is not None
        img = Image.open(result)
        assert img.width == 1080  # 横幅はフル維持
        assert img.height == 1920  # フルサイズ透過PNG
        assert img.mode == "RGBA"
        # 描画領域にはピクセルが存在する
        non_transparent = sum(1 for p in img.getdata() if p[3] > 0)
        assert non_transparent > 0

    def test_ai_design_end_to_end(self, tmp_path):
        """AI設計→キャッシュ→描画→画像検証のフルフロー"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "lines": [
                    {"segments": [
                        {"text": "衝撃", "font_size": 90, "gradient": ["#FFD700", "#FF6600"], "weight": "Eb"},
                        {"text": "の事実", "font_size": 60, "color": "#FFFFFF", "weight": "Bd"},
                    ], "outer_outline_width": 8, "inner_outline_width": 4},
                ],
                "line_spacing": 12,
                "padding_top": 80,
            })))]
        )
        output = tmp_path / "e2e.png"
        result = generate_title_image(
            title="衝撃の事実", keywords=["衝撃"], output_path=output,
            client=mock_client, orientation="vertical",
        )
        assert result is not None
        img = Image.open(result)
        assert img.width == 1080  # 横幅はフル維持
        assert img.height == 1920  # フルサイズ透過PNG
        assert img.mode == "RGBA"
        # キャッシュが生成されている
        assert output.with_suffix(".title.json").exists()


class TestDesignTitleLayoutCandidates:
    """Stage 1: 複数候補生成のテスト"""

    def _mock_response(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.choices[0].message.content = content
        return mock

    def test_generates_multiple_candidates(self):
        """複数候補が正常に生成されること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 160}]}]},
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 120}]}]},
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
                ]
            })
        )
        results = design_title_layout_candidates(
            client=mock_client,
            title="テスト",
            keywords=["AI"],
            target_size=(1080, 438),
        )
        assert len(results) == 3
        assert results[0].lines[0].segments[0].font_size == 160
        assert results[2].lines[0].segments[0].font_size == 90

    def test_skips_invalid_candidates(self):
        """文字不一致の候補はスキップされること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 160}]}]},
                    {"lines": [{"segments": [{"text": "改変された", "font_size": 120}]}]},
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
                ]
            })
        )
        results = design_title_layout_candidates(
            client=mock_client,
            title="テスト",
            keywords=[],
            target_size=(1080, 438),
        )
        assert len(results) == 2  # 改変された候補はスキップ

    def test_empty_response_raises(self):
        """空レスポンスでValueErrorが発生すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(None)
        with pytest.raises(ValueError, match="AIレスポンスが空"):
            design_title_layout_candidates(
                client=mock_client, title="テスト", keywords=[],
                target_size=(1080, 438),
            )


class TestFilterFittingCandidates:
    """Stage 2: フィルタリングのテスト"""

    def test_filters_by_height(self, tmp_path):
        """ターゲット高さを超える候補がフィルタされること"""
        # 小さいフォントの候補（収まる）
        small_design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=80)])]
        )
        # 大きいフォントの候補（はみ出す可能性）
        large_design = TitleImageDesign(
            lines=[
                TitleLine(segments=[TitleTextSegment(text="テスト", font_size=200)]),
                TitleLine(segments=[TitleTextSegment(text="テスト", font_size=200)]),
                TitleLine(segments=[TitleTextSegment(text="テスト", font_size=200)]),
            ]
        )
        results, tmp_dirs = filter_fitting_candidates(
            candidates=[small_design, large_design],
            target_width=1080,
            target_height=438,
            canvas_width=1080,
            canvas_height=1920,
        )
        # 少なくとも1つの結果が返ること（フォールバック含む）
        assert len(results) >= 1
        # 全候補分の一時ディレクトリが返ること
        assert len(tmp_dirs) == 2
        # 各結果のtuple構造を検証
        for design, path, w, content_h in results:
            assert isinstance(design, TitleImageDesign)
            assert path.exists()
            assert w == 1080
            assert content_h > 0

    def test_fallback_when_none_fit(self, tmp_path):
        """収まる候補がない場合にフォールバック候補が返ること"""
        # 非常に大きなフォントの候補3つ
        big_designs = [
            TitleImageDesign(
                lines=[
                    TitleLine(segments=[TitleTextSegment(text="あ" * 10, font_size=200)]),
                    TitleLine(segments=[TitleTextSegment(text="い" * 10, font_size=200)]),
                    TitleLine(segments=[TitleTextSegment(text="う" * 10, font_size=200)]),
                ]
            )
            for _ in range(3)
        ]
        results, tmp_dirs = filter_fitting_candidates(
            candidates=big_designs,
            target_width=1080,
            target_height=100,  # 非常に小さいターゲット
            canvas_width=1080,
            canvas_height=1920,
        )
        # フォールバック: アスペクト比が近い上位3つ
        assert len(results) == 3
        assert len(tmp_dirs) == 3
        # フォールバック候補はターゲット高さを超えている（フィットしなかった証明）
        for design, path, w, content_h in results:
            assert isinstance(design, TitleImageDesign)
            assert path.exists()
            assert content_h > 100  # target_height(100)を超えている

    def test_empty_candidates(self):
        """空の候補リストで空リストが返ること"""
        results, tmp_dirs = filter_fitting_candidates(
            candidates=[],
            target_width=1080,
            target_height=438,
        )
        assert results == []
        assert tmp_dirs == []


class TestOffsetY:
    """offset_yパラメータのテスト"""

    def test_render_offset_y_shifts_content_down(self, tmp_path):
        """offset_yが正の場合、コンテンツが下方向にシフトすること"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=72)])],
            padding_top=60,
        )
        # offset_y=0 で描画
        out0 = tmp_path / "no_offset.png"
        render_title_image(design, out0, width=540, height=960, offset_y=0)
        img0 = Image.open(out0)
        bbox0 = img0.getbbox()

        # offset_y=100 で描画
        out100 = tmp_path / "offset_100.png"
        render_title_image(design, out100, width=540, height=960, offset_y=100)
        img100 = Image.open(out100)
        bbox100 = img100.getbbox()

        # offset_y=100の方がコンテンツ上端(top-y)が約100px下にあること
        assert bbox100[1] > bbox0[1]
        assert abs((bbox100[1] - bbox0[1]) - 100) < 5  # 誤差5px以内

    def test_render_offset_y_negative(self, tmp_path):
        """offset_yが負の場合、コンテンツが上方向にシフトすること"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=72)])],
            padding_top=100,
        )
        out_neg = tmp_path / "neg.png"
        render_title_image(design, out_neg, width=540, height=960, offset_y=-50)
        img = Image.open(out_neg)
        bbox = img.getbbox()
        # padding_top=100, offset_y=-50 → 実効位置は50px付近
        assert bbox is not None
        assert bbox[1] < 100  # 100pxより上に描画される

    def test_filter_fitting_with_offset_y(self):
        """offset_yが大きいとフィルタリングで弾かれること"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=80)])],
            padding_top=10,
        )
        # offset_y=0: コンテンツは上部に収まるはず
        results_no_offset, _ = filter_fitting_candidates(
            candidates=[design],
            target_width=1080, target_height=300,
            canvas_width=1080, canvas_height=1920,
            offset_y=0,
        )
        # offset_y=500: コンテンツが大幅に下にずれ、target_heightを超える
        results_large_offset, _ = filter_fitting_candidates(
            candidates=[design],
            target_width=1080, target_height=300,
            canvas_width=1080, canvas_height=1920,
            offset_y=500,
        )
        # offset_y=0 はフィットする候補を返す
        assert len(results_no_offset) == 1
        _, _, _, content_h_no = results_no_offset[0]
        assert content_h_no <= 300  # ターゲット高さ以内
        # offset_y=500 はフィットしないのでフォールバック候補が返る
        assert len(results_large_offset) >= 1
        _, _, _, content_h_large = results_large_offset[0]
        assert content_h_large > 300  # ターゲット高さを超えているフォールバック候補

    def test_generate_title_image_with_offset(self, tmp_path):
        """generate_title_imageにoffset_yを渡して画像生成できること"""
        output = tmp_path / "offset.png"
        result = generate_title_image(
            title="テスト", keywords=[], output_path=output,
            client=None, offset_y=80,
        )
        assert result is not None
        assert result.exists()
        img = Image.open(result)
        bbox = img.getbbox()
        # padding_top(60) + offset_y(80) = 140px付近からコンテンツ開始
        assert bbox[1] >= 100


class TestEvaluateCandidatesWithVision:
    """Stage 3: Vision AI評価のテスト"""

    def test_selects_best_candidate(self, tmp_path):
        """Vision AIが最適な候補を選択すること"""
        # ダミー画像を作成
        for i in range(3):
            img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
            img.save(str(tmp_path / f"c{i}.png"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps({"best_index": 1, "reason": "可読性が高い"})
            ))]
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[
                (0, tmp_path / "c0.png"),
                (1, tmp_path / "c1.png"),
                (2, tmp_path / "c2.png"),
            ],
            title="テスト",
        )
        assert result == 1

    def test_single_candidate_returns_immediately(self, tmp_path):
        """候補が1つの場合はAPIを呼ばずにそのインデックスを返すこと"""
        img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
        img.save(str(tmp_path / "single.png"))

        mock_client = MagicMock()
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[(5, tmp_path / "single.png")],
            title="テスト",
        )
        assert result == 5
        mock_client.chat.completions.create.assert_not_called()

    def test_api_failure_returns_first(self, tmp_path):
        """API失敗時に最初の候補インデックスを返すこと"""
        for i in range(2):
            img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
            img.save(str(tmp_path / f"c{i}.png"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[(0, tmp_path / "c0.png"), (1, tmp_path / "c1.png")],
            title="テスト",
        )
        assert result == 0

    def test_empty_candidates_returns_zero(self):
        """空の候補リストで0を返すこと"""
        mock_client = MagicMock()
        result = evaluate_candidates_with_vision(
            client=mock_client, candidate_images=[], title="テスト",
        )
        assert result == 0


class TestGenerateTitleImageWithTargetSize:
    """target_size指定時の3段階パイプラインのテスト"""

    def test_pipeline_with_target_size(self, tmp_path):
        """target_size指定時にパイプラインが実行されること"""
        # Stage 1: 複数候補生成
        mock_client = MagicMock()
        # 最初のAPI呼び出し: 候補生成
        candidates_response = MagicMock()
        candidates_response.choices[0].message.content = json.dumps({
            "designs": [
                {"lines": [{"segments": [{"text": "テスト", "font_size": 120}]}]},
                {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
            ]
        })
        # 2番目のAPI呼び出し: Vision AI評価
        vision_response = MagicMock()
        vision_response.choices[0].message.content = json.dumps({
            "best_index": 0, "reason": "インパクトが強い"
        })
        mock_client.chat.completions.create.side_effect = [
            candidates_response, vision_response,
        ]

        output = tmp_path / "pipeline.png"
        result = generate_title_image(
            title="テスト",
            keywords=["AI"],
            output_path=output,
            client=mock_client,
            target_size=(1080, 438),
        )
        assert result is not None
        assert result.exists()
        # キャッシュが生成されている
        assert output.with_suffix(".title.json").exists()

    def test_pipeline_fallback_to_legacy(self, tmp_path):
        """パイプライン失敗時に従来方式にフォールバックすること"""
        mock_client = MagicMock()
        # パイプライン用API呼び出しは全て失敗
        mock_client.chat.completions.create.side_effect = Exception("API error")

        output = tmp_path / "fallback_pipeline.png"
        result = generate_title_image(
            title="テスト",
            keywords=[],
            output_path=output,
            client=mock_client,
            target_size=(1080, 438),
        )
        # フォールバックデザインが使われる
        assert result is not None
        assert result.exists()

    def test_batch_with_target_size(self, tmp_path):
        """バッチ生成でtarget_size指定時にパイプラインが各タイトルに適用されること"""
        mock_client = MagicMock()

        # 各タイトルに対して2回のAPI呼び出し（候補生成 + Vision評価）
        def make_candidates_response(title):
            r = MagicMock()
            r.choices[0].message.content = json.dumps({
                "designs": [
                    {"lines": [{"segments": [{"text": title, "font_size": 100}]}]},
                ]
            })
            return r

        def make_vision_response():
            r = MagicMock()
            r.choices[0].message.content = json.dumps({
                "best_index": 0, "reason": "OK"
            })
            return r

        mock_client.chat.completions.create.side_effect = [
            make_candidates_response("A"),
            make_candidates_response("B"),
        ]

        suggestions = []
        for t in ["A", "B"]:
            s = MagicMock()
            s.title = t
            s.keywords = []
            suggestions.append(s)

        results = generate_title_images_batch(
            suggestions=suggestions,
            output_dir=tmp_path / "titles",
            client=mock_client,
            target_size=(1080, 438),
        )
        assert len(results) == 2
        assert all(p.exists() for p in results.values())


class TestVisionAIEdgeCases:
    """Vision AI評価のエッジケーステスト"""

    def test_out_of_range_best_index(self, tmp_path):
        """Vision AIが範囲外のbest_indexを返した場合にフォールバックすること"""
        for i in range(3):
            img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
            img.save(str(tmp_path / f"c{i}.png"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps({"best_index": 99, "reason": "範囲外"})
            ))]
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[
                (0, tmp_path / "c0.png"),
                (1, tmp_path / "c1.png"),
                (2, tmp_path / "c2.png"),
            ],
            title="テスト",
        )
        # 範囲外なのでフォールバック（最初の候補のインデックス）
        assert result == 0

    def test_negative_best_index(self, tmp_path):
        """Vision AIが負のbest_indexを返した場合にフォールバックすること"""
        for i in range(2):
            img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
            img.save(str(tmp_path / f"c{i}.png"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps({"best_index": -1, "reason": "負の値"})
            ))]
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[(0, tmp_path / "c0.png"), (1, tmp_path / "c1.png")],
            title="テスト",
        )
        assert result == 0


class TestFilterEdgeCases:
    """フィルタリングのエッジケーステスト"""

    def test_target_width_zero_no_crash(self):
        """target_width=0でクラッシュしないこと"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=80)])]
        )
        # target_width=0 でもゼロ除算にならないこと
        results, tmp_dirs = filter_fitting_candidates(
            candidates=[design],
            target_width=0,
            target_height=438,
            canvas_width=1080,
            canvas_height=1920,
        )
        # クラッシュせず結果が返ること
        assert isinstance(results, list)
        assert isinstance(tmp_dirs, list)


class TestPipelineEmptyResults:
    """パイプラインの空結果テスト"""

    def test_stage1_all_invalid_candidates(self, tmp_path):
        """Stage 1で全候補がバリデーション失敗した場合のフォールバック"""
        mock_client = MagicMock()
        # 全候補が文字不一致
        candidates_response = MagicMock()
        candidates_response.choices[0].message.content = json.dumps({
            "designs": [
                {"lines": [{"segments": [{"text": "改変A", "font_size": 120}]}]},
                {"lines": [{"segments": [{"text": "改変B", "font_size": 90}]}]},
            ]
        })
        mock_client.chat.completions.create.side_effect = [candidates_response]

        output = tmp_path / "empty_stage1.png"
        result = generate_title_image(
            title="テスト",
            keywords=[],
            output_path=output,
            client=mock_client,
            target_size=(1080, 438),
        )
        # パイプライン失敗→従来方式フォールバックで画像は生成される
        assert result is not None
        assert result.exists()

    def test_batch_with_target_size_and_cache(self, tmp_path):
        """バッチ生成でtarget_size指定+キャッシュ済みの場合"""
        output_dir = tmp_path / "titles"
        output_dir.mkdir()

        # キャッシュを作成
        cache_data = json.dumps({
            "lines": [{"segments": [{"text": "キャッシュ", "font_size": 72}]}],
            "line_spacing": 10,
            "padding_top": 60,
        }, ensure_ascii=False)
        (output_dir / "01_キャッシュ.title.json").write_text(cache_data)

        suggestions = []
        s = MagicMock()
        s.title = "キャッシュ"
        s.keywords = []
        suggestions.append(s)

        mock_client = MagicMock()
        results = generate_title_images_batch(
            suggestions=suggestions,
            output_dir=output_dir,
            client=mock_client,
            target_size=(1080, 438),
        )
        # キャッシュがあるのでAI呼び出しなしで画像生成
        assert 1 in results
        assert results[1].exists()
        # パイプラインAPI呼び出しは不要
        mock_client.chat.completions.create.assert_not_called()
