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
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageChops = ImageDraw = ImageFont = None  # type: ignore[assignment,misc]

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

_OUTLINE_VS_BG_THRESHOLD = 3.0
_TEXT_VS_OUTLINE_THRESHOLD = 2.0


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.0 相対輝度を計算 (0.0=黒, 1.0=白)"""
    r, g, b = _hex_to_rgb(hex_color)

    def srgb(c: int) -> float:
        c_norm = c / 255.0
        return c_norm / 12.92 if c_norm <= 0.04045 else ((c_norm + 0.055) / 1.055) ** 2.4

    return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)


def _contrast_ratio(color1: str, color2: str) -> float:
    """WCAG 2.0 コントラスト比を計算 (1.0〜21.0)"""
    l1 = _relative_luminance(color1)
    l2 = _relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(design: TitleImageDesign, frame_colors: list[str]) -> TitleImageDesign:
    """テキスト色と背景色のコントラストが低い場合に自動補正する"""
    import copy

    if not frame_colors:
        return design

    bg_luminance = _relative_luminance(frame_colors[0])
    bg_is_light = bg_luminance > 0.4

    design = copy.deepcopy(design)

    for line in design.lines:
        outline_color = line.outer_outline_color
        min_contrast_vs_bg = min(_contrast_ratio(outline_color, fc) for fc in frame_colors)

        if min_contrast_vs_bg < _OUTLINE_VS_BG_THRESHOLD:
            new_outline = "#000000" if bg_is_light else "#FFFFFF"
            logger.info(
                "コントラスト補正: アウトライン %s → %s (比率%.2f < %.1f)",
                outline_color,
                new_outline,
                min_contrast_vs_bg,
                _OUTLINE_VS_BG_THRESHOLD,
            )
            line.outer_outline_color = new_outline

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
    design = _snap_segments_to_word_boundaries(design)

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
3. 最も伝えたい語句を非常に大きく（font_size: 160-200）、補足・接続詞・助詞も大きめに（110-140）
4. 背景フレームの色に映える配色を選ぶ
5. 白文字や明るい色の文字は黒の外アウトラインのみ（inner_outline_width=0）でシンプルに
6. グラデーションセグメントのみ二重アウトライン（外側=暗色、内側=明色）で装飾する
7. 強調セグメントにgradientを使う（2色の縦グラデーション）
8. weightは強調語=Eb、補足=Bd、句読点=Rg

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
) -> list[TitleImageDesign]:
    """AIに複数のデザイン候補を1回のAPI呼び出しで生成させる (Stage 1)"""
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "title_image_candidates.md"
    if prompt_path.exists():
        prompt_template = prompt_path.read_text(encoding="utf-8")
    else:
        logger.warning("title_image_candidates.md が見つかりません。デフォルトプロンプトで1候補生成に切り替えます。")
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
            # バリデーション: 文字一致チェック
            reconstructed = "".join(seg.text for line in design.lines for seg in line.segments)
            if reconstructed != title:
                logger.warning(
                    f"候補#{i+1}: AIがタイトル文字を変更 (期待: {title!r}, 実際: {reconstructed!r})。スキップ。"
                )
                continue
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
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin_x = 40  # 左右マージン
    usable_width = width - margin_x * 2
    current_y = design.padding_top + offset_y  # デザインのpadding_top + ユーザーオフセット

    for line in design.lines:
        # 各セグメントのフォントをロード
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
                if font_path:
                    fonts[i] = ImageFont.truetype(font_path, new_size)
                else:
                    fonts[i] = ImageFont.load_default(size=new_size)
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
) -> Path | None:
    """3段階パイプラインでタイトル画像を生成する

    Stage 1: AIで複数候補デザイン生成
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
        logger.info(f"Stage 1: {title} — 複数候補生成中...")
        candidates = design_title_layout_candidates(
            client=client,
            title=title,
            keywords=keywords,
            target_size=target_size,
            frame_colors=frame_colors,
            orientation=orientation,
            model=model,
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
    target_size: tuple[int, int] | None = None,
    offset_y: int = 0,
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

    # target_size指定時: 各タイトルに3段階パイプラインを個別適用
    if target_size is not None and client is not None:
        result_paths: dict[int, Path] = {}
        for i, s in enumerate(suggestions):
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
                    result_paths[i + 1] = result_path
                    logger.info(f"タイトル画像(キャッシュ): {output_path.name} ({img_w}x{img_h})")
                except Exception as e:
                    logger.error(f"タイトル画像描画失敗 (#{i+1}): {e}")
                continue

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
                )
                if result:
                    result_paths[i + 1] = result
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
                    result_paths[i + 1] = result_path
            except Exception as e:
                logger.error(f"タイトル画像生成失敗 (#{i+1}): {e}")
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
