"""
字幕画像レンダリングモジュールのユニットテスト

use_cases/ai/subtitle_image_renderer.py の全機能を検証する。
PIL 実描画テストと、フォント解決・インポートチェックのモックテストを含む。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from use_cases.ai.subtitle_image_renderer import (
    FALLBACK_FONTS,
    FONT_DIR,
    FONT_WEIGHTS,
    SubtitleEntry,
    SubtitleStyle,
    _draw_text_with_outline,
    _ensure_pil,
    _resolve_font,
    render_subtitle_image,
    render_subtitle_images_batch,
)


# ---------------------------------------------------------------------------
# SubtitleEntry / SubtitleStyle — データクラスのデフォルト値
# ---------------------------------------------------------------------------


class TestSubtitleEntry:
    def test_fields_stored_correctly(self):
        entry = SubtitleEntry(index=3, start_time=1.5, end_time=4.0, text="テスト字幕")
        assert entry.index == 3
        assert entry.start_time == pytest.approx(1.5)
        assert entry.end_time == pytest.approx(4.0)
        assert entry.text == "テスト字幕"

    def test_index_zero(self):
        entry = SubtitleEntry(index=0, start_time=0.0, end_time=0.5, text="")
        assert entry.index == 0
        assert entry.text == ""

    def test_large_index(self):
        entry = SubtitleEntry(index=9999, start_time=100.0, end_time=200.0, text="最後")
        assert entry.index == 9999

    def test_multiline_text(self):
        entry = SubtitleEntry(index=1, start_time=0.0, end_time=3.0, text="一行目\n二行目")
        assert "\n" in entry.text


class TestSubtitleStyle:
    def test_default_values(self):
        style = SubtitleStyle()
        assert style.font_size == 48
        assert style.font_weight == "Bd"
        assert style.text_color == "#FFFFFF"
        assert style.outer_outline_color == "#000000"
        assert style.outer_outline_width == 6
        assert style.inner_outline_color == "#FFFFFF"
        assert style.inner_outline_width == 0
        assert style.line_spacing == 8

    def test_custom_values(self):
        style = SubtitleStyle(
            font_size=72,
            font_weight="Eb",
            text_color="#FFFF00",
            outer_outline_color="#0000FF",
            outer_outline_width=10,
            inner_outline_color="#FF0000",
            inner_outline_width=3,
            line_spacing=12,
        )
        assert style.font_size == 72
        assert style.font_weight == "Eb"
        assert style.text_color == "#FFFF00"
        assert style.outer_outline_color == "#0000FF"
        assert style.outer_outline_width == 10
        assert style.inner_outline_color == "#FF0000"
        assert style.inner_outline_width == 3
        assert style.line_spacing == 12

    def test_zero_inner_outline_width_is_default(self):
        """内側アウトラインのデフォルトは0（無効）"""
        style = SubtitleStyle()
        assert style.inner_outline_width == 0


# ---------------------------------------------------------------------------
# _ensure_pil — PIL インポートチェック
# ---------------------------------------------------------------------------


class TestEnsurePil:
    def test_returns_pil_modules_when_available(self):
        ImageMod, ImageDrawMod, ImageFontMod = _ensure_pil()
        assert ImageMod is Image
        assert ImageDrawMod is ImageDraw
        assert ImageFontMod is ImageFont

    def test_raises_import_error_when_pil_missing(self):
        """PIL がインストールされていない場合に分かりやすい ImportError を送出する"""
        # PIL モジュールをキャッシュから退避させて import に失敗させる
        pil_backup = {k: v for k, v in sys.modules.items() if "PIL" in k}
        for key in list(pil_backup.keys()):
            del sys.modules[key]

        try:
            real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

            def _block_pil(name, *args, **kwargs):
                if name == "PIL" or name.startswith("PIL."):
                    raise ImportError("mocked no PIL")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_block_pil):
                with pytest.raises(ImportError, match="Pillow is required"):
                    _ensure_pil()
        finally:
            sys.modules.update(pil_backup)

    def test_returns_tuple_of_three(self):
        result = _ensure_pil()
        assert len(result) == 3


# ---------------------------------------------------------------------------
# _resolve_font — フォント解決
# ---------------------------------------------------------------------------


class TestResolveFont:
    def test_returns_freetype_font(self):
        font = _resolve_font("Bd", 48)
        assert isinstance(font, ImageFont.FreeTypeFont)

    def test_all_known_weights(self):
        """定義された全ウェイトでフォントが解決できること"""
        for weight in FONT_WEIGHTS:
            font = _resolve_font(weight, 24)
            assert isinstance(font, ImageFont.FreeTypeFont), f"weight={weight} failed"

    def test_unknown_weight_falls_back_to_bd(self):
        """未知のウェイトは 'Bd' にフォールバックする"""
        font = _resolve_font("XX", 24)
        assert font is not None

    def test_different_sizes_return_different_fonts(self):
        """異なるフォントサイズが別オブジェクトで返ること"""
        f1 = _resolve_font("Bd", 24)
        f2 = _resolve_font("Bd", 72)
        # サイズが異なるのでオブジェクトも異なる
        assert f1 is not f2

    def test_font_file_exists_path_used(self, tmp_path):
        """preset/ にフォントファイルがあればそれを使う"""
        # ダミーフォントを用意（実際には .otf の代わりに truetype フォントを生成できないので
        # 存在するシステムフォントをコピーする）
        import shutil

        # システム上に存在するフォントパスを探す
        system_font = None
        for fb in FALLBACK_FONTS:
            if Path(fb).exists():
                system_font = fb
                break

        if system_font is None:
            pytest.skip("システムフォントが見つからないためスキップ")

        # FONT_WEIGHTS の最初のウェイトのファイル名でコピーを作成
        weight = "Bd"
        font_name = FONT_WEIGHTS[weight]
        dest = tmp_path / font_name
        shutil.copy(system_font, dest)

        # FONT_DIR をモックしてダミーフォントパスを使わせる
        with patch("use_cases.ai.subtitle_image_renderer.FONT_DIR", tmp_path):
            font = _resolve_font(weight, 36)
        assert isinstance(font, ImageFont.FreeTypeFont)

    def test_no_preset_font_uses_fallback(self, tmp_path):
        """preset/ にフォントがない場合にシステムフォールバックを使う"""
        empty_dir = tmp_path / "empty_preset"
        empty_dir.mkdir()

        with patch("use_cases.ai.subtitle_image_renderer.FONT_DIR", empty_dir):
            font = _resolve_font("Bd", 36)
        # 何らかのフォント（FreeTypeFont か ImageFont.ImageFont）が返ること
        assert font is not None

    def test_no_preset_no_system_font_uses_default(self, tmp_path, caplog):
        """preset/ にもシステムフォントにも存在しない場合にデフォルトフォントを使い警告を出す"""
        import logging

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with (
            patch("use_cases.ai.subtitle_image_renderer.FONT_DIR", empty_dir),
            patch("use_cases.ai.subtitle_image_renderer.FALLBACK_FONTS", ["/nonexistent/font.ttc"]),
            caplog.at_level(logging.WARNING, logger="use_cases.ai.subtitle_image_renderer"),
        ):
            font = _resolve_font("Bd", 24)

        assert font is not None
        assert any("日本語フォントが見つかりません" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _draw_text_with_outline — アウトライン描画
# ---------------------------------------------------------------------------


class TestDrawTextWithOutline:
    def _make_draw(self, size=(300, 100)):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        return img, draw

    def _count_non_transparent(self, img: Image.Image) -> int:
        return sum(1 for px in img.getdata() if px[3] > 0)

    def _get_font(self, size=20):
        return ImageFont.load_default(size=size)

    def test_draws_text_without_outlines(self):
        """アウトライン幅 0 でもテキスト本文が描画されること"""
        img, draw = self._make_draw()
        font = self._get_font()
        _draw_text_with_outline(
            draw,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_width=0,
            inner_width=0,
        )
        assert self._count_non_transparent(img) > 0

    def test_outer_outline_increases_pixel_count(self):
        """外側アウトラインがあると描画ピクセル数が増えること"""
        font = self._get_font()

        img_no, draw_no = self._make_draw()
        _draw_text_with_outline(
            draw_no,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_width=0,
            inner_width=0,
        )
        px_no = self._count_non_transparent(img_no)

        img_out, draw_out = self._make_draw()
        _draw_text_with_outline(
            draw_out,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_color="#000000",
            outer_width=4,
            inner_width=0,
        )
        px_out = self._count_non_transparent(img_out)

        assert px_out > px_no

    def test_inner_outline_draws_additional_pixels(self):
        """内側アウトラインが有効な場合にピクセルが描画されること"""
        font = self._get_font()

        img_single, draw_single = self._make_draw()
        _draw_text_with_outline(
            draw_single,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_color="#000000",
            outer_width=3,
            inner_color="#FFFFFF",
            inner_width=0,
        )
        px_single = self._count_non_transparent(img_single)

        img_double, draw_double = self._make_draw()
        _draw_text_with_outline(
            draw_double,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_color="#000000",
            outer_width=3,
            inner_color="#FF0000",
            inner_width=2,
        )
        px_double = self._count_non_transparent(img_double)

        # 内側アウトラインを加えても不透明ピクセルは同数以上
        assert px_double >= px_single

    def test_text_drawn_at_specified_position(self):
        """テキストが指定位置付近に描画されること"""
        font = self._get_font()
        img, draw = self._make_draw(size=(300, 100))
        _draw_text_with_outline(
            draw,
            (50, 20),
            "X",
            font,
            fill="#FFFFFF",
            outer_width=0,
            inner_width=0,
        )
        data = list(img.getdata())
        width = img.width
        # (50, 20) 付近にピクセルが存在すること — (40..80, 15..45) の矩形内にある
        found = False
        for y in range(15, 45):
            for x in range(40, 80):
                if data[y * width + x][3] > 0:
                    found = True
                    break
            if found:
                break
        assert found, "指定位置付近に描画ピクセルが見つからない"

    def test_double_outline_different_colors(self):
        """外側と内側で異なる色が使われること（色が混在していること）"""
        font = self._get_font()
        img, draw = self._make_draw()
        _draw_text_with_outline(
            draw,
            (10, 10),
            "Hi",
            font,
            fill="#FFFFFF",
            outer_color="#FF0000",
            outer_width=4,
            inner_color="#0000FF",
            inner_width=2,
        )
        pixels = list(img.getdata())
        colors = {px[:3] for px in pixels if px[3] > 0}
        # 複数の色が混在していること
        assert len(colors) > 1


# ---------------------------------------------------------------------------
# render_subtitle_image — 単一字幕のレンダリング
# ---------------------------------------------------------------------------


class TestRenderSubtitleImage:
    def test_normal_text_creates_file(self, tmp_path):
        out = tmp_path / "sub.png"
        result = render_subtitle_image("テスト字幕", out, width=200, height=400)
        assert result == out
        assert out.exists()

    def test_returns_output_path(self, tmp_path):
        out = tmp_path / "result.png"
        returned = render_subtitle_image("Hello", out, width=200, height=400)
        assert returned == out

    def test_creates_rgba_image(self, tmp_path):
        out = tmp_path / "rgba.png"
        render_subtitle_image("テスト", out, width=300, height=600)
        img = Image.open(out)
        assert img.mode == "RGBA"

    def test_correct_image_size(self, tmp_path):
        out = tmp_path / "size.png"
        render_subtitle_image("サイズテスト", out, width=320, height=640)
        img = Image.open(out)
        assert img.size == (320, 640)

    def test_transparent_background(self, tmp_path):
        """背景が透明（アルファ=0）であること"""
        out = tmp_path / "transparent.png"
        render_subtitle_image("字幕", out, width=300, height=600)
        img = Image.open(out)
        # 右上隅（字幕が描画されない領域）は完全透明のはず
        corner_pixel = img.getpixel((0, 0))
        assert corner_pixel[3] == 0, "背景が透明でない"

    def test_text_is_rendered_as_non_transparent_pixels(self, tmp_path):
        """テキストが実際に描画されること（非透明ピクセルが存在）"""
        out = tmp_path / "nonzero.png"
        render_subtitle_image("字幕テスト", out, width=300, height=600)
        img = Image.open(out)
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent > 0

    def test_empty_text_creates_fully_transparent_image(self, tmp_path):
        """空文字列では完全透明の画像が生成されること"""
        out = tmp_path / "empty.png"
        render_subtitle_image("", out, width=200, height=400)
        assert out.exists()
        img = Image.open(out)
        assert img.mode == "RGBA"
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent == 0

    def test_whitespace_only_text_creates_transparent_image(self, tmp_path):
        """空白のみのテキストでも透明画像が生成されること"""
        out = tmp_path / "ws.png"
        render_subtitle_image("   ", out, width=200, height=400)
        img = Image.open(out)
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent == 0

    def test_multiline_text_renders_content(self, tmp_path):
        """改行を含むテキストが正しく描画されること"""
        out = tmp_path / "multiline.png"
        render_subtitle_image("一行目\n二行目", out, width=300, height=600)
        img = Image.open(out)
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent > 0

    def test_multiline_has_more_pixels_than_single_line(self, tmp_path):
        """2行テキストは1行テキストよりも多くのピクセルが描画されること"""
        out1 = tmp_path / "single.png"
        out2 = tmp_path / "multi.png"

        render_subtitle_image("字幕テキスト", out1, width=300, height=600)
        render_subtitle_image("字幕テキスト\n二行目追加", out2, width=300, height=600)

        px1 = sum(1 for px in Image.open(out1).getdata() if px[3] > 0)
        px2 = sum(1 for px in Image.open(out2).getdata() if px[3] > 0)
        assert px2 > px1

    def test_parent_directory_created_automatically(self, tmp_path):
        """出力先の親ディレクトリが存在しなくても自動作成されること"""
        out = tmp_path / "nested" / "deep" / "sub.png"
        assert not out.parent.exists()
        render_subtitle_image("テスト", out, width=200, height=400)
        assert out.exists()

    def test_default_style_is_applied_when_none(self, tmp_path):
        """style=None の場合にデフォルトスタイルが使われて描画されること"""
        out = tmp_path / "default_style.png"
        render_subtitle_image("デフォルト", out, width=300, height=600, style=None)
        assert out.exists()
        img = Image.open(out)
        assert img.mode == "RGBA"

    def test_custom_style_is_applied(self, tmp_path):
        """カスタムスタイルが反映されること"""
        style = SubtitleStyle(
            font_size=24,
            outer_outline_width=2,
            inner_outline_width=1,
        )
        out = tmp_path / "custom.png"
        render_subtitle_image("スタイル", out, width=300, height=600, style=style)
        assert out.exists()

    def test_no_outer_outline_still_renders(self, tmp_path):
        """アウトラインなしでもテキストが描画されること"""
        style = SubtitleStyle(outer_outline_width=0, inner_outline_width=0)
        out = tmp_path / "no_outline.png"
        render_subtitle_image("アウトラインなし", out, width=300, height=600, style=style)
        img = Image.open(out)
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent > 0

    def test_text_positioned_in_lower_region(self, tmp_path):
        """字幕が画像の下部（85%付近）に配置されること"""
        height = 600
        out = tmp_path / "position.png"
        render_subtitle_image("位置テスト", out, width=300, height=height)
        img = Image.open(out)

        # 非透明ピクセルの最小 y 座標を求める
        min_y = None
        for y in range(height):
            for x in range(300):
                if img.getpixel((x, y))[3] > 0:
                    min_y = y
                    break
            if min_y is not None:
                break

        assert min_y is not None
        # 画像高さの 50% 以上の位置から始まること
        assert min_y > height * 0.5, f"字幕開始位置 {min_y} が上すぎる（height={height}）"

    def test_saves_as_png_format(self, tmp_path):
        """PNG 形式で保存されること"""
        out = tmp_path / "fmt.png"
        render_subtitle_image("フォーマット", out, width=200, height=400)
        # PNG マジックバイトを確認
        with open(out, "rb") as f:
            header = f.read(8)
        assert header[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# render_subtitle_images_batch — バッチレンダリング
# ---------------------------------------------------------------------------


class TestRenderSubtitleImagesBatch:
    def _make_entries(self, texts: list[str]) -> list[SubtitleEntry]:
        return [
            SubtitleEntry(index=i + 1, start_time=float(i * 2), end_time=float(i * 2 + 2), text=t)
            for i, t in enumerate(texts)
        ]

    def test_empty_list_returns_empty_list(self, tmp_path):
        paths = render_subtitle_images_batch([], tmp_path / "out", width=200, height=400)
        assert paths == []

    def test_single_entry_creates_one_file(self, tmp_path):
        entries = self._make_entries(["字幕1"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert len(paths) == 1
        assert paths[0].exists()

    def test_multiple_entries_create_correct_count(self, tmp_path):
        entries = self._make_entries(["A", "B", "C", "D"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert len(paths) == 4
        assert all(p.exists() for p in paths)

    def test_output_filenames_use_zero_padded_index(self, tmp_path):
        """ファイル名が subtitle_{index:04d}.png の形式であること"""
        entries = self._make_entries(["一", "二", "三"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        names = [p.name for p in paths]
        assert names == ["subtitle_0001.png", "subtitle_0002.png", "subtitle_0003.png"]

    def test_all_outputs_are_rgba_png(self, tmp_path):
        entries = self._make_entries(["テスト1", "テスト2"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        for p in paths:
            img = Image.open(p)
            assert img.mode == "RGBA"
            assert img.size == (200, 400)

    def test_empty_text_entry_produces_transparent_image(self, tmp_path):
        """テキストが空のエントリは完全透明の画像になること"""
        entries = [SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="")]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert len(paths) == 1
        img = Image.open(paths[0])
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent == 0

    def test_whitespace_text_entry_produces_transparent_image(self, tmp_path):
        entries = [SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="   ")]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        img = Image.open(paths[0])
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent == 0

    def test_nonempty_entry_has_visible_pixels(self, tmp_path):
        entries = [SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="見える字幕")]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=300, height=600)
        img = Image.open(paths[0])
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent > 0

    def test_mixed_entries_empty_and_nonempty(self, tmp_path):
        """空テキストと非空テキストが混在する場合の処理"""
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="実際の字幕"),
            SubtitleEntry(index=2, start_time=2.0, end_time=4.0, text=""),
            SubtitleEntry(index=3, start_time=4.0, end_time=6.0, text="もう一つ"),
        ]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=300, height=600)
        assert len(paths) == 3

        px0 = sum(1 for px in Image.open(paths[0]).getdata() if px[3] > 0)
        px1 = sum(1 for px in Image.open(paths[1]).getdata() if px[3] > 0)
        px2 = sum(1 for px in Image.open(paths[2]).getdata() if px[3] > 0)

        assert px0 > 0
        assert px1 == 0  # 空テキスト
        assert px2 > 0

    def test_output_directory_created_automatically(self, tmp_path):
        """出力ディレクトリが存在しなくても自動作成されること"""
        out_dir = tmp_path / "nested" / "output"
        assert not out_dir.exists()
        entries = self._make_entries(["字幕"])
        render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert out_dir.exists()

    def test_custom_style_applied_to_all_entries(self, tmp_path):
        """カスタムスタイルが全エントリに適用されること"""
        style = SubtitleStyle(font_size=24, outer_outline_width=1)
        entries = self._make_entries(["A", "B"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400, style=style)
        assert len(paths) == 2
        for p in paths:
            img = Image.open(p)
            assert img.mode == "RGBA"

    def test_default_style_used_when_none(self, tmp_path):
        """style=None の場合にデフォルトスタイルで処理されること"""
        entries = self._make_entries(["テスト"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400, style=None)
        assert len(paths) == 1
        assert paths[0].exists()

    def test_returns_list_of_paths(self, tmp_path):
        """戻り値が Path オブジェクトのリストであること"""
        entries = self._make_entries(["X"])
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert isinstance(paths, list)
        assert all(isinstance(p, Path) for p in paths)

    def test_large_index_zero_padded(self, tmp_path):
        """大きいインデックスも 4 桁にゼロパディングされること"""
        entries = [SubtitleEntry(index=123, start_time=0.0, end_time=1.0, text="テスト")]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=200, height=400)
        assert paths[0].name == "subtitle_0123.png"


# ---------------------------------------------------------------------------
# 画像バリデーション — 透過 PNG・サイズ検証
# ---------------------------------------------------------------------------


class TestImageValidation:
    def test_transparent_png_has_correct_mode(self, tmp_path):
        """レンダリング結果が RGBA モードの PNG であること"""
        out = tmp_path / "check.png"
        render_subtitle_image("バリデーション", out, width=400, height=800)
        img = Image.open(out)
        assert img.mode == "RGBA"

    def test_image_size_matches_parameters(self, tmp_path):
        """width/height パラメータ通りの画像サイズになること"""
        for w, h in [(640, 480), (1080, 1920), (100, 100)]:
            out = tmp_path / f"size_{w}x{h}.png"
            render_subtitle_image("テスト", out, width=w, height=h)
            img = Image.open(out)
            assert img.size == (w, h), f"Expected ({w},{h}), got {img.size}"

    def test_batch_image_sizes_match_parameters(self, tmp_path):
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="サイズ確認"),
        ]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=540, height=960)
        img = Image.open(paths[0])
        assert img.size == (540, 960)
        assert img.mode == "RGBA"

    def test_empty_text_still_correct_size(self, tmp_path):
        """空テキストでも正しいサイズの画像が生成されること"""
        out = tmp_path / "empty_size.png"
        render_subtitle_image("", out, width=300, height=600)
        img = Image.open(out)
        assert img.size == (300, 600)
        assert img.mode == "RGBA"

    def test_alpha_channel_is_zero_at_corners(self, tmp_path):
        """字幕が描画されない四隅のアルファ値が 0 であること"""
        out = tmp_path / "corners.png"
        w, h = 400, 800
        render_subtitle_image("コーナーテスト", out, width=w, height=h)
        img = Image.open(out)
        # 左上隅
        assert img.getpixel((0, 0))[3] == 0, "左上隅が透明でない"
        # 右上隅
        assert img.getpixel((w - 1, 0))[3] == 0, "右上隅が透明でない"

    def test_png_magic_bytes(self, tmp_path):
        """ファイルが PNG フォーマットであること（マジックバイト確認）"""
        out = tmp_path / "magic.png"
        render_subtitle_image("PNG確認", out, width=200, height=400)
        with open(out, "rb") as f:
            header = f.read(8)
        assert header == b"\x89PNG\r\n\x1a\n"

    def test_batch_transparent_corners(self, tmp_path):
        """バッチ出力の各画像も四隅が透明であること"""
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=1.0, text="バッチ確認"),
        ]
        out_dir = tmp_path / "out"
        paths = render_subtitle_images_batch(entries, out_dir, width=300, height=600)
        img = Image.open(paths[0])
        assert img.getpixel((0, 0))[3] == 0
        assert img.getpixel((299, 0))[3] == 0


# ---------------------------------------------------------------------------
# 統合的なシナリオテスト
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    def test_full_pipeline_single_entry(self, tmp_path):
        """SubtitleEntry → render_subtitle_image → 画像検証の一連フロー"""
        entry = SubtitleEntry(index=5, start_time=10.0, end_time=15.0, text="統合テスト字幕")
        style = SubtitleStyle(
            font_size=36,
            text_color="#FFFF00",
            outer_outline_color="#000000",
            outer_outline_width=4,
            inner_outline_color="#FFFFFF",
            inner_outline_width=2,
        )
        out = tmp_path / "integration.png"
        result = render_subtitle_image(entry.text, out, width=300, height=600, style=style)

        assert result.exists()
        img = Image.open(result)
        assert img.mode == "RGBA"
        assert img.size == (300, 600)
        non_transparent = sum(1 for px in img.getdata() if px[3] > 0)
        assert non_transparent > 0

    def test_batch_consistency_with_single(self, tmp_path):
        """バッチ出力と単一出力の画像内容が一致すること"""
        text = "一致確認"
        style = SubtitleStyle(font_size=30, outer_outline_width=3)

        out_single = tmp_path / "single.png"
        render_subtitle_image(text, out_single, width=300, height=600, style=style)

        entries = [SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text=text)]
        out_dir = tmp_path / "batch"
        paths = render_subtitle_images_batch(entries, out_dir, width=300, height=600, style=style)

        img_s = Image.open(out_single)
        img_b = Image.open(paths[0])

        px_s = sum(1 for px in img_s.getdata() if px[3] > 0)
        px_b = sum(1 for px in img_b.getdata() if px[3] > 0)

        # 同じテキスト・スタイル・サイズなので非透明ピクセル数が一致するはず
        assert px_s == px_b, f"単一={px_s}, バッチ={px_b} — 一致しない"

    def test_japanese_text_renders_without_error(self, tmp_path):
        """日本語テキストがエラーなく描画されること"""
        texts = ["本日のニュース", "AIが世界を変える", "2024年の展望\n専門家に聞く"]
        for i, text in enumerate(texts):
            out = tmp_path / f"jp_{i}.png"
            render_subtitle_image(text, out, width=400, height=800)
            assert out.exists()

    def test_very_long_text_renders_without_crash(self, tmp_path):
        """非常に長いテキストでもクラッシュしないこと"""
        long_text = "あ" * 50
        out = tmp_path / "long.png"
        render_subtitle_image(long_text, out, width=300, height=600)
        assert out.exists()
