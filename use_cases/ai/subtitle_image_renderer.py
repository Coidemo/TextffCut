"""
字幕画像レンダリングモジュール

Pillowを使用して字幕テキストを透過PNG画像に変換する。
ダブルストローク（外側+内側のアウトライン）機能付き。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# フォント解決（title_image_generator と同じロジック）
FONT_DIR = Path(__file__).parent.parent.parent / "preset"
FONT_WEIGHTS = {
    "Th": "LINESeedJP_A_OTF_Th.otf",
    "Rg": "LINESeedJP_A_OTF_Rg.otf",
    "Bd": "LINESeedJP_A_OTF_Bd.otf",
    "Eb": "LINESeedJP_A_OTF_Eb.otf",
}
FALLBACK_FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"


@dataclass
class SubtitleEntry:
    """字幕エントリ（SE配置計算等で使用するデータコンテナ）"""

    index: int
    start_time: float
    end_time: float
    text: str


@dataclass
class SubtitleStyle:
    """字幕描画スタイル"""

    font_size: int = 48
    font_weight: str = "Bd"
    text_color: str = "#FFFFFF"
    outer_outline_color: str = "#000000"
    outer_outline_width: int = 6
    inner_outline_color: str = "#FFFFFF"
    inner_outline_width: int = 0
    line_spacing: int = 8


def _resolve_font(weight: str = "Bd", size: int = 48) -> ImageFont.FreeTypeFont:
    """フォントを解決する。preset/内のフォント → システムフォールバック。"""
    font_name = FONT_WEIGHTS.get(weight, FONT_WEIGHTS["Bd"])
    font_path = FONT_DIR / font_name
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size)
    if Path(FALLBACK_FONT).exists():
        return ImageFont.truetype(FALLBACK_FONT, size)
    return ImageFont.load_default()


def _draw_text_with_outline(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    outer_color: str = "#000000",
    outer_width: int = 6,
    inner_color: str = "#FFFFFF",
    inner_width: int = 0,
) -> None:
    """テキストをアウトライン付きで描画する。"""
    x, y = position

    # 外側アウトライン
    if outer_width > 0:
        for dx in range(-outer_width, outer_width + 1):
            for dy in range(-outer_width, outer_width + 1):
                if dx * dx + dy * dy <= outer_width * outer_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=outer_color)

    # 内側アウトライン
    if inner_width > 0:
        for dx in range(-inner_width, inner_width + 1):
            for dy in range(-inner_width, inner_width + 1):
                if dx * dx + dy * dy <= inner_width * inner_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=inner_color)

    # 本文
    draw.text((x, y), text, font=font, fill=fill)


def render_subtitle_image(
    text: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    style: SubtitleStyle | None = None,
) -> Path:
    """
    字幕テキストを透過PNG画像として描画する。

    Args:
        text: 字幕テキスト（改行含む）
        output_path: 出力パス
        width: 画像幅
        height: 画像高さ
        style: 描画スタイル

    Returns:
        出力ファイルパス
    """
    if style is None:
        style = SubtitleStyle()

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _resolve_font(style.font_weight, style.font_size)

    lines = text.split("\n")
    # 各行の高さを計算
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_height = sum(line_heights) + style.line_spacing * (len(lines) - 1)

    # 画面下部に配置（下から15%の位置）
    y = int(height * 0.85) - total_height

    for i, line in enumerate(lines):
        lw = line_widths[i]
        x = (width - lw) // 2
        _draw_text_with_outline(
            draw, (x, y), line, font,
            fill=style.text_color,
            outer_color=style.outer_outline_color,
            outer_width=style.outer_outline_width,
            inner_color=style.inner_outline_color,
            inner_width=style.inner_outline_width,
        )
        y += line_heights[i] + style.line_spacing

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


def render_subtitle_images_batch(
    entries: list[SubtitleEntry],
    output_dir: Path,
    width: int = 1080,
    height: int = 1920,
    style: SubtitleStyle | None = None,
) -> list[Path]:
    """
    複数の字幕エントリをバッチで透過PNG画像に変換する。

    Args:
        entries: SubtitleEntry のリスト
        output_dir: 出力ディレクトリ
        width: 画像幅
        height: 画像高さ
        style: 描画スタイル

    Returns:
        出力ファイルパスのリスト
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for entry in entries:
        out_path = output_dir / f"subtitle_{entry.index:04d}.png"
        render_subtitle_image(entry.text, out_path, width, height, style)
        paths.append(out_path)
    return paths
