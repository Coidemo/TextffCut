"""P1: 静止画 1 枚で EasyOCR (CRAFT) のテキスト検出動作を確認するスクリプト.

動画から指定タイムスタンプのフレームを抽出し、テキスト bbox を検出して
赤枠で可視化した画像を保存する.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np


def extract_frame(video_path: Path, timestamp: float) -> np.ndarray:
    """指定タイムスタンプのフレームを抽出して BGR np.ndarray で返す."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    target_frame = int(round(timestamp * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"フレーム抽出失敗: timestamp={timestamp}s")
    return frame


def detect_text_boxes(image: np.ndarray, languages: list[str]) -> list[list[int]]:
    """EasyOCR の detect-only モードで text bbox を取得.

    Returns:
        [[x1, y1, x2, y2], ...] の bbox リスト.
    """
    import easyocr

    print(f"[P1] EasyOCR Reader 初期化中 (languages={languages})...")
    t0 = time.time()
    reader = easyocr.Reader(languages, gpu=False, verbose=False)
    print(f"[P1] Reader 初期化: {time.time() - t0:.2f}s")

    print("[P1] 検出実行中...")
    t1 = time.time()
    horizontal_list, free_list = reader.detect(image)
    print(f"[P1] 検出: {time.time() - t1:.2f}s")

    boxes: list[list[int]] = []
    for box in horizontal_list[0]:
        x_min, x_max, y_min, y_max = box
        boxes.append([int(x_min), int(y_min), int(x_max), int(y_max)])

    for poly in free_list[0]:
        xs = [int(p[0]) for p in poly]
        ys = [int(p[1]) for p in poly]
        boxes.append([min(xs), min(ys), max(xs), max(ys)])

    return boxes


def draw_boxes(image: np.ndarray, boxes: list[list[int]]) -> np.ndarray:
    """bbox を画像に描画."""
    result = image.copy()
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(result, (x1, y1), (x2, y2), (0, 0, 255), 2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="P1: 単一フレームで text 検出動作確認")
    parser.add_argument("--input", required=True, type=Path, help="入力動画 or 画像")
    parser.add_argument("--timestamp", type=float, default=5.0, help="動画の場合の抽出タイムスタンプ (秒)")
    parser.add_argument("--output", required=True, type=Path, help="可視化画像の出力先")
    parser.add_argument("--languages", nargs="+", default=["ja", "en"], help="EasyOCR 言語")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        return 1

    if args.input.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"}:
        print(f"[P1] 動画 {args.input.name} の {args.timestamp}s フレームを抽出")
        image = extract_frame(args.input, args.timestamp)
    else:
        image = cv2.imread(str(args.input))
        if image is None:
            print(f"画像を読み込めません: {args.input}", file=sys.stderr)
            return 1

    h, w = image.shape[:2]
    print(f"[P1] 画像サイズ: {w}x{h}")

    boxes = detect_text_boxes(image, args.languages)
    print(f"[P1] 検出 bbox 数: {len(boxes)}")
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        print(f"  [{i}] ({x1},{y1})-({x2},{y2})  size={x2-x1}x{y2-y1}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    visualized = draw_boxes(image, boxes)
    cv2.imwrite(str(args.output), visualized)
    print(f"[P1] 可視化画像を保存: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
