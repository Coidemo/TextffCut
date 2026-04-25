"""共通: EasyOCR ベースのテキスト bbox 検出.

P1-P4 で共通利用される検出ロジック.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Box:
    """検出された text bbox."""

    x1: int
    y1: int
    x2: int
    y2: int

    def as_xywh(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]

    def expand(self, padding: int, max_w: int, max_h: int) -> Box:
        return Box(
            max(0, self.x1 - padding),
            max(0, self.y1 - padding),
            min(max_w, self.x2 + padding),
            min(max_h, self.y2 + padding),
        )

    def iou(self, other: Box) -> float:
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        a1 = (self.x2 - self.x1) * (self.y2 - self.y1)
        a2 = (other.x2 - other.x1) * (other.y2 - other.y1)
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0.0


class OcrmacDetector:
    """Apple Vision Framework (ocrmac) ベースのテキスト検出器.

    Apple Silicon の Neural Engine を活用するため EasyOCR より大幅に高速.
    Vision の VNRecognizeTextRequest を使い、認識結果は捨てて bbox のみ取り出す.
    """

    def __init__(
        self,
        languages: list[str] | None = None,
        detect_scale: float = 1.0,
        recognition_level: str = "accurate",
    ) -> None:
        from ocrmac import ocrmac as ocrmac_lib  # noqa: F401 (validate import)

        # Apple Vision の言語コードは "ja-JP" / "en-US" 形式. 短縮形なら補完.
        lang_map = {"ja": "ja-JP", "en": "en-US", "zh": "zh-Hans", "ko": "ko-KR"}
        normalized = [lang_map.get(lang, lang) for lang in (languages or ["ja", "en"])]
        self.languages = normalized
        self.detect_scale = detect_scale
        # 日本語は accurate モード (revision 3+) でのみサポート, fast はラテン系のみ
        self.recognition_level = recognition_level

    def detect(self, image: np.ndarray) -> list[Box]:
        from PIL import Image
        from ocrmac import ocrmac as ocrmac_lib

        if self.detect_scale != 1.0:
            small = cv2.resize(
                image, None, fx=self.detect_scale, fy=self.detect_scale, interpolation=cv2.INTER_AREA
            )
        else:
            small = image
        small_h, small_w = small.shape[:2]
        inv = 1.0 / self.detect_scale if self.detect_scale != 1.0 else 1.0

        # OpenCV BGR → PIL RGB
        pil_img = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))

        ocr = ocrmac_lib.OCR(
            pil_img,
            language_preference=self.languages,
            recognition_level=self.recognition_level,
        )
        annotations = ocr.recognize()

        boxes: list[Box] = []
        for ann in annotations:
            # Apple Vision は bottom-left origin の正規化座標 (x, y, w, h)
            _text, _conf, bbox = ann
            x_n, y_n_bl, w_n, h_n = bbox
            # bottom-left origin → top-left origin に変換
            x1 = int(x_n * small_w * inv)
            x2 = int((x_n + w_n) * small_w * inv)
            y1 = int((1.0 - y_n_bl - h_n) * small_h * inv)
            y2 = int((1.0 - y_n_bl) * small_h * inv)
            boxes.append(Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))

        return boxes


class TextDetector:
    """EasyOCR の detect-only モードでテキスト bbox を抽出."""

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool = False,
        detect_scale: float = 1.0,
    ) -> None:
        import easyocr

        self.languages = languages or ["ja", "en"]
        self.reader = easyocr.Reader(self.languages, gpu=gpu, verbose=False)
        self.detect_scale = detect_scale

    def detect(self, image: np.ndarray) -> list[Box]:
        if self.detect_scale != 1.0:
            small = cv2.resize(
                image,
                None,
                fx=self.detect_scale,
                fy=self.detect_scale,
                interpolation=cv2.INTER_AREA,
            )
            horizontal_list, free_list = self.reader.detect(small)
            inv = 1.0 / self.detect_scale
        else:
            horizontal_list, free_list = self.reader.detect(image)
            inv = 1.0

        boxes: list[Box] = []
        for box in horizontal_list[0]:
            x_min, x_max, y_min, y_max = box
            boxes.append(
                Box(
                    int(x_min * inv),
                    int(y_min * inv),
                    int(x_max * inv),
                    int(y_max * inv),
                )
            )

        for poly in free_list[0]:
            xs = [int(p[0] * inv) for p in poly]
            ys = [int(p[1] * inv) for p in poly]
            boxes.append(Box(min(xs), min(ys), max(xs), max(ys)))

        return boxes


def sample_edge_color(
    frame: np.ndarray, box: Box, border_width: int = 8
) -> tuple[int, int, int]:
    """bbox の縁周辺 (外側) の median 色を取得 (BGR).

    bbox の上下左右にある border_width 幅の帯状領域からピクセルを集め、
    median を取ることで text の影響を受けない「周囲の色」を得る.
    """
    h, w = frame.shape[:2]
    samples: list[np.ndarray] = []

    # 上端 strip (bbox の上に位置する)
    if box.y1 - border_width >= 0:
        samples.append(frame[max(0, box.y1 - border_width) : box.y1, box.x1 : box.x2])
    # 下端 strip
    if box.y2 + border_width <= h:
        samples.append(frame[box.y2 : min(h, box.y2 + border_width), box.x1 : box.x2])
    # 左端 strip
    if box.x1 - border_width >= 0:
        samples.append(frame[box.y1 : box.y2, max(0, box.x1 - border_width) : box.x1])
    # 右端 strip
    if box.x2 + border_width <= w:
        samples.append(frame[box.y1 : box.y2, box.x2 : min(w, box.x2 + border_width)])

    if not samples:
        return (128, 128, 128)

    all_pixels = np.concatenate([s.reshape(-1, 3) for s in samples if s.size > 0], axis=0)
    if all_pixels.size == 0:
        return (128, 128, 128)
    median = np.median(all_pixels, axis=0)
    return (int(median[0]), int(median[1]), int(median[2]))


def merge_boxes(boxes: list[Box], gap_x: int = 40, gap_y: int = 40) -> list[Box]:
    """近接した bbox を 1 つの矩形に結合する.

    各 bbox を gap_x/gap_y だけ膨張させて重なりを判定し、重なるものは
    union を取って 1 つにまとめる. 反復的に何も merge できなくなるまで実行.
    """
    if not boxes:
        return []

    current = [Box(b.x1, b.y1, b.x2, b.y2) for b in boxes]

    while True:
        merged_one = False
        n = len(current)
        for i in range(n):
            if merged_one:
                break
            for j in range(i + 1, n):
                a = current[i]
                b = current[j]
                # 拡張後に重なるかチェック
                ax1, ay1 = a.x1 - gap_x, a.y1 - gap_y
                ax2, ay2 = a.x2 + gap_x, a.y2 + gap_y
                if ax2 < b.x1 or b.x2 < ax1 or ay2 < b.y1 or b.y2 < ay1:
                    continue
                union = Box(
                    min(a.x1, b.x1),
                    min(a.y1, b.y1),
                    max(a.x2, b.x2),
                    max(a.y2, b.y2),
                )
                current = [c for k, c in enumerate(current) if k != i and k != j]
                current.append(union)
                merged_one = True
                break
        if not merged_one:
            break

    return current
