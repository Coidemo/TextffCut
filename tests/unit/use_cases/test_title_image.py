"""タイトル画像生成のユニットテスト"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from use_cases.ai.title_image_generator import (
    _DARK_TEXT_LUMINANCE,
    TitleImageDesign,
    TitleLine,
    TitleTextSegment,
    _contrast_ratio,
    _enforce_line_break,
    _ensure_contrast,
    _ensure_fit_height,
    _force_outline_style,
    _get_segment_luminance,
    _hex_to_rgb,
    _parse_design_json,
    _relative_luminance,
    _safe_int,
    _save_design_cache,
    _scale_outline,
    _shrink_particles,
    _snap_lines_to_word_boundaries,
    _split_title,
    _strip_punctuation_from_design,
    _strip_title_punctuation,
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
        title = "これは長い文章で「テスト」を含む例です"
        result = _split_title(title)
        assert len(result) >= 2
        # 句読点分割でも文字が欠落しないこと
        assert "".join(result) == title

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

    def test_word_boundary_snap_no_punctuation(self):
        """句読点なし長文を GiNZA 単語境界で分割し、単語が分断されないこと。

        現象再現: 「親の不仲によるストレスへの対処法」(16字) を均等分割すると
        「親の不仲によるス / トレスへの対処法」となり「ストレス」が分断される。
        新ロジックで GiNZA 境界にスナップされ、ストレスを温存することを期待。
        """
        title = "親の不仲によるストレスへの対処法"
        result = _split_title(title, max_lines=2)
        assert "".join(result) == title  # 文字欠落なし
        assert len(result) == 2
        # 「ストレス」がどの行にも完全な形で含まれること = 分断されてない
        assert any("ストレス" in part for part in result), f"ストレスが分断されました: {result}"

    def test_extreme_word_bounds_falls_back_to_equal_split(self, monkeypatch):
        """中間点から離れすぎた snap 候補は均等分割に fallback すること。

        word_bounds が極端に偏ってる場合 (例: [3, 14] for 16字) に snap すると
        「親の」(2字) / 「不仲によるストレスへの対処法」(14字) のように極端
        アンバランスを生むため、距離 guard で fallback する。
        """
        from core.japanese_line_break import JapaneseLineBreakRules

        title = "親の不仲によるストレスへの対処法"  # 16 字
        # 中間点 8 から離れた境界しか返さない mock
        monkeypatch.setattr(
            JapaneseLineBreakRules,
            "get_word_boundaries",
            classmethod(lambda cls, text: [3, 14]),
        )
        result = _split_title(title, max_lines=2)
        assert "".join(result) == title  # 文字欠落なし
        assert len(result) == 2
        # snap せず均等分割 (8 字ずつ) になる
        assert len(result[0]) == 8 and len(result[1]) == 8


class TestSnapLinesToWordBoundaries:
    def _line(self, text: str) -> TitleLine:
        return TitleLine(segments=[TitleTextSegment(text=text)])

    def test_single_line_noop(self):
        design = TitleImageDesign(lines=[self._line("親の不仲によるストレス")])
        result = _snap_lines_to_word_boundaries(design)
        assert result is design  # 1 行は変更なし

    def test_snap_word_break(self):
        """中途半端な分割を単語境界にスナップする。"""
        design = TitleImageDesign(
            lines=[self._line("親の不仲によるス"), self._line("トレスへの対処法")]
        )
        result = _snap_lines_to_word_boundaries(design)
        recombined = "".join(seg.text for line in result.lines for seg in line.segments)
        assert recombined == "親の不仲によるストレスへの対処法"
        # 全文に「ストレス」を含む以上、いずれか 1 行に完全な形で含まれること
        line_texts = ["".join(seg.text for seg in line.segments) for line in result.lines]
        assert any("ストレス" in t for t in line_texts), (
            f"ストレスが行を跨いで分断されました: {line_texts}"
        )

    def test_already_at_word_boundary_noop(self):
        """既に単語境界に乗ってる場合は変更しない。"""
        design = TitleImageDesign(lines=[self._line("親の不仲による"), self._line("ストレスへの対処法")])
        result = _snap_lines_to_word_boundaries(design)
        # 同じ design がそのまま返ってくる (needs_snap=False で短絡)
        assert result is design

    def test_preserves_segment_styles_after_snap(self):
        """snap 後も各 segment の色・サイズ・gradient・weight が保持されること。

        AI が複数色 segment で返した行を snap で再構築する際、元 segment の
        スタイル情報がコピーされず欠落するとデザインが破綻するため検証。
        """
        # 「親の不仲によるス | トレスへの対処法」を 2 色 + 2 行で AI が返した想定
        # 期待: snap で「親の不仲による | ストレスへの対処法」に再構築されても
        # 「親の不仲」(red, size 100) と「によるス」(blue, size 80) の色情報が
        # 維持される
        line1 = TitleLine(
            segments=[
                TitleTextSegment(text="親の不仲", font_size=100, color="#FF0000", weight="Bd"),
                TitleTextSegment(text="によるス", font_size=80, color="#0000FF", weight="Rg"),
            ]
        )
        line2 = TitleLine(
            segments=[TitleTextSegment(text="トレスへの対処法", font_size=80, color="#00FF00")]
        )
        design = TitleImageDesign(lines=[line1, line2])
        result = _snap_lines_to_word_boundaries(design)

        # 全文の合計テキストが保たれる
        all_text = "".join(seg.text for line in result.lines for seg in line.segments)
        assert all_text == "親の不仲によるストレスへの対処法"

        # 各 segment の色がいずれか保持されている (snap で文字位置がシフト
        # しても、各文字の元の色は維持される)
        all_colors = {seg.color for line in result.lines for seg in line.segments}
        assert "#FF0000" in all_colors  # 親の不仲 の赤
        assert "#0000FF" in all_colors  # によるス の青
        assert "#00FF00" in all_colors  # トレスへの対処法 の緑

        # font_size も同様に保持
        all_sizes = {seg.font_size for line in result.lines for seg in line.segments}
        assert 100 in all_sizes
        assert 80 in all_sizes


class TestStripTitlePunctuation:
    def test_strip_japanese_punctuation(self):
        assert _strip_title_punctuation("これは、テスト。") == "これはテスト"
        assert _strip_title_punctuation("本当！？") == "本当"
        assert _strip_title_punctuation("AIの真実，それは．") == "AIの真実それは"

    def test_strip_halfwidth_punctuation(self):
        assert _strip_title_punctuation("Hello, world.") == "Hello world"
        assert _strip_title_punctuation("Why?") == "Why"

    def test_no_punctuation_unchanged(self):
        assert _strip_title_punctuation("親の不仲によるストレス") == "親の不仲によるストレス"

    def test_brackets_preserved(self):
        # 括弧は強調装飾として残す
        assert _strip_title_punctuation("「衝撃」の真実") == "「衝撃」の真実"


class TestStripPunctuationFromDesign:
    def _line(self, text: str) -> TitleLine:
        return TitleLine(segments=[TitleTextSegment(text=text)])

    def test_strip_from_segments(self):
        design = TitleImageDesign(lines=[self._line("これは、"), self._line("テスト。")])
        result = _strip_punctuation_from_design(design)
        all_text = "".join(seg.text for line in result.lines for seg in line.segments)
        assert all_text == "これはテスト"

    def test_punctuation_only_segment_removed(self):
        """句読点のみの segment は削除されること。"""
        line = TitleLine(
            segments=[
                TitleTextSegment(text="本当", color="#FF0000"),
                TitleTextSegment(text="！？", color="#0000FF"),  # 句読点のみ
                TitleTextSegment(text="です", color="#00FF00"),
            ]
        )
        design = TitleImageDesign(lines=[line])
        result = _strip_punctuation_from_design(design)
        assert len(result.lines) == 1
        assert len(result.lines[0].segments) == 2
        all_text = "".join(seg.text for seg in result.lines[0].segments)
        assert all_text == "本当です"

    def test_all_empty_returns_original(self):
        """全て句読点になった場合は元 design を返す (安全側)。"""
        design = TitleImageDesign(lines=[self._line("、。!?")])
        result = _strip_punctuation_from_design(design)
        # 全消えで元 design がそのまま返る
        assert result is design


class TestEnforceLineBreakEndToEnd:
    def test_long_single_line_split_no_word_break(self):
        """1 行で 11字超の長文を強制分割した結果、単語が分断されないこと。"""
        title = "親の不仲によるストレスへの対処法"
        design = TitleImageDesign(lines=[TitleLine(segments=[TitleTextSegment(text=title)])])
        broken = _enforce_line_break(design)
        snapped = _snap_lines_to_word_boundaries(broken)
        assert len(snapped.lines) >= 2
        recombined = "".join(seg.text for line in snapped.lines for seg in line.segments)
        assert recombined == title
        # 「ストレス」が含まれている以上、いずれか 1 行に完全な形で存在すること
        line_texts = ["".join(seg.text for seg in line.segments) for line in snapped.lines]
        assert any("ストレス" in t for t in line_texts), (
            f"ストレスが行を跨いで分断: {line_texts}"
        )


class TestParseDesignJson:
    def test_valid_json(self):
        raw = {
            "lines": [
                {
                    "segments": [{"text": "テスト", "font_size": 80, "color": "#FFFFFF", "weight": "Eb"}],
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
        raw = {"lines": [{"segments": [{"text": "グラデ", "gradient": ["#FFD700", "#FF6600"]}]}]}
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].gradient == ("#FFD700", "#FF6600")

    def test_clamp_values(self):
        raw = {
            "lines": [
                {
                    "segments": [{"text": "大きすぎ", "font_size": 300}],
                    "outer_outline_width": 50,
                }
            ],
            "padding_top": 999,
        }
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].font_size == 220  # clamped upper
        assert design.lines[0].outer_outline_width == 10  # clamped
        assert design.padding_top == 200  # clamped

    def test_clamp_lower_bound(self):
        """font_sizeが下限(80)にクランプされること"""
        raw = {
            "lines": [
                {
                    "segments": [{"text": "小さすぎ", "font_size": 10}],
                }
            ],
        }
        design = _parse_design_json(raw)
        assert design.lines[0].segments[0].font_size == 80  # clamped lower

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
        design = TitleImageDesign(lines=[TitleLine(segments=[TitleTextSegment(text="あ" * 30, font_size=120)])])
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
                    "segments": [{"text": "キャッシュ", "font_size": 72, "color": "#FFFFFF", "weight": "Eb"}],
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
            json.dumps(
                {
                    "lines": [{"segments": [{"text": "テスト", "font_size": 80}]}],
                    "line_spacing": 10,
                    "padding_top": 60,
                }
            )
        )
        design = design_title_layout(
            client=mock_client,
            title="テスト",
            keywords=["AI"],
        )
        assert len(design.lines) == 1
        assert design.lines[0].segments[0].text == "テスト"
        mock_client.chat.completions.create.assert_called_once()

    def test_title_mismatch_raises_error(self):
        """AIがタイトル文字を変更した場合にValueErrorが発生すること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps(
                {
                    "lines": [{"segments": [{"text": "改変された", "font_size": 80}]}],
                }
            )
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
            json.dumps(
                {
                    "lines": [{"segments": [{"text": "OK", "font_size": 72}]}],
                }
            )
        )
        design_title_layout(
            client=mock_client,
            title="OK",
            keywords=[],
            prompt_template="Custom: {TITLE} {KEYWORDS} {FRAME_COLORS} {JSON_SCHEMA} {ORIENTATION}",
        )
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Custom:" in prompt

    def test_frame_colors_in_prompt(self):
        """frame_colorsがプロンプトに含まれること"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps(
                {
                    "lines": [{"segments": [{"text": "色", "font_size": 72}]}],
                }
            )
        )
        design_title_layout(
            client=mock_client,
            title="色",
            keywords=[],
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
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "タイトルA", "font_size": 80}]}]},
                        {"lines": [{"segments": [{"text": "タイトルB", "font_size": 72}]}]},
                    ]
                }
            )
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
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "OK", "font_size": 80}]}]},
                        {"lines": []},  # 空行 → ValueError
                    ]
                }
            )
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
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "改変", "font_size": 80}]}]},
                    ]
                }
            )
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
                client=mock_client,
                titles=["テスト"],
                keywords_list=[[]],
            )

    def test_fewer_designs_than_titles(self):
        """AIの返すデザイン数がタイトル数より少ない場合"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._mock_response(
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "A", "font_size": 72}]}]},
                    ]
                }
            )
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
        cache_data = json.dumps(
            {
                "lines": [{"segments": [{"text": "キャッシュ済み", "font_size": 72}]}],
                "line_spacing": 10,
                "padding_top": 60,
            },
            ensure_ascii=False,
        )
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
            lines=[
                TitleLine(
                    segments=[TitleTextSegment(text="テスト", font_size=80, color="#FF0000", weight="Bd")],
                    outer_outline_width=6,
                    inner_outline_width=3,
                    inner_outline_color="#FFFFFF",
                )
            ],
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
            lines=[TitleLine(segments=[TitleTextSegment(text="グラデ", gradient=("#FFD700", "#FF6600"))])]
        )
        cache_path = tmp_path / "grad.title.json"
        _save_design_cache(design, cache_path)

        raw = json.loads(cache_path.read_text())
        reloaded = _parse_design_json(raw)
        assert reloaded.lines[0].segments[0].gradient == ("#FFD700", "#FF6600")

    def test_null_gradient_roundtrip(self, tmp_path):
        """gradient=Noneがラウンドトリップで保持されること"""
        design = TitleImageDesign(lines=[TitleLine(segments=[TitleTextSegment(text="普通")])])
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
            title="テストタイトル",
            keywords=[],
            output_path=output,
            client=None,
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
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=json.dumps(
                            {
                                "lines": [
                                    {
                                        "segments": [
                                            {
                                                "text": "衝撃",
                                                "font_size": 90,
                                                "gradient": ["#FFD700", "#FF6600"],
                                                "weight": "Eb",
                                            },
                                            {"text": "の事実", "font_size": 60, "color": "#FFFFFF", "weight": "Bd"},
                                        ],
                                        "outer_outline_width": 8,
                                        "inner_outline_width": 4,
                                    },
                                ],
                                "line_spacing": 12,
                                "padding_top": 80,
                            }
                        )
                    )
                )
            ]
        )
        output = tmp_path / "e2e.png"
        result = generate_title_image(
            title="衝撃の事実",
            keywords=["衝撃"],
            output_path=output,
            client=mock_client,
            orientation="vertical",
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
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "テスト", "font_size": 160}]}]},
                        {"lines": [{"segments": [{"text": "テスト", "font_size": 120}]}]},
                        {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
                    ]
                }
            )
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
            json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": "テスト", "font_size": 160}]}]},
                        {"lines": [{"segments": [{"text": "改変された", "font_size": 120}]}]},
                        {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
                    ]
                }
            )
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
                client=mock_client,
                title="テスト",
                keywords=[],
                target_size=(1080, 438),
            )


class TestFilterFittingCandidates:
    """Stage 2: フィルタリングのテスト"""

    def test_filters_by_height(self, tmp_path):
        """ターゲット高さを超える候補がフィルタされること"""
        # 小さいフォントの候補（収まる）
        small_design = TitleImageDesign(lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=80)])])
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
            target_width=1080,
            target_height=300,
            canvas_width=1080,
            canvas_height=1920,
            offset_y=0,
        )
        # offset_y=500: コンテンツが大幅に下にずれ、target_heightを超える
        results_large_offset, _ = filter_fitting_candidates(
            candidates=[design],
            target_width=1080,
            target_height=300,
            canvas_width=1080,
            canvas_height=1920,
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
            title="テスト",
            keywords=[],
            output_path=output,
            client=None,
            offset_y=80,
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
            choices=[MagicMock(message=MagicMock(content=json.dumps({"best_index": 1, "reason": "可読性が高い"})))]
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
            client=mock_client,
            candidate_images=[],
            title="テスト",
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
        candidates_response.choices[0].message.content = json.dumps(
            {
                "designs": [
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 120}]}]},
                    {"lines": [{"segments": [{"text": "テスト", "font_size": 90}]}]},
                ]
            }
        )
        # 2番目のAPI呼び出し: Vision AI評価
        vision_response = MagicMock()
        vision_response.choices[0].message.content = json.dumps({"best_index": 0, "reason": "インパクトが強い"})
        mock_client.chat.completions.create.side_effect = [
            candidates_response,
            vision_response,
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
            r.choices[0].message.content = json.dumps(
                {
                    "designs": [
                        {"lines": [{"segments": [{"text": title, "font_size": 100}]}]},
                    ]
                }
            )
            return r

        def make_vision_response():
            r = MagicMock()
            r.choices[0].message.content = json.dumps({"best_index": 0, "reason": "OK"})
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
            choices=[MagicMock(message=MagicMock(content=json.dumps({"best_index": 99, "reason": "範囲外"})))]
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
            choices=[MagicMock(message=MagicMock(content=json.dumps({"best_index": -1, "reason": "負の値"})))]
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[(0, tmp_path / "c0.png"), (1, tmp_path / "c1.png")],
            title="テスト",
        )
        assert result == 0

    def test_non_json_response_falls_back(self, tmp_path):
        """Vision AIが非JSONレスポンスを返した場合にフォールバックすること"""
        for i in range(2):
            img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
            img.save(str(tmp_path / f"c{i}.png"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="候補1が最適です"))]  # JSONではない自由文
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[(0, tmp_path / "c0.png"), (1, tmp_path / "c1.png")],
            title="テスト",
        )
        # json.loads失敗 → except → フォールバック
        assert result == 0

    def test_partial_encode_failure_correct_index(self, tmp_path):
        """一部画像のbase64エンコード失敗時にインデックスがずれないこと"""
        # 画像0と画像2は正常、画像1は存在しない
        img = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
        img.save(str(tmp_path / "c0.png"))
        img.save(str(tmp_path / "c2.png"))
        # c1.pngは作成しない（base64エンコード失敗を再現）

        mock_client = MagicMock()
        # Vision AIは2枚目（表示順index=1）を選択
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({"best_index": 1, "reason": "2枚目が良い"})))]
        )
        result = evaluate_candidates_with_vision(
            client=mock_client,
            candidate_images=[
                (0, tmp_path / "c0.png"),
                (1, tmp_path / "c1.png"),  # 存在しない → エンコード失敗
                (2, tmp_path / "c2.png"),
            ],
            title="テスト",
        )
        # AIは表示された2枚のうちindex=1（=c2.png、元インデックス2）を選択
        assert result == 2  # c1.pngではなくc2.pngの元インデックスが返る


class TestFilterEdgeCases:
    """フィルタリングのエッジケーステスト"""

    def test_target_width_zero_no_crash(self):
        """target_width=0でクラッシュしないこと"""
        design = TitleImageDesign(lines=[TitleLine(segments=[TitleTextSegment(text="テスト", font_size=80)])])
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
        candidates_response.choices[0].message.content = json.dumps(
            {
                "designs": [
                    {"lines": [{"segments": [{"text": "改変A", "font_size": 120}]}]},
                    {"lines": [{"segments": [{"text": "改変B", "font_size": 90}]}]},
                ]
            }
        )
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
        cache_data = json.dumps(
            {
                "lines": [{"segments": [{"text": "キャッシュ", "font_size": 72}]}],
                "line_spacing": 10,
                "padding_top": 60,
            },
            ensure_ascii=False,
        )
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


class TestXmlAttrEscape:
    """XML属性値のダブルクォートエスケープテスト"""

    def test_xml_attr_escapes_double_quotes(self):
        """_xml_attrがダブルクォートを&quot;にエスケープすること"""
        from core.export import _xml_attr

        assert _xml_attr('test"value') == "test&quot;value"
        assert _xml_attr("no quotes") == "no quotes"
        assert _xml_attr('<script>"alert"</script>') == "&lt;script&gt;&quot;alert&quot;&lt;/script&gt;"

    def test_xml_attr_escapes_standard_entities(self):
        """_xml_attrが標準エンティティもエスケープすること"""
        from core.export import _xml_attr

        assert "&amp;" in _xml_attr("a&b")
        assert "&lt;" in _xml_attr("a<b")
        assert "&gt;" in _xml_attr("a>b")


class TestRelativeLuminance:
    """WCAG 2.0 相対輝度のテスト"""

    def test_black(self):
        assert _relative_luminance("#000000") == pytest.approx(0.0)

    def test_white(self):
        assert _relative_luminance("#FFFFFF") == pytest.approx(1.0)

    def test_red(self):
        lum = _relative_luminance("#FF0000")
        assert 0.2 < lum < 0.22

    def test_green(self):
        lum = _relative_luminance("#00FF00")
        assert 0.71 < lum < 0.73

    def test_blue(self):
        lum = _relative_luminance("#0000FF")
        assert 0.07 < lum < 0.08

    def test_mid_gray(self):
        lum = _relative_luminance("#808080")
        assert 0.2 < lum < 0.25


class TestContrastRatio:
    """WCAG 2.0 コントラスト比のテスト"""

    def test_black_white(self):
        assert _contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)

    def test_white_black(self):
        """順序に関係なく同じ結果"""
        assert _contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)

    def test_same_color(self):
        assert _contrast_ratio("#FF8800", "#FF8800") == pytest.approx(1.0)

    def test_low_contrast_orange_on_orange(self):
        """オレンジ背景にオレンジ縁取り — 低コントラスト"""
        ratio = _contrast_ratio("#e06000", "#e0c040")
        assert ratio < 3.0

    def test_high_contrast_black_on_orange(self):
        """オレンジ背景に黒縁取り — 高コントラスト"""
        ratio = _contrast_ratio("#000000", "#e0c040")
        assert ratio > 3.0


class TestForceOutlineStyle:
    """白外縁強制 + 内縁色適応のテスト"""

    def _make_design(
        self, text_color="#000000", gradient=None, weight="Rg", outline_color="#000000", outline_width=4, inner_width=0
    ):
        return TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(
                            text="テスト",
                            color=text_color,
                            gradient=gradient,
                            weight=weight,
                        )
                    ],
                    outer_outline_color=outline_color,
                    outer_outline_width=outline_width,
                    inner_outline_width=inner_width,
                ),
            ],
        )

    def test_outer_always_white(self):
        """外縁は常に白に強制される"""
        result = _force_outline_style(self._make_design(outline_color="#FF0000"))
        assert result.lines[0].outer_outline_color == "#FFFFFF"

    def test_outer_width_at_least_10(self):
        """外縁幅は最低10"""
        result = _force_outline_style(self._make_design(outline_width=4))
        assert result.lines[0].outer_outline_width >= 10

    def test_outer_width_preserved_if_larger(self):
        """外縁幅が10超なら保持"""
        result = _force_outline_style(self._make_design(outline_width=15))
        assert result.lines[0].outer_outline_width == 15

    def test_dark_text_no_inner_outline(self):
        """暗いテキスト（黒系）→ 内縁不要"""
        result = _force_outline_style(self._make_design(text_color="#000000"))
        assert result.lines[0].inner_outline_width == 0

    def test_light_text_gets_black_inner(self):
        """明るいテキスト（白系）→ 黒内縁"""
        result = _force_outline_style(self._make_design(text_color="#FFFFFF"))
        assert result.lines[0].inner_outline_color == "#000000"
        assert result.lines[0].inner_outline_width >= 6

    def test_gradient_gets_black_inner(self):
        """グラデーション → 黒内縁"""
        result = _force_outline_style(self._make_design(gradient=("#FF0000", "#FFFF00")))
        assert result.lines[0].inner_outline_color == "#000000"
        assert result.lines[0].inner_outline_width >= 6

    def test_all_weights_forced_to_eb(self):
        """全セグメントのウェイトがEbに統一される"""
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(text="A", weight="Th"),
                        TitleTextSegment(text="B", weight="Rg"),
                        TitleTextSegment(text="C", weight="Bd"),
                    ]
                ),
            ]
        )
        result = _force_outline_style(design)
        for seg in result.lines[0].segments:
            assert seg.weight == "Eb"

    def test_original_not_mutated(self):
        """元のデザインは変更されない"""
        design = self._make_design(outline_color="#FF0000", weight="Rg")
        _force_outline_style(design)
        assert design.lines[0].outer_outline_color == "#FF0000"
        assert design.lines[0].segments[0].weight == "Rg"

    def test_colorful_text_gets_inner_outline(self):
        """カラーテキスト（中間輝度）→ 黒内縁"""
        result = _force_outline_style(self._make_design(text_color="#FF4444"))
        assert result.lines[0].inner_outline_color == "#000000"
        assert result.lines[0].inner_outline_width >= 6


class TestShrinkParticles:
    """助詞縮小のテスト"""

    def _make_design(self, text="テストは成功です", font_size=100):
        return TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[TitleTextSegment(text=text, font_size=font_size)],
                ),
            ],
        )

    def test_particle_shrunk(self):
        """助詞のfont_sizeが80%に縮小される"""
        result = _shrink_particles(self._make_design("テストは成功"))
        texts = [seg.text for seg in result.lines[0].segments]
        joined = "".join(texts)
        assert joined == "テストは成功"
        # 「は」を含むセグメントが80%
        for seg in result.lines[0].segments:
            if "は" in seg.text:
                assert seg.font_size == 80  # 100 * 0.8

    def test_non_particle_unchanged(self):
        """非助詞のfont_sizeは変更されない"""
        result = _shrink_particles(self._make_design("テストは成功"))
        for seg in result.lines[0].segments:
            if "は" not in seg.text:
                assert seg.font_size == 100

    def test_all_weights_eb(self):
        """全セグメント（助詞含む）のweightがEb"""
        result = _shrink_particles(self._make_design("テストは成功"))
        for seg in result.lines[0].segments:
            assert seg.weight == "Eb"

    def test_text_integrity(self):
        """全セグメントのテキスト結合が元テキストと一致"""
        original = "SNSで無難な発言はもう通用しない"
        result = _shrink_particles(self._make_design(original))
        joined = "".join(seg.text for seg in result.lines[0].segments)
        assert joined == original

    def test_empty_line_unchanged(self):
        """空行はそのまま返す"""
        design = TitleImageDesign(
            lines=[TitleLine(segments=[TitleTextSegment(text="")])],
        )
        result = _shrink_particles(design)
        assert result.lines[0].segments[0].text == ""

    def test_no_mutation(self):
        """元のデザインは変更されない"""
        design = self._make_design("テストは成功")
        original_size = design.lines[0].segments[0].font_size
        _shrink_particles(design)
        assert design.lines[0].segments[0].font_size == original_size

    def test_ginza_import_failure_skips(self):
        """GiNZA未インストール時はスキップされる"""
        design = self._make_design("テストは成功")
        with patch.dict("sys.modules", {"core.japanese_line_break": None}):
            result = _shrink_particles(design)
        # 元のセグメント数・テキストのまま
        assert len(result.lines[0].segments) == 1
        assert result.lines[0].segments[0].text == "テストは成功"

    def test_preserves_color_and_gradient(self):
        """セグメントのcolor/gradientが保持される"""
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(
                            text="テストは成功",
                            font_size=100,
                            color="#FF0000",
                            gradient=("#FF0000", "#FFFF00"),
                        )
                    ],
                ),
            ],
        )
        result = _shrink_particles(design)
        for seg in result.lines[0].segments:
            assert seg.color == "#FF0000"
            assert seg.gradient == ("#FF0000", "#FFFF00")


class TestEnsureContrast:
    """コントラスト自動補正のテスト"""

    def _make_design(self, outline_color="#e06000", text_color="#FFFFFF", gradient=None):
        return TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[TitleTextSegment(text="テスト", color=text_color, gradient=gradient)],
                    outer_outline_color=outline_color,
                    outer_outline_width=8,
                ),
            ],
        )

    def test_outline_forced_to_white(self):
        """_ensure_contrast内で_force_outline_styleが適用され、外縁は白になる"""
        design = self._make_design(outline_color="#e06000")
        frame_colors = ["#e0c040", "#e08000", "#e06000"]
        result = _ensure_contrast(design, frame_colors)
        assert result.lines[0].outer_outline_color == "#FFFFFF"

    def test_high_contrast_outline_forced_to_white(self):
        """入力に関わらず外縁は白に強制される"""
        design = self._make_design(outline_color="#000000")
        frame_colors = ["#e0c040", "#e08000"]
        result = _ensure_contrast(design, frame_colors)
        assert result.lines[0].outer_outline_color == "#FFFFFF"

    def test_white_text_on_white_outline_corrected(self):
        """白外縁に白テキストが同化する場合、テキスト色が補正される"""
        design = self._make_design(outline_color="#FFFFFF", text_color="#FFFFFF")
        frame_colors = ["#101010"]
        result = _ensure_contrast(design, frame_colors)
        assert result.lines[0].segments[0].color == "#000000"

    def test_empty_frame_colors_no_change(self):
        """frame_colorsが空ならそのまま返す"""
        design = self._make_design(outline_color="#e06000")
        result = _ensure_contrast(design, [])
        assert result.lines[0].outer_outline_color == "#e06000"

    def test_original_design_not_mutated(self):
        """元のデザインオブジェクトは変更されない"""
        design = self._make_design(outline_color="#FFFFFF", text_color="#FFFFFF")
        frame_colors = ["#101010"]
        result = _ensure_contrast(design, frame_colors)
        assert design.lines[0].segments[0].color == "#FFFFFF"
        assert result.lines[0].segments[0].color == "#000000"


class TestEnsureFitHeight:
    """高さ制限の自動補正テスト"""

    def _make_design(self, font_size=200, num_lines=3):
        lines = []
        for _ in range(num_lines):
            lines.append(
                TitleLine(
                    segments=[TitleTextSegment(text="テスト", font_size=font_size)],
                    outer_outline_color="#000000",
                    outer_outline_width=8,
                ),
            )
        return TitleImageDesign(lines=lines, line_spacing=14, padding_top=60)

    def test_oversized_design_is_scaled_down(self, tmp_path):
        """高さ超過のデザインが縮小される"""
        design = self._make_design(font_size=200, num_lines=3)
        result = _ensure_fit_height(design, target_height=400, canvas_width=540, canvas_height=960)
        # フォントサイズが元より小さくなる
        for line in result.lines:
            for seg in line.segments:
                assert seg.font_size < 200

    def test_small_design_unchanged(self, tmp_path):
        """高さ以内のデザインは変更されない"""
        design = self._make_design(font_size=60, num_lines=1)
        result = _ensure_fit_height(design, target_height=400, canvas_width=540, canvas_height=960)
        assert result.lines[0].segments[0].font_size == 60

    def test_original_design_not_mutated(self, tmp_path):
        """元のデザインオブジェクトは変更されない"""
        design = self._make_design(font_size=200, num_lines=3)
        _ensure_fit_height(design, target_height=400, canvas_width=540, canvas_height=960)
        assert design.lines[0].segments[0].font_size == 200


class TestGetSegmentLuminance:
    """セグメント輝度計算のテスト"""

    def test_black_segment(self):
        """黒セグメントの輝度がしきい値以下"""
        seg = TitleTextSegment(text="テスト", color="#000000")
        assert _get_segment_luminance(seg) < _DARK_TEXT_LUMINANCE

    def test_white_segment(self):
        """白セグメントの輝度がしきい値超"""
        seg = TitleTextSegment(text="テスト", color="#FFFFFF")
        assert _get_segment_luminance(seg) > _DARK_TEXT_LUMINANCE

    def test_gradient_uses_max(self):
        """グラデーションでは最大輝度を返す"""
        seg = TitleTextSegment(text="テスト", gradient=("#000000", "#FFFFFF"))
        assert _get_segment_luminance(seg) == pytest.approx(1.0)

    def test_colorful_segment(self):
        """カラーセグメント（赤系）はしきい値超"""
        seg = TitleTextSegment(text="テスト", color="#FF4444")
        assert _get_segment_luminance(seg) > _DARK_TEXT_LUMINANCE

    def test_dark_red(self):
        """暗い赤はしきい値以下"""
        seg = TitleTextSegment(text="テスト", color="#1A0000")
        assert _get_segment_luminance(seg) < _DARK_TEXT_LUMINANCE

    def test_empty_color_defaults_bright(self):
        """空文字列colorは明るい扱い（安全側）"""
        seg = TitleTextSegment(text="テスト", color="")
        assert _get_segment_luminance(seg) == 1.0

    def test_non_hex_color_defaults_bright(self):
        """非hex colorは明るい扱い（安全側）"""
        seg = TitleTextSegment(text="テスト", color="red")
        assert _get_segment_luminance(seg) == 1.0


class TestMixedColorLineInnerOutline:
    """同一行にカラー文字と黒文字が混在する場合のテスト"""

    def test_dark_segment_inner_outline_skipped_in_render(self, tmp_path):
        """黒文字セグメントの内縁がスキップされ、画像が正常に生成されること

        render_title_image() が内部で _force_outline_style() を適用するため、
        元のデザインをそのまま渡して end-to-end で検証する。
        """
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(text="家族と", color="#000000", font_size=120),
                        TitleTextSegment(text="無理に", color="#FF4444", font_size=120),
                    ],
                    outer_outline_color="#000000",
                    outer_outline_width=8,
                )
            ]
        )
        # 行レベルでは内縁が有効になることを事前確認
        forced = _force_outline_style(design)
        assert forced.lines[0].inner_outline_width >= 6

        # 元のデザインを直接渡す（render内部でforce_outline_style適用）
        output = tmp_path / "mixed.png"
        render_title_image(design, output, width=540, height=960)
        img = Image.open(output)
        assert img.getbbox() is not None

    def test_force_outline_line_level_still_works(self):
        """行レベルの内縁判定は従来通り動作すること"""
        # 全セグメントが明るい → 行全体に内縁
        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[
                        TitleTextSegment(text="テスト", color="#FFFFFF"),
                        TitleTextSegment(text="です", color="#FFFF00"),
                    ],
                )
            ]
        )
        result = _force_outline_style(design)
        assert result.lines[0].inner_outline_width >= 6
        assert result.lines[0].inner_outline_color == "#000000"


class TestDropShadow:
    """ドロップシャドウのテスト"""

    def _render_with_layers(self, tmp_path, filename, layers):
        """指定レイヤーのみで描画し、bboxを返すヘルパー"""
        from use_cases.ai.title_image_generator import (
            _draw_segment,
            _force_outline_style,
            _scale_outline,
            _shrink_particles,
            find_font,
        )

        design = TitleImageDesign(
            lines=[
                TitleLine(
                    segments=[TitleTextSegment(text="影Test", font_size=100)],
                    outer_outline_width=6,
                )
            ],
            padding_top=20,
        )
        design = _force_outline_style(design)
        design = _shrink_particles(design)

        w, h = 540, 300
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        line = design.lines[0]
        seg = line.segments[0]
        font_path = find_font(seg.weight)
        font = ImageFont.truetype(font_path, seg.font_size) if font_path else ImageFont.load_default(size=seg.font_size)
        bbox = font.getbbox(seg.text)
        seg_w = bbox[2] - bbox[0]
        ascent = -bbox[1]

        margin_x = 40
        usable_width = w - margin_x * 2
        x = margin_x + (usable_width - seg_w) // 2
        y = design.padding_top + ascent
        actual_size = font.size
        outer_w = _scale_outline(line.outer_outline_width, actual_size)
        inner_w = _scale_outline(line.inner_outline_width, actual_size)

        _draw_segment(
            img=img,
            draw=draw,
            text=seg.text,
            xy=(x, y),
            font=font,
            color=seg.color,
            gradient=seg.gradient,
            outer_outline_color=line.outer_outline_color,
            outer_outline_width=outer_w,
            inner_outline_color=line.inner_outline_color,
            inner_outline_width=inner_w,
            layers=frozenset(layers),
        )
        return img.getbbox()

    def test_shadow_extends_bounding_box(self, tmp_path):
        """シャドウにより非透過ピクセルの範囲がオフセット分広がること"""
        bbox_no_shadow = self._render_with_layers(tmp_path, "no_shadow", {"outer", "inner", "text"})
        bbox_with_shadow = self._render_with_layers(tmp_path, "with_shadow", {"shadow", "outer", "inner", "text"})

        assert bbox_no_shadow is not None
        assert bbox_with_shadow is not None
        # シャドウありの方が右端・下端が広がっている
        assert bbox_with_shadow[2] > bbox_no_shadow[2]
        assert bbox_with_shadow[3] > bbox_no_shadow[3]

    def test_shadow_only_produces_pixels(self, tmp_path):
        """shadowレイヤーのみでもピクセルが描画されること"""
        bbox_shadow_only = self._render_with_layers(tmp_path, "shadow_only", {"shadow"})
        assert bbox_shadow_only is not None


class TestFillMaskHoles:
    """_fill_mask_holes() の挙動テスト。

    文字内ループ穴埋めロジック (タイトル画像「な」「は」「使」等の白アウトライン
    隙間解消) の正確性を検証する。
    """

    def test_no_holes_returns_unchanged(self):
        """穴のない単純背景マスクで内容が変化しないこと。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        img = Image.new("L", (40, 40), 0)
        result = _fill_mask_holes(img)
        # 全 0 のまま
        assert list(result.getdata()) == [0] * 1600

    def test_single_hole_filled_when_no_max(self):
        """max_hole_area=None なら穴が埋まること。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        img = Image.new("L", (40, 40), 0)
        d = ImageDraw.Draw(img)
        d.rectangle([5, 5, 35, 35], outline=255, width=2)  # 中央に 1 つの穴
        result = _fill_mask_holes(img)
        # 元 mask で 0 だった穴中央 (例: (20, 20)) が 255 に変わる
        assert result.getpixel((20, 20)) == 255
        # 外背景 (0, 0) は 0 のまま
        assert result.getpixel((0, 0)) == 0

    def test_max_area_filters_large_holes(self):
        """max_hole_area で大穴が除外され、小穴のみ埋まること。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        # 大穴 (中央) と、その内側の小穴 (もう 1 段の閉じ領域) を作る
        img = Image.new("L", (60, 60), 0)
        d = ImageDraw.Draw(img)
        # 外側「文字」リング (大穴を作る境界)
        d.rectangle([10, 10, 50, 50], outline=255, width=2)
        # 内側「文字」リング (小穴を作る境界、~9px²)
        d.rectangle([22, 22, 28, 28], outline=255, width=1)
        # 小穴 (~25px²) は埋め、大穴 (リング内空間 ~900px²) は埋めない閾値
        result = _fill_mask_holes(img, max_hole_area=100)
        # 小穴中央 (25, 25) は 255 になる
        assert result.getpixel((25, 25)) == 255
        # 大穴の領域 (例: (15, 15)) は元のまま 0
        assert result.getpixel((15, 15)) == 0

    def test_max_area_zero_fills_nothing(self):
        """max_hole_area=0 ならどの穴も埋まらない。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        img = Image.new("L", (40, 40), 0)
        d = ImageDraw.Draw(img)
        d.rectangle([5, 5, 35, 35], outline=255, width=2)
        result = _fill_mask_holes(img, max_hole_area=0)
        # 穴中央は 0 のまま
        assert result.getpixel((20, 20)) == 0

    def test_disconnected_outer_background_not_filled(self):
        """複数の文字ストロークで分断された外背景が「穴」と誤認されないこと。

        これがないと「ひどい」状態 (文字周囲が白い長方形になる) が再発する。
        境界全周から flood-fill する設計の根幹をテスト。
        """
        from use_cases.ai.title_image_generator import _fill_mask_holes

        # 中央縦ストロークで左右の背景を分断
        img = Image.new("L", (40, 40), 0)
        d = ImageDraw.Draw(img)
        d.rectangle([18, 0, 22, 39], fill=255)
        result = _fill_mask_holes(img)
        # 左側背景 (5, 20) は 0 のまま (= 穴と誤認されない)
        assert result.getpixel((5, 20)) == 0
        # 右側背景 (35, 20) も 0 のまま
        assert result.getpixel((35, 20)) == 0

    def test_full_background_remains_zero(self):
        """全 0 画像 (穴も文字もない) は変化しない。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        img = Image.new("L", (20, 20), 0)
        result = _fill_mask_holes(img)
        assert list(result.getdata()) == [0] * 400

    def test_full_foreground_remains_filled(self):
        """全 255 画像 (穴がない、すべて文字) は変化しない。"""
        from use_cases.ai.title_image_generator import _fill_mask_holes

        img = Image.new("L", (20, 20), 255)
        result = _fill_mask_holes(img)
        assert list(result.getdata()) == [255] * 400


class TestSrtModeSwitching:
    """Phase A SRT モード分岐ロジックのテスト (PR #141)。

    AI 呼び出しは MagicMock で置き換え、プロンプト選択 + バリデーション分岐 +
    placeholder 置換が正しく動くことを検証する。
    """

    @staticmethod
    def _make_mock_client(designs_response: list[dict]) -> MagicMock:
        """OpenAI client のモック。指定 designs を JSON で返す。"""
        client = MagicMock()
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = json.dumps({"designs": designs_response})
        client.chat.completions.create.return_value = completion
        return client

    @staticmethod
    def _valid_design(text: str) -> dict:
        """有効な単一 line デザイン。"""
        return {
            "lines": [
                {
                    "segments": [{"text": text, "font_size": 160, "color": "#000000"}],
                    "outer_outline_color": "#FFFFFF",
                    "outer_outline_width": 10,
                    "inner_outline_color": "#000000",
                    "inner_outline_width": 0,
                }
            ],
            "line_spacing": 10,
            "padding_top": 60,
        }

    def test_srt_mode_selects_srt_prompt_file(self):
        """srt_text 指定時、title_image_candidates_from_srt.md のプロンプトが使われる。"""
        from use_cases.ai.title_image_generator import design_title_layout_candidates

        client = self._make_mock_client([self._valid_design("AI生成タイトル")])
        design_title_layout_candidates(
            client=client,
            title="元タイトル",
            keywords=[],
            target_size=(1080, 438),
            srt_text="字幕内容",
        )
        sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # SRT モード特有のキーワードが含まれていること
        assert "SRT 字幕 (clip 内容の真実)" in sent_prompt
        assert "字幕内容" in sent_prompt  # SRT_TEXT 置換確認

    def test_existing_mode_selects_default_prompt_file(self):
        """srt_text 未指定時は既存の title_image_candidates.md が使われる。"""
        from use_cases.ai.title_image_generator import design_title_layout_candidates

        client = self._make_mock_client([self._valid_design("元タイトル")])
        design_title_layout_candidates(
            client=client,
            title="元タイトル",
            keywords=["AI"],
            target_size=(1080, 438),
        )
        sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # SRT モード特有の文字列が含まれない
        assert "SRT 字幕 (clip 内容の真実)" not in sent_prompt

    def test_max_line_chars_placeholder_replaced_from_constant(self):
        """{MAX_LINE_CHARS} placeholder が定数 _TITLE_FORCE_BREAK_THRESHOLD で置換される。"""
        from use_cases.ai.title_image_generator import (
            _TITLE_FORCE_BREAK_THRESHOLD,
            design_title_layout_candidates,
        )

        client = self._make_mock_client([self._valid_design("テスト")])
        design_title_layout_candidates(
            client=client,
            title="テスト",
            keywords=[],
            target_size=(1080, 438),
            srt_text="字幕",
        )
        sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # 定数値がプロンプトに反映されている
        assert f"{_TITLE_FORCE_BREAK_THRESHOLD} 文字" in sent_prompt
        # placeholder が残っていないこと
        assert "{MAX_LINE_CHARS}" not in sent_prompt

    def test_existing_mode_validates_title_match(self):
        """既存モード: AI がタイトル文字を変えたらスキップされる。"""
        from use_cases.ai.title_image_generator import design_title_layout_candidates

        # AI が「異なるタイトル」を返す
        client = self._make_mock_client([self._valid_design("異なるタイトル")])
        result = design_title_layout_candidates(
            client=client,
            title="元タイトル",
            keywords=[],
            target_size=(1080, 438),
        )
        # 文字一致しないのでスキップされ、結果は空
        assert result == []

    def test_srt_mode_allows_free_generation(self):
        """SRT モード: AI が title と異なる文字列を返してもスキップされない。"""
        from use_cases.ai.title_image_generator import design_title_layout_candidates

        client = self._make_mock_client([self._valid_design("AI が考えた新タイトル")])
        result = design_title_layout_candidates(
            client=client,
            title="元タイトル",
            keywords=[],
            target_size=(1080, 438),
            srt_text="字幕内容",
        )
        # 文字一致チェックなしで採用される
        assert len(result) == 1
        text = "".join(s.text for line in result[0].lines for s in line.segments)
        assert "AI が考えた新タイトル" in text or text == "AI が考えた新タイトル"

    def test_srt_mode_rejects_empty_title(self):
        """SRT モード: AI が空文字列を返したらスキップされる。"""
        from use_cases.ai.title_image_generator import design_title_layout_candidates

        client = self._make_mock_client([self._valid_design("")])
        result = design_title_layout_candidates(
            client=client,
            title="元タイトル",
            keywords=[],
            target_size=(1080, 438),
            srt_text="字幕",
        )
        assert result == []


class TestBatchPromptTemplate:
    """design_title_layouts_batch() のプロンプト整合性テスト。

    target_size 未指定経路 (= バッチ AI 呼び出し) でも、Phase B/A の 11 文字
    ルールと placeholder が他経路と整合していることを確認。
    """

    @staticmethod
    def _make_mock_client(designs: list[dict]) -> MagicMock:
        client = MagicMock()
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = json.dumps({"designs": designs})
        client.chat.completions.create.return_value = completion
        return client

    @staticmethod
    def _valid_design(text: str) -> dict:
        return {
            "lines": [
                {
                    "segments": [{"text": text, "font_size": 160, "color": "#000000"}],
                    "outer_outline_color": "#FFFFFF",
                    "outer_outline_width": 10,
                    "inner_outline_color": "#000000",
                    "inner_outline_width": 0,
                }
            ],
            "line_spacing": 10,
            "padding_top": 60,
        }

    def test_batch_template_contains_max_line_chars_rule(self):
        """バッチプロンプトに「{MAX_LINE_CHARS} 文字超は複数行」ルールが含まれる。"""
        from use_cases.ai.title_image_generator import (
            _BATCH_PROMPT_TEMPLATE,
        )

        # template 自体に placeholder が含まれていること (= 修正前は無かった)
        assert "{MAX_LINE_CHARS}" in _BATCH_PROMPT_TEMPLATE
        assert "複数行" in _BATCH_PROMPT_TEMPLATE

    def test_batch_call_replaces_max_line_chars(self):
        """バッチ呼び出しで {MAX_LINE_CHARS} が定数値で置換される。"""
        from use_cases.ai.title_image_generator import (
            _TITLE_FORCE_BREAK_THRESHOLD,
            design_title_layouts_batch,
        )

        client = self._make_mock_client([self._valid_design("タイトルA"), self._valid_design("タイトルB")])
        design_title_layouts_batch(
            client=client,
            titles=["タイトルA", "タイトルB"],
            keywords_list=[[], []],
        )
        sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # 定数値がプロンプトに反映されている
        assert f"{_TITLE_FORCE_BREAK_THRESHOLD} 文字" in sent_prompt
        # placeholder が残っていないこと
        assert "{MAX_LINE_CHARS}" not in sent_prompt

    def test_batch_call_validates_title_match(self):
        """バッチ呼び出しは既存モードと同じく文字一致をチェックする。"""
        from use_cases.ai.title_image_generator import design_title_layouts_batch

        # 1 件目は一致、2 件目は不一致
        client = self._make_mock_client([self._valid_design("正しいタイトル"), self._valid_design("AIが書き換えた")])
        results = design_title_layouts_batch(
            client=client,
            titles=["正しいタイトル", "元タイトル"],
            keywords_list=[[], []],
        )
        # 1 件目は採用、2 件目は不一致でスキップ → None
        assert results[0] is not None
        assert results[1] is None

    def test_batch_call_applies_enforce_line_break(self):
        """バッチ呼び出しでも _enforce_line_break (Phase B) が適用される。

        AI が 11 文字超を 1 line で返した場合、後処理で複数行に分割される。
        """
        from use_cases.ai.title_image_generator import (
            _TITLE_FORCE_BREAK_THRESHOLD,
            design_title_layouts_batch,
        )

        long_title = "あ" * (_TITLE_FORCE_BREAK_THRESHOLD + 5)  # 16 文字 1 行
        client = self._make_mock_client([self._valid_design(long_title)])
        results = design_title_layouts_batch(
            client=client,
            titles=[long_title],
            keywords_list=[[]],
        )
        assert results[0] is not None
        # Phase B 適用で複数行に分割されている
        assert len(results[0].lines) >= 2
