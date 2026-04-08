"""
タイトル画像生成モジュール

GPT-4.1-miniがタイトルのレイアウト（行分割・サイズ・色・グラデーション）をJSON設計し、
Pillowが透過PNG画像として描画する。FCPXMLにオーバーレイとして配置する用途。
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------


@dataclass
class TitleTextSegment:
    """行内の1セグメント（文字グループ）"""

    text: str
    font_size: int = 72
    color: str = "#FFFFFF"
    gradient: tuple[str, str] | None = None
    weight: str = "Eb"


@dataclass
class TitleLine:
    """1行（複数セグメントで構成）"""

    segments: list[TitleTextSegment]
    outer_outline_color: str = "#000000"
    outer_outline_width: int = 8
    inner_outline_color: str = "#FFFFFF"
    inner_outline_width: int = 0


@dataclass
class TitleImageDesign:
    """タイトル画像全体のデザイン"""

    lines: list[TitleLine]
    line_spacing: int = 10
    padding_top: int = 60


# ---------------------------------------------------------------------------
# フォント検索
# ---------------------------------------------------------------------------

_WEIGHT_MAP = {
    "Th": "Th",
    "Rg": "Rg",
    "Bd": "Bd",
    "Eb": "Eb",
}


def find_font(weight: str = "Eb", font_dir: Path | None = None) -> str:
    """フォントファイルパスを返す。見つからなければフォールバック。"""
    w = _WEIGHT_MAP.get(weight, "Eb")
    filename = f"LINESeedJP_OTF_{w}.otf"

    # 1. font_dir（preset/fonts/ 等）
    if font_dir:
        p = font_dir / filename
        if p.exists():
            return str(p)

    # 2. ~/Library/Fonts/
    home_font = Path.home() / "Library" / "Fonts" / filename
    if home_font.exists():
        return str(home_font)

    # 3. フォールバック: ヒラギノ角ゴシック
    hiragino = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
    if hiragino.exists():
        return str(hiragino)

    # 4. 最終フォールバック: Pillowデフォルトフォント
    logger.warning(f"フォントが見つかりません: {filename}。デフォルトフォントを使用します。")
    return ""  # ImageFont.truetype("") は失敗するが、呼び出し元でキャッチされる


# ---------------------------------------------------------------------------
# frame.png 色抽出
# ---------------------------------------------------------------------------


def extract_frame_colors(frame_path: Path, num_colors: int = 5) -> list[str]:
    """frame.pngから支配色を抽出し、hex文字列リストで返す"""
    try:
        img = Image.open(frame_path).convert("RGBA")
        # リサイズして高速化
        img = img.resize((100, 100), Image.LANCZOS)

        pixels = []
        for pixel in img.getdata():
            r, g, b, a = pixel
            if a > 128:  # 半透明以上のピクセルのみ
                # 32刻みに量子化してグラデーション/微差を吸収
                qr = (r // 32) * 32
                qg = (g // 32) * 32
                qb = (b // 32) * 32
                pixels.append((qr, qg, qb))

        if not pixels:
            return []

        counter = Counter(pixels)
        top_colors = counter.most_common(num_colors)
        return [f"#{r:02x}{g:02x}{b:02x}" for (r, g, b), _ in top_colors]
    except Exception as e:
        logger.warning(f"フレーム色抽出失敗: {e}")
        return []


# ---------------------------------------------------------------------------
# AIタイトルデザイン
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """{
  "lines": [
    {
      "segments": [
        {"text": "str", "font_size": 72, "color": "#FFFFFF", "gradient": null, "weight": "Eb"}
      ],
      "outer_outline_color": "#000000",
      "outer_outline_width": 8,
      "inner_outline_color": "#FFFFFF",
      "inner_outline_width": 0
    }
  ],
  "line_spacing": 10,
  "padding_top": 60
}"""


def design_title_layout(
    client: "openai.OpenAI",
    title: str,
    keywords: list[str],
    frame_colors: list[str] | None = None,
    orientation: str = "vertical",
    model: str = "gpt-4.1-mini",
    prompt_template: str | None = None,
) -> TitleImageDesign:
    """AIにタイトルレイアウトを設計させる"""
    if prompt_template is None:
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "title_image_design.md"
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = _DEFAULT_PROMPT

    frame_info = "なし（デフォルトの配色で設計してください）"
    if frame_colors:
        frame_info = ", ".join(frame_colors)

    prompt = prompt_template.replace("{TITLE}", title)
    prompt = prompt.replace("{KEYWORDS}", ", ".join(keywords) if keywords else "なし")
    prompt = prompt.replace("{FRAME_COLORS}", frame_info)
    prompt = prompt.replace("{JSON_SCHEMA}", _JSON_SCHEMA)
    prompt = prompt.replace("{ORIENTATION}", orientation)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("AIレスポンスが空です")
    raw = json.loads(content)
    design = _parse_design_json(raw)

    # バリデーション: AIが文字を書き換えていないか確認
    reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
    if reconstructed != title:
        logger.warning(
            f"AIがタイトル文字を変更しました (期待: {title!r}, 実際: {reconstructed!r})。フォールバック使用。"
        )
        raise ValueError("AIがタイトル文字を変更しました")

    return design


_DEFAULT_PROMPT = """あなたはYouTubeショート動画のタイトルテキストデザイナーです。
クリップタイトルを動画上部に表示するキャッチーな2-3行テキストにデザインしてください。

## タイトル
{TITLE}

## キーワード
{KEYWORDS}

## 背景フレームの色情報
{FRAME_COLORS}

## 画面向き
{ORIENTATION}

## 最重要ルール
- タイトルの文字は一切変更・省略・言い換えしないこと
- 全セグメントのtextを結合した結果が元タイトルと完全一致すること

## デザインルール
1. 2-3行に分割（意味の切れ目、インパクト重視で改行）
2. 各行内をさらにセグメントに分割（強調語・句読点・助詞などで区切る）
3. 最も伝えたい語句を大きく（font_size: 80-100）、接続詞・助詞・句読点を小さく（50-70）
4. 背景フレームの色に映える配色を選ぶ
5. 白文字や明るい色の文字は黒の外アウトラインのみ（inner_outline_width=0）でシンプルに
6. グラデーションセグメントのみ二重アウトライン（外側=暗色、内側=明色）で装飾する
7. 強調セグメントにgradientを使う（2色の縦グラデーション）
8. weightは強調語=Eb、補足=Bd、句読点=Rg

## 出力JSON
{JSON_SCHEMA}
"""


def _parse_design_json(raw: dict) -> TitleImageDesign:
    """AIのJSON出力をデータクラスに変換（値クランプ付き）"""
    lines = []
    for line_data in raw.get("lines", []):
        segments = []
        for seg_data in line_data.get("segments", []):
            grad = seg_data.get("gradient")
            if isinstance(grad, list) and len(grad) == 2:
                grad = (str(grad[0]), str(grad[1]))
            else:
                grad = None

            segments.append(
                TitleTextSegment(
                    text=str(seg_data.get("text", "")),
                    font_size=_clamp(_safe_int(seg_data.get("font_size"), 72), 40, 120),
                    color=str(seg_data.get("color", "#FFFFFF")),
                    gradient=grad,
                    weight=str(seg_data.get("weight", "Eb")),
                )
            )

        if not segments:
            continue

        lines.append(
            TitleLine(
                segments=segments,
                outer_outline_color=str(line_data.get("outer_outline_color", "#000000")),
                outer_outline_width=_clamp(_safe_int(line_data.get("outer_outline_width"), 8), 0, 10),
                inner_outline_color=str(line_data.get("inner_outline_color", "#FFFFFF")),
                inner_outline_width=_clamp(_safe_int(line_data.get("inner_outline_width"), 0), 0, 10),
            )
        )

    if not lines:
        raise ValueError("AIレスポンスに有効な行がありません")

    return TitleImageDesign(
        lines=lines,
        line_spacing=_clamp(_safe_int(raw.get("line_spacing"), 10), 0, 50),
        padding_top=_clamp(_safe_int(raw.get("padding_top"), 60), 0, 200),
    )


def _safe_int(value: object, default: int) -> int:
    """AI出力の値を安全にintに変換する（None/文字列/float対応）"""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _scale_outline(base_width: int, font_size: int, ref_size: int = 90) -> int:
    """フォントサイズに比例してアウトライン幅を調整する。

    base_width は ref_size (デフォルト90px) 基準の値。
    例: font_size=60, base_width=8, ref_size=90 → round(8 * 60/90) = 5
    """
    if base_width <= 0:
        return 0
    scaled = round(base_width * font_size / ref_size)
    return max(2, scaled)  # 最低2pxは確保


# ---------------------------------------------------------------------------
# フォールバック（AI無し）
# ---------------------------------------------------------------------------


def create_fallback_design(title: str) -> TitleImageDesign:
    """AIなしでデフォルトデザインを作成する（強調処理付き）"""
    parts = _split_title(title)

    # 最も長い行を見つけて強調する
    longest_idx = max(range(len(parts)), key=lambda i: len(parts[i])) if parts else 0

    lines = []
    for i, part in enumerate(parts):
        is_emphasis = (i == longest_idx) and len(parts) > 1
        # 強調行は大きく太く、他は小さめに
        font_size = 85 if is_emphasis else 65
        weight = "Eb" if is_emphasis else "Bd"

        # 強調行はグラデーション
        if is_emphasis:
            gradient = ("#FFD700", "#FF8C00")
            color = "#FFFFFF"
        else:
            gradient = None
            color = "#FFFFFF"

        lines.append(
            TitleLine(
                segments=[
                    TitleTextSegment(
                        text=part,
                        font_size=font_size,
                        color=color,
                        gradient=gradient,
                        weight=weight,
                    )
                ],
                outer_outline_color="#000000",
                outer_outline_width=8,
                inner_outline_width=4 if gradient else 0,
                inner_outline_color="#FFFFFF",
            )
        )

    return TitleImageDesign(lines=lines, padding_top=80, line_spacing=12)


def _split_title(title: str, max_lines: int = 3) -> list[str]:
    """タイトルを自然な位置で分割"""
    if len(title) <= 10:
        return [title]

    # 句読点・括弧・助詞で分割を試みる
    split_points = []
    for i, ch in enumerate(title):
        if ch in "、。！？」』）】":
            split_points.append(i + 1)
        elif ch in "「『（【":
            if i > 0:
                split_points.append(i)

    if not split_points:
        # 均等分割（最後のパートに残り全文字を含める）
        n_lines = min(max_lines, max(1, (len(title) + 9) // 10))
        chunk = len(title) // n_lines
        parts = [title[i : i + chunk] for i in range(0, len(title), chunk)]
        if len(parts) > n_lines:
            parts[n_lines - 1] += "".join(parts[n_lines:])
            parts = parts[:n_lines]
        return parts

    # 分割点で分ける
    parts = []
    prev = 0
    for sp in split_points:
        if sp > prev:
            parts.append(title[prev:sp])
            prev = sp
        if len(parts) >= max_lines - 1:
            break
    if prev < len(title):
        parts.append(title[prev:])

    return parts[:max_lines]


# ---------------------------------------------------------------------------
# Pillow描画
# ---------------------------------------------------------------------------


def render_title_image(
    design: TitleImageDesign,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    font_dir: Path | None = None,
) -> Path:
    """デザインに基づいてタイトル画像を描画し、PNGで保存する"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin_x = 40  # 左右マージン
    usable_width = width - margin_x * 2
    current_y = design.padding_top

    for line in design.lines:
        # 各セグメントのフォントをロード
        fonts: list[ImageFont.FreeTypeFont] = []
        seg_widths: list[int] = []
        seg_heights: list[int] = []
        seg_ascents: list[int] = []

        for seg in line.segments:
            font_path = find_font(seg.weight, font_dir)
            font = ImageFont.truetype(font_path, seg.font_size)
            fonts.append(font)

            bbox = font.getbbox(seg.text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            ascent = -bbox[1]  # ベースラインからの上方向距離
            seg_widths.append(w)
            seg_heights.append(h)
            seg_ascents.append(ascent)

        total_line_width = sum(seg_widths)

        # 幅超過時の自動縮小
        if total_line_width > usable_width and total_line_width > 0:
            scale_factor = usable_width / total_line_width
            for i, seg in enumerate(line.segments):
                new_size = max(30, int(seg.font_size * scale_factor))
                font_path = find_font(seg.weight, font_dir)
                fonts[i] = ImageFont.truetype(font_path, new_size)
                bbox = fonts[i].getbbox(seg.text)
                seg_widths[i] = bbox[2] - bbox[0]
                seg_heights[i] = bbox[3] - bbox[1]
                seg_ascents[i] = -bbox[1]
            total_line_width = sum(seg_widths)

        # 行の最大可視高さ（垂直中央揃え用）
        max_vis_height = max(seg_heights) if seg_heights else 0

        # 行全体をx方向中央揃え
        start_x = margin_x + (usable_width - total_line_width) // 2
        x = start_x

        for i, seg in enumerate(line.segments):
            font = fonts[i]
            # 垂直中央揃え: 小さいセグメントを行の中央に配置
            vis_top = current_y + (max_vis_height - seg_heights[i]) // 2
            y = vis_top + seg_ascents[i]

            # フォントサイズに応じてアウトライン幅を調整
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
            )

            x += seg_widths[i]

        current_y += max_vis_height + design.line_spacing

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


def _draw_segment(
    img: Image.Image,
    draw: ImageDraw.Draw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    color: str,
    gradient: tuple[str, str] | None,
    outer_outline_color: str,
    outer_outline_width: int,
    inner_outline_color: str,
    inner_outline_width: int,
) -> None:
    """1セグメントを二重アウトライン + グラデーション対応で描画

    リングマスク方式:
      1. テキスト / 内側 / 外側 の3段階マスクを作成
      2. 差分でリング（ドーナツ型）マスクを作り、各色で塗る
      3. テキスト塗りはグリフ形状のみ（膨張しない）
    """

    x, y = xy
    total_stroke = outer_outline_width + inner_outline_width

    # ストローク込みの領域を計算
    bbox_full = font.getbbox(text, stroke_width=total_stroke)
    rx = x + bbox_full[0]
    ry = y + bbox_full[1]
    rw = bbox_full[2] - bbox_full[0]
    rh = bbox_full[3] - bbox_full[1]

    if rw <= 0 or rh <= 0:
        return

    # 領域内ローカル座標
    lx = x - rx
    ly = y - ry

    # --- マスク作成 ---
    # テキスト本体（グリフのみ）
    text_mask = Image.new("L", (rw, rh), 0)
    ImageDraw.Draw(text_mask).text((lx, ly), text, font=font, fill=255)

    # 内側アウトライン領域（グリフ + inner_width）
    if inner_outline_width > 0:
        inner_mask = Image.new("L", (rw, rh), 0)
        ImageDraw.Draw(inner_mask).text(
            (lx, ly), text, font=font, fill=255,
            stroke_width=inner_outline_width, stroke_fill=255,
        )
    else:
        inner_mask = text_mask.copy()

    # 外側アウトライン領域（グリフ + inner + outer）
    if total_stroke > 0:
        outer_mask = Image.new("L", (rw, rh), 0)
        ImageDraw.Draw(outer_mask).text(
            (lx, ly), text, font=font, fill=255,
            stroke_width=total_stroke, stroke_fill=255,
        )
    else:
        outer_mask = inner_mask.copy()

    # --- リングマスク（差分） ---
    outer_ring = ImageChops.subtract(outer_mask, inner_mask)
    inner_ring = ImageChops.subtract(inner_mask, text_mask)

    # --- 描画 ---
    # 外側リング
    if outer_outline_width > 0:
        _paint_mask(img, outer_ring, (rx, ry), outer_outline_color)

    # 内側リング
    if inner_outline_width > 0:
        _paint_mask(img, inner_ring, (rx, ry), inner_outline_color)

    # テキスト塗り（グリフ形状のみ、膨張なし）
    if gradient:
        _draw_gradient_fill(img, text_mask, (rx, ry), gradient)
    else:
        _paint_mask(img, text_mask, (rx, ry), color)


def _paint_mask(
    img: Image.Image,
    mask: Image.Image,
    pos: tuple[int, int],
    hex_color: str,
) -> None:
    """マスク領域をhex色で塗りimg上に合成"""
    rgba = _hex_to_rgb(hex_color) + (255,)
    layer = Image.new("RGBA", mask.size, rgba)
    layer.putalpha(mask)
    img.paste(layer, pos, layer)


def _draw_gradient_fill(
    img: Image.Image,
    mask: Image.Image,
    pos: tuple[int, int],
    gradient: tuple[str, str],
) -> None:
    """マスク形状にグラデーションを適用してimg上に合成"""
    w, h = mask.size
    c1 = _hex_to_rgb(gradient[0])
    c2 = _hex_to_rgb(gradient[1])

    grad_img = Image.new("RGBA", (w, h))
    grad_draw = ImageDraw.Draw(grad_img)
    for row in range(h):
        t = row / max(1, h - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        grad_draw.line([(0, row), (w - 1, row)], fill=(r, g, b, 255))

    grad_img.putalpha(mask)
    img.paste(grad_img, pos, grad_img)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """#RRGGBB → (R, G, B)"""
    try:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return (255, 255, 255)
        return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except (ValueError, AttributeError):
        return (255, 255, 255)


# ---------------------------------------------------------------------------
# 高レベル関数
# ---------------------------------------------------------------------------


def generate_title_image(
    title: str,
    keywords: list[str],
    output_path: Path,
    orientation: str = "vertical",
    client: "openai.OpenAI | None" = None,
    model: str = "gpt-4.1-mini",
    font_dir: Path | None = None,
    frame_path: Path | None = None,
) -> Path | None:
    """タイトル画像を生成する高レベル関数

    Returns:
        生成した画像のPath。失敗時はNone。
    """
    # 画像サイズ
    if orientation == "vertical":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    # frame.pngの色を抽出
    frame_colors = None
    if frame_path and frame_path.exists():
        frame_colors = extract_frame_colors(frame_path)

    # デザインキャッシュ確認
    cache_path = output_path.with_suffix(".title.json")
    design = None

    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            design = _parse_design_json(raw)
            logger.info(f"タイトルデザインキャッシュ読み込み: {cache_path.name}")
        except Exception as e:
            logger.warning(f"キャッシュ読み込み失敗: {e}")

    # AI設計
    if design is None and client is not None:
        try:
            design = design_title_layout(
                client=client,
                title=title,
                keywords=keywords,
                frame_colors=frame_colors,
                orientation=orientation,
                model=model,
            )
            # キャッシュ保存
            _save_design_cache(design, cache_path)
            logger.info(f"AIタイトルデザイン生成: {title}")
        except Exception as e:
            logger.warning(f"AIタイトルデザイン失敗、フォールバック使用: {e}")

    # フォールバック
    if design is None:
        design = create_fallback_design(title)
        logger.info(f"フォールバックデザイン使用: {title}")

    # 描画
    try:
        result = render_title_image(
            design=design,
            output_path=output_path,
            width=width,
            height=height,
            font_dir=font_dir,
        )
        logger.info(f"タイトル画像生成完了: {result}")
        return result
    except Exception as e:
        logger.error(f"タイトル画像描画失敗: {e}")
        return None


def _save_design_cache(design: TitleImageDesign, path: Path) -> None:
    """デザインをJSONキャッシュとして保存"""
    data = {
        "lines": [
            {
                "segments": [
                    {
                        "text": seg.text,
                        "font_size": seg.font_size,
                        "color": seg.color,
                        "gradient": list(seg.gradient) if seg.gradient else None,
                        "weight": seg.weight,
                    }
                    for seg in line.segments
                ],
                "outer_outline_color": line.outer_outline_color,
                "outer_outline_width": line.outer_outline_width,
                "inner_outline_color": line.inner_outline_color,
                "inner_outline_width": line.inner_outline_width,
            }
            for line in design.lines
        ],
        "line_spacing": design.line_spacing,
        "padding_top": design.padding_top,
    }
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    # アトミック書き込み: 一時ファイルに書いてからリネーム
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # 失敗時は一時ファイルを削除
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# バッチAPI呼び出し（複数タイトルを1回で設計）
# ---------------------------------------------------------------------------

_BATCH_PROMPT_TEMPLATE = """あなたはYouTubeショート動画のタイトルテキストデザイナーです。
以下の複数タイトルそれぞれについて、動画上部に表示するキャッチーな2-3行テキストにデザインしてください。

## 最重要ルール
- 各タイトルの文字は一切変更・省略・言い換えしないこと
- 全セグメントのtextを結合した結果が元タイトルと完全一致すること

## タイトル一覧
{TITLES}

## キーワード
{KEYWORDS}

## 背景フレームの色情報
{FRAME_COLORS}

## 画面向き
{ORIENTATION}

## デザインルール
1. 2-3行に分割（意味の切れ目、インパクト重視で改行）
2. 各行内をさらにセグメントに分割（強調語・句読点・助詞などで区切る）
3. 最も伝えたい語句を大きく（font_size: 80-100）、接続詞・助詞・句読点を小さく（50-70）
4. 背景フレームの色に映える配色を選ぶ
5. 白文字や明るい色の文字は黒の外アウトラインのみ（inner_outline_width=0）でシンプルに
6. グラデーションセグメントのみ二重アウトライン（外側=暗色、内側=明色）で装飾する
7. 強調セグメントにgradientを使う（2色の縦グラデーション）
8. weightは強調語=Eb、補足=Bd、句読点=Rg

## 出力JSON
designsキーに各タイトルのデザインを配列で返してください:
{{"designs": [{JSON_SCHEMA}, ...]}}
"""


def design_title_layouts_batch(
    client: "openai.OpenAI",
    titles: list[str],
    keywords_list: list[list[str]],
    frame_colors: list[str] | None = None,
    orientation: str = "vertical",
    model: str = "gpt-4.1-mini",
) -> list[TitleImageDesign | None]:
    """複数タイトルを1回のAPI呼び出しでまとめて設計させる"""
    titles_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))

    # キーワードをタイトルごとにまとめる
    kw_lines = []
    for i, kws in enumerate(keywords_list):
        if kws:
            kw_lines.append(f"{i+1}. {', '.join(kws)}")
    keywords_text = "\n".join(kw_lines) if kw_lines else "なし"

    frame_info = "なし（デフォルトの配色で設計してください）"
    if frame_colors:
        frame_info = ", ".join(frame_colors)

    prompt = _BATCH_PROMPT_TEMPLATE.replace("{TITLES}", titles_text)
    prompt = prompt.replace("{KEYWORDS}", keywords_text)
    prompt = prompt.replace("{FRAME_COLORS}", frame_info)
    prompt = prompt.replace("{ORIENTATION}", orientation)
    prompt = prompt.replace("{JSON_SCHEMA}", _JSON_SCHEMA)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("AIレスポンスが空です")
    raw = json.loads(content)
    designs_raw = raw.get("designs", [])

    results: list[TitleImageDesign | None] = []
    for i, title in enumerate(titles):
        if i >= len(designs_raw):
            results.append(None)
            continue
        try:
            design = _parse_design_json(designs_raw[i])
            # バリデーション
            reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
            if reconstructed != title:
                logger.warning(f"AIがタイトル文字を変更 (#{i+1}): {title!r} -> {reconstructed!r}")
                results.append(None)
            else:
                results.append(design)
        except Exception as e:
            logger.warning(f"バッチデザインパース失敗 (#{i+1}): {e}")
            results.append(None)

    return results


# ---------------------------------------------------------------------------
# バッチ画像生成（GUI/CLI共通）
# ---------------------------------------------------------------------------


def generate_title_images_batch(
    suggestions: list,
    output_dir: Path,
    orientation: str = "vertical",
    client: "openai.OpenAI | None" = None,
    model: str = "gpt-4.1-mini",
    font_dir: Path | None = None,
    frame_path: Path | None = None,
    sanitize_fn: "Callable[[str], str] | None" = None,
) -> dict[int, Path]:
    """複数候補のタイトル画像をバッチ生成する。

    Args:
        suggestions: titleとkeywords属性を持つ候補のリスト
        output_dir: 出力ディレクトリ（title_images/）
        sanitize_fn: ファイル名サニタイズ関数（省略時は簡易サニタイズ）

    Returns:
        {1: Path, 2: Path, ...} 生成成功した画像のマッピング
    """
    if sanitize_fn is None:
        def sanitize_fn(t: str) -> str:
            return t.replace("/", "_").replace("\\", "_")[:50] or "untitled"

    output_dir.mkdir(parents=True, exist_ok=True)

    if orientation == "vertical":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    # frame色抽出（1回だけ）
    frame_colors = None
    if frame_path and frame_path.exists():
        frame_colors = extract_frame_colors(frame_path)

    titles = [s.title for s in suggestions]
    keywords_list = [getattr(s, "keywords", []) for s in suggestions]

    # キャッシュ確認 + 未キャッシュ分をまとめてAI呼び出し
    designs: list[TitleImageDesign | None] = [None] * len(suggestions)
    uncached_indices: list[int] = []

    for i, s in enumerate(suggestions):
        sanitized = sanitize_fn(s.title)
        cache_path = (output_dir / f"{i+1:02d}_{sanitized}.title.json")
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                designs[i] = _parse_design_json(raw)
                logger.info(f"キャッシュ読み込み: {cache_path.name}")
            except Exception:
                uncached_indices.append(i)
        else:
            uncached_indices.append(i)

    # バッチAI呼び出し（未キャッシュ分をまとめて1回）
    if uncached_indices and client is not None:
        uncached_titles = [titles[i] for i in uncached_indices]
        uncached_keywords = [keywords_list[i] for i in uncached_indices]
        try:
            batch_results = design_title_layouts_batch(
                client=client,
                titles=uncached_titles,
                keywords_list=uncached_keywords,
                frame_colors=frame_colors,
                orientation=orientation,
                model=model,
            )
            for j, idx in enumerate(uncached_indices):
                if j < len(batch_results) and batch_results[j] is not None:
                    designs[idx] = batch_results[j]
                    # キャッシュ保存
                    sanitized = sanitize_fn(titles[idx])
                    cache_path = output_dir / f"{idx+1:02d}_{sanitized}.title.json"
                    _save_design_cache(batch_results[j], cache_path)
        except Exception as e:
            logger.warning(f"バッチAI呼び出し失敗: {e}")

    # フォールバック + 描画
    result_paths: dict[int, Path] = {}
    for i, s in enumerate(suggestions):
        if designs[i] is None:
            designs[i] = create_fallback_design(s.title)

        sanitized = sanitize_fn(s.title)
        output_path = output_dir / f"{i+1:02d}_{sanitized}.png"
        try:
            render_title_image(
                design=designs[i],
                output_path=output_path,
                width=width,
                height=height,
                font_dir=font_dir,
            )
            result_paths[i + 1] = output_path
            logger.info(f"タイトル画像: {output_path.name}")
        except Exception as e:
            logger.error(f"タイトル画像描画失敗 (#{i+1}): {e}")

    return result_paths
