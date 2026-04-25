"""P2: 動画を sample-rate でフレーム抽出 → 各フレームで検出 → bbox 時系列を JSON 出力.

検出可視化用 debug 動画もオプションで出力する.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
from tqdm import tqdm

from detector import TextDetector


def sample_video_frames(video_path: Path, sample_fps: float):
    """動画を sample_fps でサンプリングし (timestamp, frame) を yield."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {video_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / src_fps

    if sample_fps >= src_fps:
        step_frames = 1
    else:
        step_frames = max(1, int(round(src_fps / sample_fps)))

    frame_idx = 0
    while frame_idx < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = frame_idx / src_fps
        yield timestamp, frame, duration
        frame_idx += step_frames

    cap.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="P2: 動画 bbox 時系列生成")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--debug-video", type=Path, help="bbox 可視化動画の出力先 (任意)")
    parser.add_argument("--sample-rate", type=float, default=3.0, help="検出 fps")
    parser.add_argument("--languages", nargs="+", default=["ja", "en"])
    args = parser.parse_args()

    if not args.input.exists():
        print(f"入力動画が見つかりません: {args.input}", file=sys.stderr)
        return 1

    print(f"[P2] 検出器初期化 (languages={args.languages})...")
    t0 = time.time()
    detector = TextDetector(languages=args.languages)
    print(f"[P2] 初期化: {time.time() - t0:.2f}s")

    cap = cv2.VideoCapture(str(args.input))
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / src_fps
    cap.release()

    print(f"[P2] 動画: {width}x{height} @ {src_fps:.2f}fps, {duration:.1f}s")
    print(f"[P2] サンプリング: {args.sample_rate}fps → 約 {int(duration * args.sample_rate)} フレーム検出予定")

    debug_writer = None
    if args.debug_video:
        args.debug_video.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        debug_writer = cv2.VideoWriter(str(args.debug_video), fourcc, args.sample_rate, (width, height))

    detections: list[dict] = []
    t_detect_total = 0.0

    expected = max(1, int(round(duration * args.sample_rate)))
    pbar = tqdm(total=expected, desc="detect")

    for timestamp, frame, _ in sample_video_frames(args.input, args.sample_rate):
        t1 = time.time()
        boxes = detector.detect(frame)
        t_detect_total += time.time() - t1

        detections.append(
            {
                "timestamp": round(timestamp, 4),
                "boxes": [b.as_list() for b in boxes],
            }
        )

        if debug_writer is not None:
            vis = frame.copy()
            for b in boxes:
                cv2.rectangle(vis, (b.x1, b.y1), (b.x2, b.y2), (0, 0, 255), 2)
            cv2.putText(
                vis,
                f"t={timestamp:.2f}s  n_boxes={len(boxes)}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            debug_writer.write(vis)

        pbar.update(1)

    pbar.close()

    if debug_writer is not None:
        debug_writer.release()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w") as f:
        json.dump(
            {
                "video": str(args.input),
                "width": width,
                "height": height,
                "src_fps": src_fps,
                "duration": duration,
                "sample_rate": args.sample_rate,
                "detections": detections,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    n_frames = len(detections)
    n_boxes_total = sum(len(d["boxes"]) for d in detections)
    print(f"[P2] 検出フレーム: {n_frames}")
    print(f"[P2] 合計 bbox 数: {n_boxes_total}")
    print(f"[P2] 平均 bbox/frame: {n_boxes_total / n_frames:.1f}")
    print(f"[P2] 検出時間合計: {t_detect_total:.1f}s ({t_detect_total / n_frames:.2f}s/frame)")
    print(f"[P2] JSON: {args.output_json}")
    if args.debug_video:
        print(f"[P2] Debug 動画: {args.debug_video}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
