"""
タイトル画像生成モジュール

GPT-4.1-miniがタイトルのレイアウト（行分割・サイズ・色・グラデーション）をJSON設計し、
Pillowが透過PNG画像として描画する。FCPXMLにオーバーレイとして配置する用途。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageChops = ImageDraw = ImageFilter = ImageFont = None  # type: ignore[assignment,misc]

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

    # 4. 最終フォールバック: システム上の任意の日本語フォント
    for fallback in [
        Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),  # Linux (Noto)
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),  # Linux variant
    ]:
        if fallback.exists():
            return str(fallback)
    logger.warning(f"フォントが見つかりません: {filename}。デフォルトフォントを使用します。")
    return ""


# ---------------------------------------------------------------------------
# frame.png 色抽出
# ---------------------------------------------------------------------------


def extract_frame_colors(frame_path: Path, num_colors: int = 5) -> list[str]:
    """frame.pngから支配色を抽出し、hex文字列リストで返す"""
    if Image is None:
        raise ImportError("Pillow is required for title image generation. Install it with: pip install Pillow>=10.0.0")
    try:
        with Image.open(frame_path) as raw_img:
            img = raw_img.convert("RGBA")
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
# コントラスト計算・自動補正
# ---------------------------------------------------------------------------

_TEXT_VS_OUTLINE_THRESHOLD = 2.0

# 輝度しきい値（テキスト色が暗い→内縁不要）
_DARK_TEXT_LUMINANCE = 0.15

# ドロップシャドウ
_SHADOW_COLOR = "#000000"
_SHADOW_OPACITY = 80
_SHADOW_BLUR_RADIUS = 8
_SHADOW_OFFSET_X = 4
_SHADOW_OFFSET_Y = 4

# 文字内ループ穴の inner_mask 穴埋め用閾値
# (font_size * RATIO)² 以下の穴のみ inner で塗る (黒インナー対象)。
# - RATIO=0.06 で「使」の中の小さな閉じ領域は埋まる (~130px² @ font 190)
# - 「き」の横棒間隙間 (~150-300px²) は埋まらず、文字細部が維持される
# - 「な」「は」のループ穴 (~3000+px²) は埋まらず、中央が outer の白で見える
_INNER_HOLE_AREA_RATIO = 0.06
# 極小フォント時の最小閾値 (px²)
_INNER_HOLE_AREA_MIN_PX2 = 36


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.0 相対輝度を計算 (0.0=黒, 1.0=白)"""
    r, g, b = _hex_to_rgb(hex_color)

    def srgb(c: int) -> float:
        c_norm = c / 255.0
        return c_norm / 12.92 if c_norm <= 0.04045 else ((c_norm + 0.055) / 1.055) ** 2.4

    return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)


def _get_segment_luminance(seg: TitleTextSegment) -> float:
    """セグメントの色の最大輝度を返す（グラデーション対応）"""
    if seg.gradient:
        return max(_relative_luminance(c) for c in seg.gradient)
    if seg.color and seg.color.startswith("#"):
        return _relative_luminance(seg.color)
    return 1.0  # デフォルト（明るい扱い）


def _contrast_ratio(color1: str, color2: str) -> float:
    """WCAG 2.0 コントラスト比を計算 (1.0〜21.0)"""
    l1 = _relative_luminance(color1)
    l2 = _relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _force_outline_style(design: TitleImageDesign) -> TitleImageDesign:
    """白外縁 + テキスト色に応じた内縁色を強制適用する。

    - outer_outline_color = "#FFFFFF"（常に白）
    - outer_outline_width = max(現状, 10)
    - テキストが暗い（黒系）→ inner_outline_width=0（黒文字+白外縁で十分）
    - テキストが明るい/カラー/グラデーション → inner_outline_color="#000000", inner_outline_width=max(現状, 6)
    """
    import copy

    design = copy.deepcopy(design)

    for line in design.lines:
        # 全セグメントのウェイトを最太(Eb)に統一
        for seg in line.segments:
            seg.weight = "Eb"

        # 行内の全セグメントの輝度を調べ、最も明るいセグメントで判定
        max_luminance = 0.0
        has_gradient = False
        for seg in line.segments:
            if seg.gradient:
                has_gradient = True
                for gc in seg.gradient:
                    max_luminance = max(max_luminance, _relative_luminance(gc))
            elif seg.color and seg.color.startswith("#"):
                max_luminance = max(max_luminance, _relative_luminance(seg.color))

        # 外縁: 常に白
        line.outer_outline_color = "#FFFFFF"
        line.outer_outline_width = max(line.outer_outline_width, 10)

        # 内縁: テキスト色の輝度で判定
        if not has_gradient and max_luminance < _DARK_TEXT_LUMINANCE:
            # テキストが暗い（黒系）→ 内縁不要
            line.inner_outline_width = 0
        else:
            # テキストが明るい/カラー/グラデーション → 黒内縁
            line.inner_outline_color = "#000000"
            line.inner_outline_width = max(line.inner_outline_width, 6)

    return design


def _shrink_particles(design: TitleImageDesign) -> TitleImageDesign:
    """助詞（は、が、を等）を80%サイズに縮小する。

    GiNZA形態素解析でPOS=ADP（助詞）を検出し、該当部分のfont_sizeを0.8倍にする。
    GiNZA未インストール時はスキップ。
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
    except ImportError:
        return design

    new_lines = []

    for line in design.lines:
        line_text = "".join(seg.text for seg in line.segments)
        if not line_text:
            new_lines.append(line)
            continue

        try:
            token_info = JapaneseLineBreakRules.get_word_boundaries_with_pos(line_text)
        except Exception:
            new_lines.append(line)
            continue

        if not token_info:
            new_lines.append(line)
            continue

        # トークンごとに助詞かどうかのマップを作成 (char_start, char_end, is_particle)
        particle_ranges: list[tuple[int, int, bool]] = []
        for end_pos, surface, pos_tag in token_info:
            start = end_pos - len(surface)
            is_particle = pos_tag.startswith("助詞")
            particle_ranges.append((start, end_pos, is_particle))

        # 既存セグメントを助詞境界で分割
        new_segments: list[TitleTextSegment] = []
        seg_start = 0
        for seg in line.segments:
            seg_end = seg_start + len(seg.text)

            # このセグメント範囲内のトークンを収集
            parts: list[tuple[str, bool]] = []
            cursor = seg_start
            for t_start, t_end, is_p in particle_ranges:
                if t_end <= seg_start or t_start >= seg_end:
                    continue
                c_start = max(t_start, seg_start)
                c_end = min(t_end, seg_end)
                if c_start < c_end:
                    if cursor < c_start:
                        parts.append((line_text[cursor:c_start], False))
                    parts.append((line_text[c_start:c_end], is_p))
                    cursor = c_end
            if cursor < seg_end:
                parts.append((line_text[cursor:seg_end], False))

            # 隣接する同種パートをマージ
            merged: list[tuple[str, bool]] = []
            for text, is_p in parts:
                if merged and merged[-1][1] == is_p:
                    merged[-1] = (merged[-1][0] + text, is_p)
                else:
                    merged.append((text, is_p))

            for text, is_p in merged:
                if not text:
                    continue
                new_seg = TitleTextSegment(
                    text=text,
                    font_size=int(seg.font_size * 0.8) if is_p else seg.font_size,
                    color=seg.color,
                    gradient=seg.gradient,
                    weight="Eb",
                )
                new_segments.append(new_seg)

            seg_start = seg_end

        if new_segments:
            new_lines.append(
                TitleLine(
                    segments=new_segments,
                    outer_outline_color=line.outer_outline_color,
                    outer_outline_width=line.outer_outline_width,
                    inner_outline_color=line.inner_outline_color,
                    inner_outline_width=line.inner_outline_width,
                )
            )
        else:
            new_lines.append(line)

    return TitleImageDesign(
        lines=new_lines,
        line_spacing=design.line_spacing,
        padding_top=design.padding_top,
    )


def _ensure_contrast(design: TitleImageDesign, frame_colors: list[str]) -> TitleImageDesign:
    """テキスト色と白外縁のコントラストが低い場合に自動補正する。

    _force_outline_style()で白外縁が強制されるため、外縁色の変更は行わない。
    テキスト色が白外縁と同化する場合のみ補正する。

    内部で _force_outline_style() を適用してから判定するため、
    呼び出し順序に依存しない。
    """
    if not frame_colors:
        return design

    # 白外縁を先に適用してからコントラスト判定する（deepcopyも兼ねる）
    design = _force_outline_style(design)

    for line in design.lines:
        for seg in line.segments:
            text_colors = []
            if seg.gradient:
                text_colors.extend(list(seg.gradient))
            elif seg.color and seg.color.startswith("#"):
                text_colors.append(seg.color)

            for tc in text_colors:
                ratio = _contrast_ratio(tc, line.outer_outline_color)
                if ratio < _TEXT_VS_OUTLINE_THRESHOLD:
                    outline_luminance = _relative_luminance(line.outer_outline_color)
                    new_color = "#FFFFFF" if outline_luminance < 0.5 else "#000000"
                    if not seg.gradient and seg.color == tc:
                        logger.info(
                            "コントラスト補正: テキスト色 %s → %s (比率%.2f < %.1f)",
                            tc,
                            new_color,
                            ratio,
                            _TEXT_VS_OUTLINE_THRESHOLD,
                        )
                        seg.color = new_color

    return design


# ---------------------------------------------------------------------------
# 高さ制限の自動補正
# ---------------------------------------------------------------------------


def _measure_content_height(
    design: TitleImageDesign,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_dir: Path | None = None,
    offset_y: int = 0,
) -> int:
    """デザインをレンダリングして実際のコンテンツ高さを測定する"""
    fd, tmp_str = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    tmp_path = Path(tmp_str)
    try:
        render_title_image(
            design, tmp_path, width=canvas_width, height=canvas_height, font_dir=font_dir, offset_y=offset_y
        )
        with Image.open(tmp_path) as img:
            bbox = img.getbbox()
            if bbox:
                return bbox[3]
        return 0
    finally:
        tmp_path.unlink(missing_ok=True)


def _measure_content_bbox(
    design: TitleImageDesign,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_dir: Path | None = None,
    offset_y: int = 0,
) -> tuple[int, int, int, int] | None:
    """デザインをレンダリングして非透過ピクセルの bbox (x0, y0, x1, y1) を返す。

    `_measure_content_height` は bbox[3] (下端 y) のみ返すが、中央配置計算には
    上端 y0 も必要なため別関数で全 bbox を返す。
    """
    fd, tmp_str = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    tmp_path = Path(tmp_str)
    try:
        render_title_image(
            design, tmp_path, width=canvas_width, height=canvas_height, font_dir=font_dir, offset_y=offset_y
        )
        with Image.open(tmp_path) as img:
            return img.getbbox()
    finally:
        tmp_path.unlink(missing_ok=True)


def _ensure_fit_height(
    design: TitleImageDesign,
    target_height: int,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_dir: Path | None = None,
    offset_y: int = 0,
) -> TitleImageDesign:
    """コンテンツがtarget_heightに収まるようにフォントサイズを縮小する"""
    import copy

    design = copy.deepcopy(design)

    for _ in range(5):
        content_h = _measure_content_height(design, canvas_width, canvas_height, font_dir, offset_y)
        if content_h <= 0 or content_h <= target_height:
            return design

        scale = (target_height / content_h) * 0.95
        logger.info(
            "高さ補正: %dpx → target %dpx (縮小率%.3f)",
            content_h,
            target_height,
            scale,
        )
        for line in design.lines:
            for seg in line.segments:
                seg.font_size = max(30, int(seg.font_size * scale))
        design.line_spacing = max(0, int(design.line_spacing * scale))

    return design


def _center_design_in_target(
    design: TitleImageDesign,
    target_height: int,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_dir: Path | None = None,
    offset_y: int = 0,
) -> TitleImageDesign:
    """target_height 範囲内でコンテンツが縦中央に来るよう padding_top を再計算する。

    Phase C 改善: 1 行短いタイトルだと content_height が target より遥かに小さく、
    画像上端だけ占有する見た目になっていた問題を解消。
    target_size 指定時のみ呼ぶ (= タイトル領域が明確に定まっている場合)。

    アルゴリズム:
      1. 現状の design で bbox 測定 → 文字の上端 y0_curr / 下端 y1_curr
      2. content_h = y1_curr - y0_curr
      3. 中央配置したい上端: target_y0 = (target_height - content_h) / 2
      4. ずらす量 delta = target_y0 - y0_curr
      5. 新 padding_top = 既存 padding_top + delta
    """
    import copy

    bbox = _measure_content_bbox(design, canvas_width, canvas_height, font_dir, offset_y)
    if bbox is None:
        return design
    y0, y1 = bbox[1], bbox[3]
    content_h = y1 - y0
    if content_h <= 0 or content_h >= target_height:
        return design

    target_y0 = (target_height - content_h) // 2
    delta = target_y0 - y0
    if delta == 0:
        return design
    centered = copy.deepcopy(design)
    centered.padding_top = max(0, design.padding_top + delta)
    logger.info(
        "縦中央配置: padding_top %d → %d (target_h=%d, content_h=%d, delta=%+d)",
        design.padding_top, centered.padding_top, target_height, content_h, delta,
    )
    return centered


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
    prompt = prompt.replace("{MAX_LINE_CHARS}", str(_TITLE_FORCE_BREAK_THRESHOLD))
    prompt = prompt.replace("{MAX_LINE_CHARS_DOUBLE}", str(_TITLE_FORCE_BREAK_THRESHOLD * 2))

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
    design = _snap_segments_to_word_boundaries(design)

    # バリデーション: AIが文字を書き換えていないか確認
    reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
    if reconstructed != title:
        logger.warning(
            f"AIがタイトル文字を変更しました (期待: {title!r}, 実際: {reconstructed!r})。フォールバック使用。"
        )
        raise ValueError("AIがタイトル文字を変更しました")

    # Phase B: 1 line で _TITLE_FORCE_BREAK_THRESHOLD 超のタイトルは強制分割。
    # AI がプロンプトを守らず単一行で返したケースの保険。
    design = _enforce_line_break(design)

    return design


def _enforce_line_break(design: TitleImageDesign) -> TitleImageDesign:
    """単一行のタイトルが閾値を超えていたら fallback の split で複数行に再構成する。"""
    if len(design.lines) != 1:
        return design
    text = "".join(seg.text for seg in design.lines[0].segments)
    if len(text) <= _TITLE_FORCE_BREAK_THRESHOLD:
        return design

    parts = _split_title(text, max_lines=3)
    if len(parts) <= 1:
        return design

    # 既存 line のスタイルを継承して複数行を再構成
    base_line = design.lines[0]
    new_lines: list[TitleLine] = []
    for part in parts:
        new_lines.append(
            TitleLine(
                segments=[
                    TitleTextSegment(
                        text=part,
                        font_size=base_line.segments[0].font_size if base_line.segments else 160,
                        color=base_line.segments[0].color if base_line.segments else "#000000",
                        gradient=base_line.segments[0].gradient if base_line.segments else None,
                        weight=base_line.segments[0].weight if base_line.segments else "Eb",
                    )
                ],
                outer_outline_color=base_line.outer_outline_color,
                outer_outline_width=base_line.outer_outline_width,
                inner_outline_color=base_line.inner_outline_color,
                inner_outline_width=base_line.inner_outline_width,
            )
        )
    logger.info(
        "AI returned 1-line for %d-char title (>%d); force-split into %d lines",
        len(text), _TITLE_FORCE_BREAK_THRESHOLD, len(new_lines),
    )
    return TitleImageDesign(
        lines=new_lines,
        line_spacing=design.line_spacing,
        padding_top=design.padding_top,
    )


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
- **タイトル全文が {MAX_LINE_CHARS} 文字を超える場合は必ず複数行 (lines を 2 個以上) に分割すること**。1 行のままだと font_size が縮小されて非常に見にくくなる

## デザインルール
1. 2-3行に分割（意味の切れ目、インパクト重視で改行）
2. 各行内をさらにセグメントに分割（強調語・句読点・助詞などで区切る）
3. 最も伝えたい語句を非常に大きく（font_size: 160-200）、補足・接続詞・助詞も大きめに（110-140）
4. 配色は背景フレームの色に合わせて選ぶ。背景色と同系色のテキストは避ける
5. 外アウトラインは常に白(#FFFFFF)、outer_outline_width=10
6. テキスト色が暗い→inner_outline_width=0。明るい/カラー/グラデーション→inner_outline_color="#000000", inner_outline_width=6
7. 強調セグメントにgradientを使う（2色の縦グラデーション）
8. weightは全セグメント Eb 固定

## 出力JSON
{JSON_SCHEMA}
"""


# ---------------------------------------------------------------------------
# 複数候補生成パイプライン (Stage 1-3)
# ---------------------------------------------------------------------------


def design_title_layout_candidates(
    client: "openai.OpenAI",
    title: str,
    keywords: list[str],
    target_size: tuple[int, int],
    frame_colors: list[str] | None = None,
    orientation: str = "vertical",
    model: str = "gpt-4.1-mini",
    num_candidates: int = 6,
    srt_text: str | None = None,
) -> list[TitleImageDesign]:
    """AIに複数のデザイン候補を1回のAPI呼び出しで生成させる (Stage 1)。

    Phase A: srt_text が渡された場合は SRT ベースで AI が自由にタイトル文字列を
    生成する (= 元 title からの大幅書き換え許容)。バリデーションも緩和。
    """
    is_srt_mode = srt_text is not None
    prompt_filename = (
        "title_image_candidates_from_srt.md" if is_srt_mode else "title_image_candidates.md"
    )
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / prompt_filename
    if prompt_path.exists():
        prompt_template = prompt_path.read_text(encoding="utf-8")
    else:
        logger.warning(f"{prompt_filename} が見つかりません。デフォルトプロンプトで1候補生成に切り替えます。")
        prompt_template = _DEFAULT_PROMPT

    frame_info = "なし（デフォルトの配色で設計してください）"
    if frame_colors:
        frame_info = ", ".join(frame_colors)

    prompt = prompt_template.replace("{TITLE}", title)
    prompt = prompt.replace("{KEYWORDS}", ", ".join(keywords) if keywords else "なし")
    prompt = prompt.replace("{FRAME_COLORS}", frame_info)
    prompt = prompt.replace("{JSON_SCHEMA}", _JSON_SCHEMA)
    prompt = prompt.replace("{ORIENTATION}", orientation)
    prompt = prompt.replace("{TARGET_WIDTH}", str(target_size[0]))
    prompt = prompt.replace("{TARGET_HEIGHT}", str(target_size[1]))
    prompt = prompt.replace("{NUM_CANDIDATES}", str(num_candidates))
    prompt = prompt.replace("{MAX_LINE_CHARS}", str(_TITLE_FORCE_BREAK_THRESHOLD))
    prompt = prompt.replace("{MAX_LINE_CHARS_DOUBLE}", str(_TITLE_FORCE_BREAK_THRESHOLD * 2))
    if is_srt_mode:
        prompt = prompt.replace("{SRT_TEXT}", srt_text or "")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.9,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("AIレスポンスが空です")
    raw = json.loads(content)
    designs_raw = raw.get("designs", [])

    results: list[TitleImageDesign] = []
    for i, design_raw in enumerate(designs_raw):
        try:
            design = _parse_design_json(design_raw)
            design = _snap_segments_to_word_boundaries(design)
            reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
            if not is_srt_mode:
                # 既存モード: 文字一致チェック
                if reconstructed != title:
                    logger.warning(
                        f"候補#{i+1}: AIがタイトル文字を変更 (期待: {title!r}, 実際: {reconstructed!r})。スキップ。"
                    )
                    continue
            else:
                # SRT モード: AI 自由生成のため文字一致は不要。空タイトルのみ排除。
                if not reconstructed.strip():
                    logger.warning(f"候補#{i+1}: 空タイトルのためスキップ")
                    continue
            # Phase B: 1 line で閾値超なら強制分割
            design = _enforce_line_break(design)
            results.append(design)
        except Exception as e:
            logger.warning(f"候補#{i+1}: パース失敗: {e}")
            continue

    return results


def filter_fitting_candidates(
    candidates: list[TitleImageDesign],
    target_width: int,
    target_height: int,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    font_dir: Path | None = None,
    offset_y: int = 0,
) -> tuple[list[tuple[TitleImageDesign, Path, int, int]], list[Path]]:
    """候補をレンダリングし、ターゲットエリアに収まるものをフィルタする (Stage 2)

    Returns:
        (fitting_candidates, all_tmp_dirs):
        - fitting_candidates: [(design, rendered_path, width, content_height), ...]
          ターゲットに収まる候補。収まるものがない場合はアスペクト比が近い上位3つ。
        - all_tmp_dirs: クリーンアップが必要な全一時ディレクトリ
    """
    all_rendered: list[tuple[TitleImageDesign, Path, int, int]] = []
    all_tmp_dirs: list[Path] = []

    for i, design in enumerate(candidates):
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="title_candidate_"))
            all_tmp_dirs.append(tmp_dir)
            tmp_path = tmp_dir / f"candidate_{i:02d}.png"
            _, img_w, img_h = render_title_image(
                design=design,
                output_path=tmp_path,
                width=canvas_width,
                height=canvas_height,
                font_dir=font_dir,
                offset_y=offset_y,
            )
            # フルサイズ透過PNGから実コンテンツ高さを計測
            content_h = img_h
            try:
                with Image.open(tmp_path) as rendered_img:
                    bbox = rendered_img.getbbox()  # 非透過ピクセルのバウンディングボックス
                    if bbox:
                        content_h = bbox[3]  # bottom-y = コンテンツの下端
            except Exception:
                pass
            all_rendered.append((design, tmp_path, img_w, content_h))
        except Exception as e:
            logger.warning(f"候補#{i+1}: レンダリング失敗: {e}")
            continue

    if not all_rendered:
        return [], all_tmp_dirs

    # ターゲットエリア（上部エリア）に収まるものをフィルタ
    fitting = [(d, p, w, h) for d, p, w, h in all_rendered if h <= target_height]

    if fitting:
        return fitting, all_tmp_dirs

    # 収まるものがない場合: アスペクト比が近い上位3つをフォールバック
    logger.warning(
        f"ターゲット({target_width}x{target_height})に収まる候補なし。"
        f"アスペクト比が近い候補をフォールバックとして返します。"
    )
    target_ratio = target_height / target_width if target_width > 0 else 1.0
    all_rendered.sort(key=lambda x: abs((x[3] / x[2] if x[2] > 0 else 0) - target_ratio))
    return all_rendered[:3], all_tmp_dirs


def evaluate_candidates_with_vision(
    client: "openai.OpenAI",
    candidate_images: list[tuple[int, Path]],
    title: str,
    model: str = "gpt-4o",
) -> int:
    """Vision AIで候補画像を評価し、最適なインデックスを返す (Stage 3)"""
    if not candidate_images:
        return 0

    if len(candidate_images) == 1:
        return candidate_images[0][0]

    # 候補画像をbase64エンコード（成功した候補のインデックスも追跡）
    image_contents = []
    encoded_candidates: list[tuple[int, Path]] = []
    for idx, img_path in candidate_images:
        try:
            with open(img_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            image_contents.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_data}",
                        "detail": "low",
                    },
                }
            )
            encoded_candidates.append((idx, img_path))
        except Exception as e:
            logger.warning(f"画像#{idx}: base64エンコード失敗: {e}")

    if not image_contents:
        return candidate_images[0][0]

    # エンコード成功が1枚のみならAPI不要
    if len(encoded_candidates) == 1:
        return encoded_candidates[0][0]

    # 評価プロンプト
    prompt_text = (
        f"以下は「{title}」というタイトルのデザイン候補画像です。\n"
        f"{len(image_contents)}枚の候補から最も良いものを1つ選んでください。\n\n"
        "評価基準:\n"
        "1. キャッチーさ・インパクト（目を引くか）\n"
        "2. 可読性（文字が読みやすいか）\n"
        "3. 色の調和・バランス\n"
        "4. テキストの収まり具合\n\n"
        'JSONで回答してください: {"best_index": N, "reason": "理由"}\n'
        "best_indexは0始まりで、画像の表示順です。"
    )

    messages_content = [{"type": "text", "text": prompt_text}]
    messages_content.extend(image_contents)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": messages_content}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if content:
            result = json.loads(content)
            best_idx = int(result.get("best_index", 0))
            reason = result.get("reason", "")
            if 0 <= best_idx < len(encoded_candidates):
                logger.info(f"Vision AI選定: 候補#{best_idx} — {reason}")
                return encoded_candidates[best_idx][0]
            else:
                logger.warning(f"Vision AIが無効なインデックスを返しました: {best_idx}")
    except Exception as e:
        logger.warning(f"Vision AI評価失敗: {e}")

    # フォールバック: エンコード成功した最初の候補
    return encoded_candidates[0][0] if encoded_candidates else candidate_images[0][0]


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
                    font_size=_clamp(_safe_int(seg_data.get("font_size"), 160), 80, 220),
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


def _snap_segments_to_word_boundaries(design: TitleImageDesign) -> TitleImageDesign:
    """AIセグメント境界をGiNZA単語境界にスナップする。

    AIが単語の途中で色を切り替えることを防ぐ。
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
    except ImportError:
        return design  # GiNZA未インストール時はそのまま返す

    new_lines = []
    for line in design.lines:
        if len(line.segments) <= 1:
            new_lines.append(line)
            continue

        line_text = "".join(seg.text for seg in line.segments)
        word_bounds = JapaneseLineBreakRules.get_word_boundaries(line_text)
        if not word_bounds:
            new_lines.append(line)  # 解析失敗時はそのまま
            continue

        valid_bounds = {0} | set(word_bounds)  # 0 と全トークン末端

        # 現在のセグメント境界を算出
        seg_boundaries = []
        pos = 0
        for seg in line.segments:
            pos += len(seg.text)
            seg_boundaries.append(pos)

        # 内部境界（最後＝行末を除く）をスナップ
        snapped = []
        for b in seg_boundaries[:-1]:
            if b in valid_bounds:
                snapped.append(b)
            else:
                nearest = min(valid_bounds, key=lambda v: abs(v - b))
                if nearest == 0:
                    # 0にスナップすると空セグメントになるので次の境界を探す
                    candidates = sorted(v for v in valid_bounds if v > 0)
                    nearest = candidates[0] if candidates else b
                snapped.append(nearest)
        snapped.append(len(line_text))  # 行末

        # 重複除去＆ソート、0を除外
        snapped = sorted(set(snapped))
        snapped = [b for b in snapped if b > 0]

        # 新セグメント構築（スタイルは中間点が属する元セグメントから継承）
        new_segments = []
        prev = 0
        for boundary in snapped:
            if boundary <= prev:
                continue
            text = line_text[prev:boundary]
            midpoint = (prev + boundary) / 2

            # midpointが属する元セグメントを特定
            orig_pos = 0
            source_seg = line.segments[0]  # フォールバック
            for orig_seg in line.segments:
                orig_end = orig_pos + len(orig_seg.text)
                if orig_pos <= midpoint < orig_end:
                    source_seg = orig_seg
                    break
                orig_pos = orig_end

            new_segments.append(
                TitleTextSegment(
                    text=text,
                    font_size=source_seg.font_size,
                    color=source_seg.color,
                    gradient=source_seg.gradient,
                    weight=source_seg.weight,
                )
            )
            prev = boundary

        if new_segments:
            new_lines.append(
                TitleLine(
                    segments=new_segments,
                    outer_outline_color=line.outer_outline_color,
                    outer_outline_width=line.outer_outline_width,
                    inner_outline_color=line.inner_outline_color,
                    inner_outline_width=line.inner_outline_width,
                )
            )
        else:
            new_lines.append(line)

    return TitleImageDesign(
        lines=new_lines,
        line_spacing=design.line_spacing,
        padding_top=design.padding_top,
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
        font_size = 180 if is_emphasis else 130
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
                outer_outline_color="#FFFFFF",
                outer_outline_width=10,
                inner_outline_color="#000000",
                inner_outline_width=6 if gradient else 0,
            )
        )

    return TitleImageDesign(lines=lines, padding_top=80, line_spacing=12)


_TITLE_FORCE_BREAK_THRESHOLD = 11
"""タイトル全文がこの文字数を超える場合、必ず複数行に分割する閾値 (Phase B)。

font_size 190 で 1080px 幅に収まる物理上限が ~11 文字程度。
それを超える長さで 1 行にすると font が縮小されて見にくくなるため強制改行。
"""


def _split_title(title: str, max_lines: int = 3) -> list[str]:
    """タイトルを自然な位置で分割"""
    if len(title) <= _TITLE_FORCE_BREAK_THRESHOLD:
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
    offset_y: int = 0,
) -> tuple[Path, int, int]:
    """デザインに基づいてタイトル画像をフルサイズ透過PNGとして描画する。

    フレーム画像と同じサイズの透過PNGを生成し、テキストは padding_top + offset_y の
    位置から描画される。これによりFCPXML上で position="0 0" で配置するだけで正確な位置になる。

    Args:
        offset_y: 垂直方向のオフセット（px）。正の値で下方向に移動。

    Returns:
        (output_path, image_width, image_height) — 画像サイズ（常にwidth x height）
    """
    if Image is None:
        raise ImportError("Pillow is required for title image generation. Install it with: pip install Pillow>=10.0.0")

    # 白外縁強制 + 助詞縮小を適用
    design = _force_outline_style(design)
    design = _shrink_particles(design)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin_x = 40  # 左右マージン
    usable_width = width - margin_x * 2
    current_y = design.padding_top + offset_y  # デザインのpadding_top + ユーザーオフセット

    # --- Phase 1: 全セグメントの位置・フォントを事前計算 ---
    draw_items: list[dict] = []

    for line in design.lines:
        fonts: list[ImageFont.FreeTypeFont] = []
        seg_widths: list[int] = []
        seg_heights: list[int] = []
        seg_ascents: list[int] = []

        for seg in line.segments:
            font_path = find_font(seg.weight, font_dir)
            if font_path:
                font = ImageFont.truetype(font_path, seg.font_size)
            else:
                font = ImageFont.load_default(size=seg.font_size)
            fonts.append(font)

            bbox = font.getbbox(seg.text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            ascent = -bbox[1]
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
                if font_path:
                    fonts[i] = ImageFont.truetype(font_path, new_size)
                else:
                    fonts[i] = ImageFont.load_default(size=new_size)
                bbox = fonts[i].getbbox(seg.text)
                seg_widths[i] = bbox[2] - bbox[0]
                seg_heights[i] = bbox[3] - bbox[1]
                seg_ascents[i] = -bbox[1]
            total_line_width = sum(seg_widths)

        max_vis_height = max(seg_heights) if seg_heights else 0
        start_x = margin_x + (usable_width - total_line_width) // 2
        x = start_x

        for i, seg in enumerate(line.segments):
            vis_top = current_y + (max_vis_height - seg_heights[i]) // 2
            y = vis_top + seg_ascents[i]
            actual_size = fonts[i].size
            outer_w = _scale_outline(line.outer_outline_width, actual_size)
            inner_w = _scale_outline(line.inner_outline_width, actual_size)

            # セグメント単位の内縁オーバーライド: 暗い文字には内縁不要
            if inner_w > 0 and _get_segment_luminance(seg) < _DARK_TEXT_LUMINANCE:
                inner_w = 0

            draw_items.append(
                {
                    "text": seg.text,
                    "xy": (x, y),
                    "font": fonts[i],
                    "color": seg.color,
                    "gradient": seg.gradient,
                    "outer_outline_color": line.outer_outline_color,
                    "outer_outline_width": outer_w,
                    "inner_outline_color": line.inner_outline_color,
                    "inner_outline_width": inner_w,
                }
            )
            x += seg_widths[i]

        current_y += max_vis_height + design.line_spacing

    # --- Phase 2: 4パス描画（影→外縁→内縁→テキスト塗り） ---
    # 影を最下層、外縁をその上に描画することで立体感を演出
    for layer in ("shadow", "outer", "inner", "text"):
        for item in draw_items:
            _draw_segment(
                img=img,
                draw=draw,
                layers=frozenset({layer}),
                **item,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return (output_path, width, height)


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
    layers: frozenset[str] | None = None,
) -> None:
    """1セグメントを二重アウトライン + グラデーション + ドロップシャドウ対応で描画

    リングマスク方式:
      1. テキスト / 内側 / 外側 の3段階マスクを作成
      2. 差分でリング（ドーナツ型）マスクを作り、各色で塗る
      3. テキスト塗りはグリフ形状のみ（膨張しない）
      4. シャドウは外側マスクをぼかしてオフセット位置に半透明描画

    Args:
        layers: 描画するレイヤーのセット。None で全レイヤー。
                "shadow", "outer", "inner", "text" の組み合わせ。
    """
    if layers is None:
        layers = frozenset({"shadow", "outer", "inner", "text"})

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
            (lx, ly),
            text,
            font=font,
            fill=255,
            stroke_width=inner_outline_width,
            stroke_fill=255,
        )
    else:
        inner_mask = text_mask.copy()

    # 外側アウトライン領域（グリフ + inner + outer）
    if total_stroke > 0:
        outer_mask = Image.new("L", (rw, rh), 0)
        ImageDraw.Draw(outer_mask).text(
            (lx, ly),
            text,
            font=font,
            fill=255,
            stroke_width=total_stroke,
            stroke_fill=255,
        )
    else:
        outer_mask = inner_mask.copy()

    # 「な」「は」「ぱ」「べ」「使」等の文字内ループ穴を埋める。
    # outer_mask: 全穴を埋めてシルエット全体で白アウトラインを塗りつぶす。
    # inner_mask: 小さい閉じ領域のみ埋める (大きいループ穴を埋めると黒インナーが
    #   文字の細部まで広がって潰れるため、面積上限で選別する)。
    outer_mask_solid = _fill_mask_holes(outer_mask)
    inner_hole_threshold = max(
        _INNER_HOLE_AREA_MIN_PX2,
        int((font.size * _INNER_HOLE_AREA_RATIO) ** 2),
    )
    inner_mask_solid = _fill_mask_holes(inner_mask, max_hole_area=inner_hole_threshold)

    # --- リングマスク（差分） ---
    inner_ring = ImageChops.subtract(inner_mask_solid, text_mask)

    # --- 描画 ---
    # ドロップシャドウ（外側マスクをぼかしてオフセット描画）
    # outer_outline_width=0 でもテキスト形状のシャドウを描画する（意図的）。
    # 穴埋め済み outer_mask_solid を使うことで、ループ穴のある文字でも
    # シャドウがソリッドシルエットでぼかされ、視覚的に自然になる。
    if "shadow" in layers:
        # パディング: blur半径の2倍でカーネル拡散を十分収容
        pad = _SHADOW_BLUR_RADIUS * 2
        padded_mask = Image.new("L", (rw + pad * 2, rh + pad * 2), 0)
        padded_mask.paste(outer_mask_solid, (pad, pad))
        blurred = padded_mask.filter(ImageFilter.GaussianBlur(radius=_SHADOW_BLUR_RADIUS))
        shadow_rgba = _hex_to_rgb(_SHADOW_COLOR) + (_SHADOW_OPACITY,)
        shadow_layer = Image.new("RGBA", blurred.size, shadow_rgba)
        shadow_layer.putalpha(blurred)
        sx = max(0, rx - pad + _SHADOW_OFFSET_X)
        sy = max(0, ry - pad + _SHADOW_OFFSET_Y)
        img.paste(shadow_layer, (sx, sy), shadow_layer)

    # 外側 (白アウトライン): リング差分ではなく、穴埋め済みシルエット全体を塗りつぶす。
    # ループ穴のある文字 (な/は/ぱ/べ等) でリング描画だと穴の内側に細リングが残り、
    # 「白アウトラインの隙間」として目立つ。シルエット全体塗りで穴の中まで白で覆う。
    if "outer" in layers and outer_outline_width > 0:
        _paint_mask(img, outer_mask_solid, (rx, ry), outer_outline_color)

    # 内側リング
    if "inner" in layers and inner_outline_width > 0:
        _paint_mask(img, inner_ring, (rx, ry), inner_outline_color)

    # テキスト塗り（グリフ形状のみ、膨張なし）
    if "text" in layers:
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


def _fill_mask_holes(mask: Image.Image, max_hole_area: int | None = None) -> Image.Image:
    """L モードマスクの内側の穴 (周囲を 255 に囲まれた 0 領域) を 255 で埋める。

    「な」「は」「ぱ」「べ」「使」等の文字内ループ穴を埋めて、白アウトラインを
    シルエット全体で塗りつぶすために使う。

    Args:
        max_hole_area: 埋める穴の最大面積 (px²)。None なら全穴を埋める (outer_mask 用)。
            指定すると面積 <= max_hole_area の穴のみ埋める。
            「使」の中の小さい閉じ領域だけ埋め、「な」「は」の大ループ穴 (黒インナーが
            広がりすぎると文字の細部が潰れる) は埋めない、といった選択的処理に使う。

    アルゴリズム:
      1. 境界 (上下左右の各辺) 全周をスキャンし 0 点から flood-fill で外背景を塗る
         (複数文字間の stroke 分断にも対応するため境界全周から起点を取る)。
      2. 反転すると「外背景=0、グリフ=0、穴=255」のマスクが得られる。
      3. max_hole_area が指定されていれば、scipy.ndimage.label で連結成分に分け、
         小さい穴のみ採用する。
      4. 元 mask に加算 → ソリッドシルエット。
    """
    import numpy as np  # 遅延 import (scipy も同様)

    work = mask.copy()
    w, h = work.size
    # 境界 4 辺で 0 のピクセル位置を numpy で一括取得 → flood-fill 起点に。
    # Pillow の getpixel は Python ループだと遅いため。
    sample_step = 2
    arr = np.array(work)
    for x in np.where(arr[0, :] == 0)[0][::sample_step]:
        if work.getpixel((int(x), 0)) == 0:  # flood-fill 後の状態を再確認
            ImageDraw.floodfill(work, (int(x), 0), 255)
    for x in np.where(arr[-1, :] == 0)[0][::sample_step]:
        if work.getpixel((int(x), h - 1)) == 0:
            ImageDraw.floodfill(work, (int(x), h - 1), 255)
    for y in np.where(arr[:, 0] == 0)[0][::sample_step]:
        if work.getpixel((0, int(y))) == 0:
            ImageDraw.floodfill(work, (0, int(y)), 255)
    for y in np.where(arr[:, -1] == 0)[0][::sample_step]:
        if work.getpixel((w - 1, int(y))) == 0:
            ImageDraw.floodfill(work, (w - 1, int(y)), 255)
    holes = ImageChops.invert(work)

    if max_hole_area is None:
        return ImageChops.add(mask, holes)

    # 面積判定: 小さい穴のみ採用
    from scipy.ndimage import label  # transitive 依存 (librosa 経由)

    holes_arr = np.array(holes) > 0
    labels, n_components = label(holes_arr)
    if n_components == 0:
        return mask
    # 各 component の面積
    areas = np.bincount(labels.ravel())
    # label=0 は「穴でない領域」なので除外
    small_label_ids = [i for i in range(1, n_components + 1) if areas[i] <= max_hole_area]
    if not small_label_ids:
        return mask
    small_holes_arr = np.isin(labels, small_label_ids).astype(np.uint8) * 255
    small_holes = Image.fromarray(small_holes_arr, mode="L")
    return ImageChops.add(mask, small_holes)


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
    target_size: tuple[int, int] | None = None,
    offset_y: int = 0,
) -> Path | None:
    """タイトル画像を生成する高レベル関数

    Args:
        target_size: (width, height) ターゲットサイズ。指定時は3段階パイプラインを使用。

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

    # target_size指定時: 3段階パイプライン
    if target_size is not None and client is not None:
        result = _generate_with_pipeline(
            title=title,
            keywords=keywords,
            output_path=output_path,
            target_size=target_size,
            canvas_size=(width, height),
            client=client,
            model=model,
            font_dir=font_dir,
            frame_colors=frame_colors,
            orientation=orientation,
            offset_y=offset_y,
        )
        if result is not None:
            return result
        logger.warning("3段階パイプライン失敗、従来方式にフォールバック")

    # 従来方式（target_size未指定 or パイプライン失敗時）
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

    # コントラスト補正 + 高さ制限
    if frame_colors:
        design = _ensure_contrast(design, frame_colors)
    if target_size:
        design = _ensure_fit_height(design, target_size[1], width, height, font_dir, offset_y)
        # Phase C: target_size 範囲内で縦中央配置
        design = _center_design_in_target(
            design, target_size[1], width, height, font_dir, offset_y
        )

    # 描画
    try:
        result_path, img_w, img_h = render_title_image(
            design=design,
            output_path=output_path,
            width=width,
            height=height,
            font_dir=font_dir,
            offset_y=offset_y,
        )
        logger.info(f"タイトル画像生成完了: {result_path} ({img_w}x{img_h})")
        return result_path
    except Exception as e:
        logger.error(f"タイトル画像描画失敗: {e}")
        return None


def _generate_with_pipeline(
    title: str,
    keywords: list[str],
    output_path: Path,
    target_size: tuple[int, int],
    canvas_size: tuple[int, int],
    client: "openai.OpenAI",
    model: str,
    font_dir: Path | None,
    frame_colors: list[str] | None,
    orientation: str,
    offset_y: int = 0,
    srt_text: str | None = None,
) -> Path | None:
    """3段階パイプラインでタイトル画像を生成する

    Stage 1: AIで複数候補デザイン生成 (Phase A: srt_text あれば SRT ベース)
    Stage 2: レンダリング→ターゲットサイズフィルタ
    Stage 3: Vision AIで最適候補選択
    """
    import shutil

    cache_path = output_path.with_suffix(".title.json")
    target_w, target_h = target_size
    canvas_w, canvas_h = canvas_size
    tmp_dirs: list[Path] = []

    try:
        # Stage 1: AI複数候補生成
        mode = "SRT ベース" if srt_text else "title ベース"
        logger.info(f"Stage 1 ({mode}): {title} — 複数候補生成中...")
        candidates = design_title_layout_candidates(
            client=client,
            title=title,
            keywords=keywords,
            target_size=target_size,
            frame_colors=frame_colors,
            orientation=orientation,
            model=model,
            srt_text=srt_text,
        )
        if not candidates:
            logger.warning("Stage 1: 有効な候補が生成されませんでした")
            return None

        logger.info(f"Stage 1: {len(candidates)}個の有効な候補を取得")

        # コントラスト補正（Stage 2 前に適用）
        if frame_colors:
            candidates = [_ensure_contrast(c, frame_colors) for c in candidates]

        # Stage 2: フィルタリング（レンダリング済み画像 + 全tmpディレクトリ）
        logger.info("Stage 2: フィルタリング中...")
        fitting, tmp_dirs = filter_fitting_candidates(
            candidates=candidates,
            target_width=target_w,
            target_height=target_h,
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            font_dir=font_dir,
            offset_y=offset_y,
        )
        if not fitting:
            logger.warning("Stage 2: フィルタリング結果が空")
            return None

        logger.info(f"Stage 2: {len(fitting)}個の候補がフィルタ通過")

        # Stage 3: Vision AI評価
        if len(fitting) > 1:
            logger.info("Stage 3: Vision AI評価中...")
            candidate_images = [(i, p) for i, (_, p, _, _) in enumerate(fitting)]
            best_idx = evaluate_candidates_with_vision(
                client=client,
                candidate_images=candidate_images,
                title=title,
            )
        else:
            best_idx = 0

        # 最適候補のレンダリング済み画像をコピー（再レンダリング不要）
        best_design, best_rendered_path = fitting[best_idx][0], fitting[best_idx][1]
        _save_design_cache(best_design, cache_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best_rendered_path, output_path)
        logger.info(
            f"パイプライン完了: {output_path.name} ({canvas_w}x{canvas_h}) " f"[候補{best_idx+1}/{len(fitting)}選択]"
        )
        return output_path

    except Exception as e:
        logger.warning(f"パイプライン失敗: {e}")
        return None
    finally:
        # 全一時ディレクトリをクリーンアップ（フィルタ除外分も含む）
        for tmp_dir in tmp_dirs:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


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
- **タイトル全文が {MAX_LINE_CHARS} 文字を超える場合は必ず複数行 (lines を 2 個以上) に分割すること**。1 行のままだと font_size が縮小されて非常に見にくくなる

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
3. 最も伝えたい語句を非常に大きく（font_size: 160-200）、補足・接続詞・助詞も大きめに（110-140）
4. 配色は背景フレームの色に合わせて選ぶ。背景色と同系色のテキストは避ける
5. 外アウトラインは常に白(#FFFFFF)、outer_outline_width=10
6. テキスト色が暗い→inner_outline_width=0。明るい/カラー/グラデーション→inner_outline_color="#000000", inner_outline_width=6
7. 強調セグメントにgradientを使う（2色の縦グラデーション）
8. weightは全セグメント Eb 固定

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
    prompt = prompt.replace("{MAX_LINE_CHARS}", str(_TITLE_FORCE_BREAK_THRESHOLD))
    prompt = prompt.replace("{MAX_LINE_CHARS_DOUBLE}", str(_TITLE_FORCE_BREAK_THRESHOLD * 2))

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
            design = _snap_segments_to_word_boundaries(design)
            # バリデーション
            reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
            if reconstructed != title:
                logger.warning(f"AIがタイトル文字を変更 (#{i+1}): {title!r} -> {reconstructed!r}")
                results.append(None)
            else:
                # Phase B: 1 line で閾値超なら強制分割
                design = _enforce_line_break(design)
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
    target_size: tuple[int, int] | None = None,
    offset_y: int = 0,
    srt_paths: "list[Path | None] | None" = None,
) -> dict[int, Path]:
    """複数候補のタイトル画像をバッチ生成する。

    Args:
        suggestions: titleとkeywords属性を持つ候補のリスト
        output_dir: 出力ディレクトリ（title_images/）
        sanitize_fn: ファイル名サニタイズ関数（省略時は簡易サニタイズ）
        srt_paths: 各 suggestion に対応する SRT ファイルパスのリスト
            (Phase A: 指定時は AI が SRT を読んでタイトルを自由生成)。
            None or 全要素 None なら従来通り title/keywords ベース。
            ファイル名はサニタイズ済みの suggestion.title で固定 (= ファイル名規則維持)。

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
        cache_path = output_dir / f"{i+1:02d}_{sanitized}.title.json"
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                designs[i] = _parse_design_json(raw)
                logger.info(f"キャッシュ読み込み: {cache_path.name}")
            except Exception:
                uncached_indices.append(i)
        else:
            uncached_indices.append(i)

    # target_size指定時: 各タイトルに3段階パイプラインを個別適用（並列実行）
    if target_size is not None and client is not None:
        from concurrent.futures import ThreadPoolExecutor

        result_paths: dict[int, Path] = {}

        def _generate_one(args: tuple[int, object]) -> tuple[int, Path | None]:
            i, s = args
            sanitized = sanitize_fn(s.title)
            output_path = output_dir / f"{i+1:02d}_{sanitized}.png"

            if designs[i] is not None:
                # キャッシュありの場合: コントラスト補正 + 高さ制限を適用して描画
                cached_design = designs[i]
                if frame_colors:
                    cached_design = _ensure_contrast(cached_design, frame_colors)
                cached_design = _ensure_fit_height(
                    cached_design,
                    target_size[1],
                    width,
                    height,
                    font_dir,
                    offset_y,
                )
                try:
                    result_path, img_w, img_h = render_title_image(
                        design=cached_design,
                        output_path=output_path,
                        width=width,
                        height=height,
                        font_dir=font_dir,
                        offset_y=offset_y,
                    )
                    logger.info(f"タイトル画像(キャッシュ): {output_path.name} ({img_w}x{img_h})")
                    return (i + 1, result_path)
                except Exception as e:
                    logger.error(f"タイトル画像描画失敗 (#{i+1}): {e}")
                    return (i + 1, None)

            # Phase A: SRT パスがあれば中身を読んで AI に渡す
            srt_text: str | None = None
            if srt_paths is not None and i < len(srt_paths) and srt_paths[i] is not None:
                try:
                    srt_text = srt_paths[i].read_text(encoding="utf-8")
                except OSError as e:
                    logger.warning(f"SRT 読み込み失敗 (#{i+1}): {e}")

            # パイプラインで生成
            try:
                result = _generate_with_pipeline(
                    title=s.title,
                    keywords=getattr(s, "keywords", []),
                    output_path=output_path,
                    target_size=target_size,
                    canvas_size=(width, height),
                    client=client,
                    model=model,
                    font_dir=font_dir,
                    frame_colors=frame_colors,
                    orientation=orientation,
                    offset_y=offset_y,
                    srt_text=srt_text,
                )
                if result:
                    return (i + 1, result)
                else:
                    # パイプライン失敗時はフォールバック
                    fb_design = create_fallback_design(s.title)
                    if frame_colors:
                        fb_design = _ensure_contrast(fb_design, frame_colors)
                    fb_design = _ensure_fit_height(
                        fb_design,
                        target_size[1],
                        width,
                        height,
                        font_dir,
                        offset_y,
                    )
                    result_path, img_w, img_h = render_title_image(
                        design=fb_design,
                        output_path=output_path,
                        width=width,
                        height=height,
                        font_dir=font_dir,
                        offset_y=offset_y,
                    )
                    return (i + 1, result_path)
            except Exception as e:
                logger.error(f"タイトル画像生成失敗 (#{i+1}): {e}")
                return (i + 1, None)

        with ThreadPoolExecutor(max_workers=min(len(suggestions), 5)) as executor:
            for key, path in executor.map(_generate_one, enumerate(suggestions)):
                if path:
                    result_paths[key] = path

        return result_paths

    # 従来方式: バッチAI呼び出し（未キャッシュ分をまとめて1回）
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

    # フォールバック + コントラスト補正 + 描画
    result_paths: dict[int, Path] = {}
    for i, s in enumerate(suggestions):
        if designs[i] is None:
            designs[i] = create_fallback_design(s.title)

        # コントラスト補正
        if frame_colors:
            designs[i] = _ensure_contrast(designs[i], frame_colors)

        sanitized = sanitize_fn(s.title)
        output_path = output_dir / f"{i+1:02d}_{sanitized}.png"
        try:
            result_path, img_w, img_h = render_title_image(
                design=designs[i],
                output_path=output_path,
                width=width,
                height=height,
                font_dir=font_dir,
                offset_y=offset_y,
            )
            result_paths[i + 1] = result_path
            logger.info(f"タイトル画像: {output_path.name} ({img_w}x{img_h})")
        except Exception as e:
            logger.error(f"タイトル画像描画失敗 (#{i+1}): {e}")

    return result_paths
