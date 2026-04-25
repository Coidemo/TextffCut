"""フルチャンク並列化のワーカー関数.

各チャンクが独立に scene_detect + detect + tracks + colors + ffmpeg blur を実行する.
ProcessPoolExecutor から呼び出されるため top-level 関数として定義し、
依存モジュールは関数内で lazy import する (multiprocessing spawn 互換).
"""

from __future__ import annotations


def process_full_chunk(args: dict) -> dict:
    """1 チャンク分の検出 + ぼかし + エンコードを完結させる.

    Returns a stats dict for logging.
    """
    import re
    import subprocess
    import tempfile
    from pathlib import Path

    import cv2

    from core.text_blur.detector import (
        OcrmacDetector,
        merge_boxes,
        sample_edge_color,
    )
    from core.text_blur.ffmpeg import (
        _build_video_codec_args,
        _track_union_bbox,
        build_solid_fill_chunk_filter,
    )
    from core.text_blur.tracker import build_tracks, filter_short_tracks

    chunk_idx: int = args["chunk_idx"]
    input_video: str = args["input_video"]
    output_path: str = args["output_path"]
    abs_start: float = args["abs_start"]
    abs_dur: float = args["abs_dur"]
    ffmpeg_timeout = args.get("ffmpeg_timeout_sec", 1200)

    # ── Step 1: scene detect on chunk range ──────────────────────────────
    cmd = [
        "ffmpeg",
        "-ss", f"{abs_start:.3f}",
        "-t", f"{abs_dur:.3f}",
        "-i", str(input_video),
        "-vf", f"select='gt(scene,{args['scene_threshold']})',showinfo",
        "-an", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=ffmpeg_timeout)
    pat = re.compile(r"pts_time:([\d.]+)")
    # pts_time は -ss 適用後 (chunk-local) で出る
    scene_changes = [float(m.group(1)) for m in pat.finditer(result.stderr)]

    # ── Step 2: build sample timestamps (chunk-local) ────────────────────
    edge_offset = 0.1
    base_int = args["base_interval"]
    timestamps: set[float] = {edge_offset}
    if args["scene_detect"]:
        for sc in scene_changes:
            t = min(abs_dur - edge_offset, max(0.0, sc + edge_offset))
            timestamps.add(round(t, 4))
    t = base_int
    while t < abs_dur:
        timestamps.add(round(t, 4))
        t += base_int
    timestamps.add(round(max(0.0, abs_dur - edge_offset), 4))
    timestamps_sorted = sorted(timestamps)

    # ── Step 3: detect at timestamps (with skip) ─────────────────────────
    detector = OcrmacDetector(
        languages=args["languages"], detect_scale=args["detect_scale"]
    )

    cap = cv2.VideoCapture(str(input_video))
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detections: list[tuple[float, list]] = []
    last_small = None
    last_boxes = None
    skip_streak = 0
    n_detected = 0
    n_skipped = 0

    skip_threshold = args["skip_threshold"]
    max_skip_streak = args["max_skip_streak"]
    diff_resize = (args.get("diff_resize_w", 320), args.get("diff_resize_h", 180))

    for t_local in timestamps_sorted:
        if t_local < 0 or t_local >= abs_dur:
            continue
        t_abs = abs_start + t_local
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_abs * src_fps)))
        ret, frame = cap.read()
        if not ret:
            continue

        if (
            skip_threshold > 0.0
            and last_small is not None
            and last_boxes is not None
            and skip_streak < max_skip_streak
        ):
            current_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            diff = float(cv2.absdiff(current_small, last_small).mean()) / 255.0
            if diff < skip_threshold:
                detections.append((t_local, last_boxes))
                skip_streak += 1
                n_skipped += 1
                continue

        raw_boxes = detector.detect(frame)
        merged = merge_boxes(
            raw_boxes, gap_x=args["merge_gap_x"], gap_y=args["merge_gap_y"]
        )
        detections.append((t_local, merged))
        n_detected += 1
        if skip_threshold > 0.0:
            last_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            last_boxes = merged
            skip_streak = 0

    # ── Step 4: build tracks (chunk-local) ────────────────────────────────
    tracks = build_tracks(
        detections,
        iou_threshold=args["iou_threshold"],
        max_gap_seconds=args["max_gap_seconds"],
    )
    if args["min_track_duration"] > 0:
        tracks = filter_short_tracks(tracks, args["min_track_duration"])

    # ── Step 5: sample fill colors (using absolute time on input) ────────
    for tr in tracks:
        t_mid_local = (tr.t_start + tr.t_end) / 2
        t_mid_abs = abs_start + t_mid_local
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_mid_abs * src_fps)))
        ret, frame = cap.read()
        if not ret:
            continue
        ub = _track_union_bbox(tr, args["padding"], width, height)
        tr.fill_color = sample_edge_color(
            frame, ub, border_width=args.get("color_sample_border", 10)
        )
    cap.release()

    # ── Step 6: build chunk filter (chunk-local times = use chunk_start=0) ─
    filter_str, vout, aout = build_solid_fill_chunk_filter(
        tracks=tracks,
        chunk_start=0.0,  # 入力 ffmpeg が seek 済みなので相対 0
        chunk_dur=abs_dur,
        persistence=args["persistence"],
        padding=args["padding"],
        frame_w=width,
        frame_h=height,
        speed=args["speed"],
    )

    # ── Step 7: ffmpeg blur+encode chunk ──────────────────────────────────
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".filterscript", delete=False) as f:
        f.write(filter_str)
        script_path = f.name
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{abs_start:.3f}",
            "-t", f"{abs_dur:.3f}",
            "-i", str(input_video),
            "-filter_complex_script", script_path,
            "-map", vout, "-map", aout,
        ]
        cmd.extend(
            _build_video_codec_args(
                args["encoder"], args["crf"], args["preset"], args["bitrate"]
            )
        )
        cmd.extend(
            [
                "-c:a", "aac", "-b:a", "192k",
                "-loglevel", "error",
                str(output_path),
            ]
        )
        subprocess.run(cmd, check=True, timeout=ffmpeg_timeout)
    finally:
        Path(script_path).unlink(missing_ok=True)

    return {
        "chunk_idx": chunk_idx,
        "n_detected": n_detected,
        "n_skipped": n_skipped,
        "n_tracks": len(tracks),
        "n_scene_changes": len(scene_changes),
    }
