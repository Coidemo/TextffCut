"""動画内テキストを自動検出してぼかし、(オプションで) 速度変更も適用して 1 ファイル出力.

エンドツーエンドの PoC スクリプト.

処理パイプライン:
  1. (--speed != 1.0 の場合) ffmpeg で先に速度変更 → sped_up.mp4 (音声含む)
  2. (--scene-detect の場合) ffmpeg scene filter で変化点タイムスタンプ取得
  3. 各サンプルタイムスタンプでテキスト bbox 検出 + 近接 bbox 結合
  4. IoU マッチングで track 化
  5. 出力 fps 全フレームに対して active な bbox を収集 → ぼかし合成 (映像のみ)
  6. ffmpeg で sped_up.mp4 の音声を blurred_video に mux → 最終出力
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from detector import Box, OcrmacDetector, TextDetector, merge_boxes
from ffmpeg_blur import (
    apply_ffmpeg_blur,
    apply_ffmpeg_blur_chunked,
    build_blur_filter_complex,
    build_mask_blur_filter_complex,
    build_solid_fill_filter_complex,
    generate_mask_video,
    sample_track_fill_colors,
)
from full_chunk_worker import process_full_chunk
from tracker import build_tracks, collect_active_boxes, filter_short_tracks


def apply_pre_speed(input_path: Path, output_path: Path, speed: float) -> None:
    """先に速度変更を適用した中間ファイルを作成 (音声含む)."""
    if speed < 0.5 or speed > 2.0:
        raise ValueError(f"--speed は 0.5..2.0 の範囲のみ対応 (PoC): got {speed}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    setpts = f"setpts=PTS/{speed}"
    atempo = f"atempo={speed}"
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-filter_complex", f"[0:v]{setpts}[v];[0:a]{atempo}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-loglevel", "error",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def detect_scene_changes(video_path: Path, threshold: float = 0.1) -> list[float]:
    """ffmpeg scene filter でシーン変化のタイムスタンプ (秒) を取得."""
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-an", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pattern = re.compile(r"pts_time:([\d.]+)")
    return [float(m.group(1)) for m in pattern.finditer(result.stderr)]


def build_sample_timestamps(
    duration: float,
    scene_changes: list[float] | None,
    base_interval: float,
    edge_offset: float = 0.1,
) -> list[float]:
    """検出を行うタイムスタンプのリストを構築.

    - シーン変化が指定されていれば各変化 + edge_offset を含める
    - base_interval ごとの定期サンプリングをフォールバックとして含める
    - 動画末尾近くも必ず 1 回検出する
    """
    timestamps: set[float] = {edge_offset}
    if scene_changes:
        for sc in scene_changes:
            t = min(duration - edge_offset, max(0.0, sc + edge_offset))
            timestamps.add(round(t, 4))
    t = base_interval
    while t < duration:
        timestamps.add(round(t, 4))
        t += base_interval
    timestamps.add(round(max(0.0, duration - edge_offset), 4))
    return sorted(timestamps)


def detect_at_timestamps(
    video_path: Path,
    detector: TextDetector,
    timestamps: list[float],
    merge_gap_x: int,
    merge_gap_y: int,
    skip_threshold: float = 0.0,
    max_skip_streak: int = 10,
    diff_resize: tuple[int, int] = (320, 180),
) -> tuple[list[tuple[float, list[Box]]], dict]:
    """指定タイムスタンプのフレームだけ検出して bbox 時系列を返す.

    skip_threshold > 0 のとき、前回検出フレームとの差分が閾値以下なら検出をスキップして
    前回の bbox を流用 (案 C1: フレーム差分スキップ).
    max_skip_streak で連続スキップ上限を設けて検出ドリフトを防ぐ.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / src_fps

    detections: list[tuple[float, list[Box]]] = []
    last_detected_small: np.ndarray | None = None
    last_boxes: list[Box] | None = None
    skip_streak = 0
    n_skipped = 0
    n_detected = 0
    pbar = tqdm(total=len(timestamps), desc="detect", leave=False)

    for t in timestamps:
        if t < 0 or t >= duration:
            pbar.update(1)
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * src_fps)))
        ret, frame = cap.read()
        if not ret:
            pbar.update(1)
            continue

        # 案 C1: 前回検出フレームとの差分でスキップ判定
        if (
            skip_threshold > 0.0
            and last_detected_small is not None
            and last_boxes is not None
            and skip_streak < max_skip_streak
        ):
            current_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            diff = float(cv2.absdiff(current_small, last_detected_small).mean()) / 255.0
            if diff < skip_threshold:
                detections.append((t, last_boxes))
                skip_streak += 1
                n_skipped += 1
                pbar.update(1)
                continue

        raw_boxes = detector.detect(frame)
        merged = merge_boxes(raw_boxes, gap_x=merge_gap_x, gap_y=merge_gap_y)
        detections.append((t, merged))
        n_detected += 1
        if skip_threshold > 0.0:
            last_detected_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            last_boxes = merged
            skip_streak = 0
        pbar.update(1)

    pbar.close()
    cap.release()

    info = {
        "src_fps": src_fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "duration": duration,
        "n_detected": n_detected,
        "n_skipped": n_skipped,
    }
    return detections, info


def _apply_gaussian(roi: np.ndarray, kernel: int) -> np.ndarray:
    k = kernel | 1
    local_k = min(k, max(3, (min(roi.shape[0], roi.shape[1]) // 2) | 1))
    if local_k < 3:
        local_k = 3
    return cv2.GaussianBlur(roi, (local_k, local_k), 0)


def _apply_mosaic(roi: np.ndarray, scale: int) -> np.ndarray:
    h, w = roi.shape[:2]
    sw = max(1, w // scale)
    sh = max(1, h // scale)
    small = cv2.resize(roi, (sw, sh), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def apply_blur(
    image: np.ndarray,
    boxes: list[Box],
    method: str,
    blur_strength: int,
    mosaic_scale: int,
    padding: int,
) -> np.ndarray:
    if not boxes:
        return image
    h, w = image.shape[:2]
    result = image.copy()
    for box in boxes:
        expanded = box.expand(padding, w, h)
        x1, y1, x2, y2 = expanded.x1, expanded.y1, expanded.x2, expanded.y2
        if x2 <= x1 or y2 <= y1:
            continue
        roi = result[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        if method == "mosaic":
            blurred_roi = _apply_mosaic(roi, mosaic_scale)
        else:
            blurred_roi = _apply_gaussian(roi, blur_strength)
        result[y1:y2, x1:x2] = blurred_roi
    return result


def render_blurred_video(
    input_path: Path,
    output_path: Path,
    tracks,
    method: str,
    blur_strength: int,
    mosaic_scale: int,
    padding: int,
    persistence: float,
    info: dict,
    preview: bool = False,
) -> None:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {input_path}")
    src_fps = info["src_fps"]
    width = info["width"]
    height = info["height"]
    total_frames = info["total_frames"]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), fourcc, src_fps, (width, height))

    pbar = tqdm(total=total_frames, desc="blur ", leave=False)
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = frame_idx / src_fps
        active_boxes = collect_active_boxes(tracks, timestamp, persistence=persistence)
        blurred = apply_blur(
            frame, active_boxes,
            method=method, blur_strength=blur_strength,
            mosaic_scale=mosaic_scale, padding=padding,
        )
        if preview:
            for b in active_boxes:
                exp = b.expand(padding, width, height)
                cv2.rectangle(blurred, (exp.x1, exp.y1), (exp.x2, exp.y2), (0, 255, 0), 2)
            cv2.putText(
                blurred, f"t={timestamp:.2f}s n_box={len(active_boxes)}",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA,
            )
        writer.write(blurred)
        frame_idx += 1
        pbar.update(1)

    pbar.close()
    cap.release()
    writer.release()


def mux_audio_from(blurred_video: Path, audio_source: Path, output: Path) -> None:
    """blurred_video (映像のみ) と audio_source の音声を mux して output へ."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(blurred_video),
        "-i", str(audio_source),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-loglevel", "error",
        str(output),
    ]
    subprocess.run(cmd, check=True)


def _run_full_chunks(args, overall_t0: float) -> int:
    """フルチャンク並列実行: 各チャンクが独立に scene_detect + detect + ffmpeg を走らせる."""
    import concurrent.futures as futures

    # 動画長取得
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        print(f"動画を開けません: {args.input}", file=sys.stderr)
        return 1
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / src_fps
    cap.release()
    print(f"[blur] 動画長: {duration:.1f}s, full-chunks={args.full_chunks}")

    chunk_dur = duration / args.full_chunks
    chunk_args_list = []
    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmpdir = Path(tmpdir_s)
        chunk_paths = []
        for i in range(args.full_chunks):
            abs_start = i * chunk_dur
            this_dur = (duration - abs_start) if i == args.full_chunks - 1 else chunk_dur
            chunk_path = tmpdir / f"chunk_{i:04d}.mp4"
            chunk_paths.append(chunk_path)
            chunk_args_list.append({
                "chunk_idx": i,
                "input_video": str(args.input),
                "output_path": str(chunk_path),
                "abs_start": abs_start,
                "abs_dur": this_dur,
                "scene_threshold": args.scene_threshold,
                "scene_detect": args.scene_detect,
                "base_interval": args.base_interval,
                "detector_backend": args.detector,
                "languages": args.languages,
                "detect_scale": args.detect_scale,
                "merge_gap_x": args.merge_gap_x,
                "merge_gap_y": args.merge_gap_y,
                "iou_threshold": args.iou_threshold,
                "max_gap_seconds": args.max_gap_seconds,
                "persistence": args.persistence,
                "min_track_duration": args.min_track_duration,
                "padding": args.padding,
                "skip_threshold": args.skip_threshold,
                "max_skip_streak": args.max_skip_streak,
                "speed": args.speed,
                "encoder": args.encoder,
                "crf": 20,
                "preset": "medium",
                "bitrate": args.bitrate,
            })

        print(f"[blur] {args.full_chunks} チャンクで並列処理開始...")
        t0 = time.time()
        with futures.ProcessPoolExecutor(max_workers=args.full_chunks) as pool:
            done_count = 0
            for fut in futures.as_completed(
                [pool.submit(process_full_chunk, ca) for ca in chunk_args_list]
            ):
                stats = fut.result()
                done_count += 1
                print(
                    f"[blur]   chunk {done_count}/{args.full_chunks} 完了 "
                    f"(detect={stats['n_detected']} skip={stats['n_skipped']} "
                    f"tracks={stats['n_tracks']} scene={stats['n_scene_changes']})"
                )
        print(f"[blur] 並列処理完了: {time.time() - t0:.1f}s")

        # concat
        print(f"[blur] チャンク結合 → {args.output}")
        t0 = time.time()
        list_file = tmpdir / "concat_list.txt"
        with list_file.open("w") as f:
            for cp in chunk_paths:
                f.write(f"file '{cp}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            "-loglevel", "error",
            str(args.output),
        ]
        subprocess.run(cmd, check=True)
        print(f"[blur] concat: {time.time() - t0:.1f}s")

    print(f"[blur] === 完了 (合計 {time.time() - overall_t0:.1f}s) ===")
    print(f"[blur] 出力: {args.output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="動画内テキストの自動検出 + ぼかし + 速度変更")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--speed", type=float, default=1.0, help="再生速度倍率 (0.5..2.0)")
    parser.add_argument(
        "--detector", choices=["easyocr", "ocrmac"], default="ocrmac",
        help="検出器バックエンド (ocrmac=Apple Vision・高速, easyocr=従来)",
    )
    parser.add_argument("--detect-scale", type=float, default=0.5, help="検出時のフレーム縮小率")

    # サンプリング戦略
    parser.add_argument(
        "--scene-detect", action=argparse.BooleanOptionalAction, default=True,
        help="シーン変化検出で検出フレームを削減 (--no-scene-detect で無効化)",
    )
    parser.add_argument("--scene-threshold", type=float, default=0.1, help="シーン変化判定閾値 (0..1)")
    parser.add_argument(
        "--base-interval", type=float, default=10.0,
        help="シーン変化以外のフォールバック検出間隔 (秒). scene-detect 無効時はこれが固定間隔",
    )

    # フレーム差分スキップ (案 C1)
    parser.add_argument(
        "--skip-threshold", type=float, default=0.02,
        help="前回検出フレームとの差分がこれ以下なら検出スキップ. 0=スキップ無効",
    )
    parser.add_argument(
        "--max-skip-streak", type=int, default=15,
        help="連続スキップ上限. 検出ドリフト防止",
    )

    # ぼかし
    parser.add_argument(
        "--blur-engine", choices=["opencv", "ffmpeg", "mask", "fill"], default="mask",
        help="エンジン (fill=塗りつぶし最速, mask=高速 blur, ffmpeg=overlay 多層, opencv=旧版)",
    )
    parser.add_argument(
        "--encoder", choices=["libx264", "h264_videotoolbox"], default="h264_videotoolbox",
        help="動画エンコーダー (h264_videotoolbox=Apple Silicon ハードウェア, 5x 高速)",
    )
    parser.add_argument("--bitrate", default="8M", help="videotoolbox 用ビットレート")
    parser.add_argument("--mask-feather", type=float, default=20.0, help="mask 方式: マスク境界の gblur sigma")
    parser.add_argument(
        "--chunks", type=int, default=1,
        help="fill engine: ffmpeg 並列チャンク数 (1=並列なし, 推奨 4-8)",
    )
    parser.add_argument(
        "--full-chunks", type=int, default=1,
        help="フルチャンク並列: 検出+ぼかし全段階を N 並列 (1=無効, 推奨 4)",
    )
    parser.add_argument("--blur-method", choices=["mosaic", "gaussian"], default="gaussian", help="opencv エンジンのみ")
    parser.add_argument("--blur-strength", type=int, default=151, help="opencv: Gaussian カーネル")
    parser.add_argument("--blur-sigma", type=float, default=40.0, help="ffmpeg: gblur sigma")
    parser.add_argument("--mosaic-scale", type=int, default=20)
    parser.add_argument("--padding", type=int, default=12)
    parser.add_argument("--merge-gap-x", type=int, default=60)
    parser.add_argument("--merge-gap-y", type=int, default=40)

    # tracking
    parser.add_argument("--iou-threshold", type=float, default=0.3)
    parser.add_argument("--max-gap-seconds", type=float, default=15.0, help="track 接続の最大ギャップ")
    parser.add_argument("--persistence", type=float, default=8.0, help="track 終了後も bbox を保持する秒数")
    parser.add_argument("--min-track-duration", type=float, default=0.0)

    parser.add_argument("--languages", nargs="+", default=["ja", "en"])
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--keep-intermediate", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"入力動画が見つかりません: {args.input}", file=sys.stderr)
        return 1
    if shutil.which("ffmpeg") is None:
        print("ffmpeg が見つかりません", file=sys.stderr)
        return 1

    overall_t0 = time.time()

    # ─── フルチャンク並列モード ────────────────────────────────────
    if args.full_chunks > 1:
        if args.blur_engine != "fill":
            print("--full-chunks は --blur-engine fill のみ対応", file=sys.stderr)
            return 1
        return _run_full_chunks(args, overall_t0)

    print(
        f"[blur] 検出器初期化 (backend={args.detector}, languages={args.languages}, "
        f"detect_scale={args.detect_scale})..."
    )
    t0 = time.time()
    if args.detector == "ocrmac":
        detector = OcrmacDetector(languages=args.languages, detect_scale=args.detect_scale)
    else:
        detector = TextDetector(languages=args.languages, detect_scale=args.detect_scale)
    print(f"[blur] 初期化: {time.time() - t0:.2f}s")

    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmpdir = Path(tmpdir_s)

        # ffmpeg/mask/fill engine では pre-speed 不要 (filter_complex で同時適用)
        # OpenCV engine のみ pre-speed して中間動画から処理
        if args.blur_engine in ("ffmpeg", "mask", "fill"):
            work_path = args.input  # 検出も blur も元動画ベース
        else:
            if abs(args.speed - 1.0) > 1e-6:
                sped_path = tmpdir / "sped_up.mp4"
                print(f"[blur] 速度変更を先に適用 ({args.speed}x) → {sped_path.name}...")
                t0 = time.time()
                apply_pre_speed(args.input, sped_path, args.speed)
                print(f"[blur] pre-speed: {time.time() - t0:.1f}s")
                work_path = sped_path
            else:
                work_path = args.input

        # scene change detection (optional)
        scene_changes: list[float] | None = None
        if args.scene_detect:
            print(f"[blur] シーン変化検出 (threshold={args.scene_threshold})...")
            t0 = time.time()
            scene_changes = detect_scene_changes(work_path, threshold=args.scene_threshold)
            print(f"[blur] scene change: {len(scene_changes)} 件 ({time.time() - t0:.1f}s)")

        # 動画情報取得
        cap = cv2.VideoCapture(str(work_path))
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / src_fps
        cap.release()

        timestamps = build_sample_timestamps(
            duration=duration,
            scene_changes=scene_changes,
            base_interval=args.base_interval,
        )
        print(f"[blur] 検出スケジュール: {len(timestamps)} フレーム (動画長 {duration:.1f}s)")

        t0 = time.time()
        detections, info = detect_at_timestamps(
            work_path, detector, timestamps,
            args.merge_gap_x, args.merge_gap_y,
            skip_threshold=args.skip_threshold,
            max_skip_streak=args.max_skip_streak,
        )
        skip_info = ""
        if info.get("n_skipped", 0) > 0:
            n_det = info.get("n_detected", 0)
            n_skip = info.get("n_skipped", 0)
            skip_pct = 100.0 * n_skip / max(1, n_det + n_skip)
            skip_info = f" (検出 {n_det}, スキップ {n_skip} = {skip_pct:.0f}%)"
        print(
            f"[blur] 検出完了: {len(detections)} frames{skip_info}, "
            f"{sum(len(b) for _, b in detections)} boxes, {time.time() - t0:.1f}s"
        )

        print(f"[blur] track 構築 (iou_threshold={args.iou_threshold})...")
        tracks = build_tracks(
            detections,
            iou_threshold=args.iou_threshold,
            max_gap_seconds=args.max_gap_seconds,
        )
        if args.min_track_duration > 0:
            tracks = filter_short_tracks(tracks, args.min_track_duration)
        print(f"[blur] track: {len(tracks)} 本")

        # blur + (speed) + encode を統合実行
        if args.blur_engine == "fill":
            print("[blur] 塗りつぶし色を track ごとにサンプリング...")
            t0 = time.time()
            sample_track_fill_colors(
                tracks=tracks,
                video_path=work_path,
                padding=args.padding,
            )
            print(f"[blur] 色サンプリング: {time.time() - t0:.1f}s")

            if args.chunks > 1:
                print(
                    f"[blur] ffmpeg 並列実行 ({args.chunks} chunks, {args.encoder}) "
                    f"+ speed={args.speed}x → {args.output}"
                )
                t0 = time.time()
                apply_ffmpeg_blur_chunked(
                    input_video=work_path,
                    output=args.output,
                    tracks=tracks,
                    duration=info["duration"],
                    persistence=args.persistence,
                    padding=args.padding,
                    frame_w=info["width"],
                    frame_h=info["height"],
                    speed=args.speed,
                    n_chunks=args.chunks,
                    encoder=args.encoder,
                    bitrate=args.bitrate,
                )
                print(f"[blur] ffmpeg チャンク並列+concat: {time.time() - t0:.1f}s")
            else:
                print(
                    f"[blur] ffmpeg 1パス (drawbox + {args.encoder}) "
                    f"+ speed={args.speed}x → {args.output}"
                )
                t0 = time.time()
                filter_str, vout, aout = build_solid_fill_filter_complex(
                    tracks=tracks,
                    persistence=args.persistence,
                    padding=args.padding,
                    frame_w=info["width"],
                    frame_h=info["height"],
                    speed=args.speed,
                )
                apply_ffmpeg_blur(
                    input_video=work_path,
                    output=args.output,
                    filter_complex=filter_str,
                    video_label=vout,
                    audio_label=aout,
                    encoder=args.encoder,
                    bitrate=args.bitrate,
                )
                print(f"[blur] ffmpeg 統合実行: {time.time() - t0:.1f}s")
        elif args.blur_engine == "mask":
            mask_path = tmpdir / "blur_mask.mp4"
            print(f"[blur] マスク動画生成 → {mask_path.name}")
            t0 = time.time()
            # gblur sigma の有効半径は ~3*sigma. それより小さい dilation だと
            # マスク内側まで透明化が及んで blur が弱まるので 3x sigma で確保.
            feather_compensation = int(round(args.mask_feather * 3))
            generate_mask_video(
                tracks=tracks,
                output_path=mask_path,
                fps=info["src_fps"],
                width=info["width"],
                height=info["height"],
                duration=info["duration"],
                persistence=args.persistence,
                padding=args.padding,
                feather_compensation=feather_compensation,
            )
            print(f"[blur] マスク生成: {time.time() - t0:.1f}s")

            print(
                f"[blur] ffmpeg 1パス (mask + {args.encoder}) blur(sigma={args.blur_sigma}) "
                f"+ speed={args.speed}x → {args.output}"
            )
            t0 = time.time()
            filter_str, vout, aout = build_mask_blur_filter_complex(
                sigma=args.blur_sigma,
                speed=args.speed,
                mask_feather=args.mask_feather,
            )
            apply_ffmpeg_blur(
                input_video=work_path,
                output=args.output,
                filter_complex=filter_str,
                video_label=vout,
                audio_label=aout,
                extra_inputs=[mask_path],
                encoder=args.encoder,
                bitrate=args.bitrate,
            )
            print(f"[blur] ffmpeg 統合実行: {time.time() - t0:.1f}s")
        elif args.blur_engine == "ffmpeg":
            print(
                f"[blur] ffmpeg 1パス (overlay + {args.encoder}) blur(sigma={args.blur_sigma}) "
                f"+ speed={args.speed}x → {args.output}"
            )
            t0 = time.time()
            filter_str, vout, aout = build_blur_filter_complex(
                tracks=tracks,
                persistence=args.persistence,
                padding=args.padding,
                frame_w=info["width"],
                frame_h=info["height"],
                sigma=args.blur_sigma,
                speed=args.speed,
            )
            apply_ffmpeg_blur(
                input_video=work_path,
                output=args.output,
                filter_complex=filter_str,
                video_label=vout,
                audio_label=aout,
                encoder=args.encoder,
                bitrate=args.bitrate,
            )
            print(f"[blur] ffmpeg 統合実行: {time.time() - t0:.1f}s")
        else:
            blurred_intermediate = tmpdir / "blurred_no_audio.mp4"
            print(f"[blur] OpenCV でぼかし合成 ({args.blur_method}) → {blurred_intermediate.name}...")
            t0 = time.time()
            render_blurred_video(
                input_path=work_path,
                output_path=blurred_intermediate,
                tracks=tracks,
                method=args.blur_method,
                blur_strength=args.blur_strength,
                mosaic_scale=args.mosaic_scale,
                padding=args.padding,
                persistence=args.persistence,
                info=info,
                preview=args.preview,
            )
            print(f"[blur] ぼかし合成: {time.time() - t0:.1f}s")

            print(f"[blur] 音声 mux → {args.output}")
            t0 = time.time()
            mux_audio_from(blurred_intermediate, work_path, args.output)
            print(f"[blur] エンコード: {time.time() - t0:.1f}s")

        if args.keep_intermediate:
            if work_path != args.input:
                kept = args.output.parent / f"{args.output.stem}_pre_speed.mp4"
                shutil.copy(work_path, kept)
                print(f"[blur] 中間 (sped): {kept}")
            mask_candidate = tmpdir / "blur_mask.mp4"
            if mask_candidate.exists():
                kept = args.output.parent / f"{args.output.stem}_mask.mp4"
                shutil.copy(mask_candidate, kept)
                print(f"[blur] 中間 (mask): {kept}")

    print(f"[blur] === 完了 (合計 {time.time() - overall_t0:.1f}s) ===")
    print(f"[blur] 出力: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
