"""ffmpeg ネイティブで blur を適用する実装.

2 つの方式をサポート:
  - overlay 方式: track ごとに crop+gblur+overlay 層を積む (track 数に比例して filter graph 増大)
  - mask 方式  : 全画面 blur + マスク動画で alphamerge (filter graph が track 数に依らず固定)

エンコーダーは libx264 と h264_videotoolbox (Apple Silicon ハードウェア) を選べる.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from detector import Box, sample_edge_color
from tracker import Track, collect_active_boxes


def _track_union_bbox(track: Track, padding: int, max_w: int, max_h: int) -> Box:
    """track 内の全 bbox の union (+padding) を返す.

    静的テキストなら全ポイントで同位置, 移動テキストなら全位置を覆う矩形.
    """
    x1 = min(p.box.x1 for p in track.points)
    y1 = min(p.box.y1 for p in track.points)
    x2 = max(p.box.x2 for p in track.points)
    y2 = max(p.box.y2 for p in track.points)
    return Box(
        max(0, x1 - padding),
        max(0, y1 - padding),
        min(max_w, x2 + padding),
        min(max_h, y2 + padding),
    )


def build_blur_filter_complex(
    tracks: list[Track],
    persistence: float,
    padding: int,
    frame_w: int,
    frame_h: int,
    sigma: float = 30.0,
    speed: float = 1.0,
) -> tuple[str, str, str]:
    """tracks → ffmpeg filter_complex 文字列 と video/audio output ラベルを返す.

    生成される構造 (speed != 1.0 の場合, blur と setpts/atempo を統合):
        [0:v]split=N+1[main][src0][src1]...[srcN-1];
        [src*]crop+gblur → [blur*];
        [main][blur*]overlay=...:enable='between(t,T*a,T*b)' → ... → [merged];
        [merged]setpts=PTS/SPEED[vout];
        [0:a]atempo=SPEED[aout]

    overlay の enable は original time domain (検出した t をそのまま使用).
    setpts は overlay の後に適用するので enable 式の変換は不要.
    """
    parts: list[str] = []
    n = len(tracks)

    if n == 0:
        # No blur. Just speed change (or copy)
        if abs(speed - 1.0) < 1e-6:
            parts.append("[0:v]copy[vout]")
            parts.append("[0:a]anull[aout]")
        else:
            parts.append(f"[0:v]setpts=PTS/{speed}[vout]")
            parts.append(f"[0:a]atempo={speed}[aout]")
        return ";".join(parts), "[vout]", "[aout]"

    # Step 1: split source video into 1 main + N copies
    split_outputs = "".join(f"[src{i}]" for i in range(n))
    parts.append(f"[0:v]split={n + 1}[main]{split_outputs}")

    # Step 2: crop + gblur per track
    union_bboxes: list[Box] = []
    for i, tr in enumerate(tracks):
        ub = _track_union_bbox(tr, padding, frame_w, frame_h)
        union_bboxes.append(ub)
        w = ub.x2 - ub.x1
        h = ub.y2 - ub.y1
        if w <= 0 or h <= 0:
            parts.append(f"[src{i}]crop=1:1:0:0,gblur=sigma=1[blur{i}]")
        else:
            parts.append(
                f"[src{i}]crop={w}:{h}:{ub.x1}:{ub.y1},gblur=sigma={sigma}[blur{i}]"
            )

    # Step 3: chain overlays with original-time enable expressions
    prev = "main"
    for i, (tr, ub) in enumerate(zip(tracks, union_bboxes, strict=False)):
        t_start = max(0.0, tr.t_start - persistence)
        t_end = tr.t_end + persistence
        is_last = i == n - 1
        out_label = "merged" if is_last else f"v{i}"
        parts.append(
            f"[{prev}][blur{i}]overlay={ub.x1}:{ub.y1}"
            f":enable='between(t,{t_start:.3f},{t_end:.3f})'[{out_label}]"
        )
        prev = out_label

    # Step 4: speed change (setpts + atempo) if needed
    if abs(speed - 1.0) < 1e-6:
        parts.append("[merged]copy[vout]")
        parts.append("[0:a]anull[aout]")
    else:
        parts.append(f"[merged]setpts=PTS/{speed}[vout]")
        parts.append(f"[0:a]atempo={speed}[aout]")

    return ";".join(parts), "[vout]", "[aout]"


def _build_video_codec_args(encoder: str, crf: int, preset: str, bitrate: str) -> list[str]:
    """エンコーダーに応じた ffmpeg 引数を返す."""
    if encoder == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-tag:v", "avc1"]
    # libx264 default
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def apply_ffmpeg_blur(
    input_video: Path,
    output: Path,
    filter_complex: str,
    video_label: str,
    audio_label: str,
    extra_inputs: list[Path] | None = None,
    encoder: str = "libx264",
    crf: int = 20,
    preset: str = "medium",
    bitrate: str = "8M",
) -> None:
    """ffmpeg で filter_complex を 1 パス実行 (blur + speed + audio + encode 統合)."""
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".filterscript", delete=False
    ) as f:
        f.write(filter_complex)
        script_path = f.name

    try:
        cmd = ["ffmpeg", "-y", "-i", str(input_video)]
        for extra in (extra_inputs or []):
            cmd.extend(["-i", str(extra)])
        cmd.extend([
            "-filter_complex_script", script_path,
            "-map", video_label,
            "-map", audio_label,
        ])
        cmd.extend(_build_video_codec_args(encoder, crf, preset, bitrate))
        cmd.extend([
            "-c:a", "aac", "-b:a", "192k",
            "-loglevel", "error",
            str(output),
        ])
        subprocess.run(cmd, check=True)
    finally:
        Path(script_path).unlink(missing_ok=True)


def generate_mask_video(
    tracks: list[Track],
    output_path: Path,
    fps: float,
    width: int,
    height: int,
    duration: float,
    persistence: float,
    padding: int,
    feather_compensation: int = 0,
) -> None:
    """各時刻で active な bbox を白で塗ったマスク動画を生成.

    feather_compensation: 後段の gblur で内側まで透明化しないよう、事前に bbox を
    この pixels 分膨らませてマスクを描く. 通常は mask_feather sigma の 2 倍くらいを
    指定する (gaussian の有効半径相当). 0 なら従来通り padding のみ.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height), isColor=True)
    if not writer.isOpened():
        raise RuntimeError(f"マスク動画の書き出しに失敗: {output_path}")

    total_frames = int(round(duration * fps))
    pbar = tqdm(total=total_frames, desc="mask ", leave=False)
    total_pad = padding + feather_compensation

    for frame_idx in range(total_frames):
        timestamp = frame_idx / fps
        active = collect_active_boxes(tracks, timestamp, persistence=persistence)
        mask = np.zeros((height, width, 3), dtype=np.uint8)
        for box in active:
            exp = box.expand(total_pad, width, height)
            if exp.x2 > exp.x1 and exp.y2 > exp.y1:
                mask[exp.y1 : exp.y2, exp.x1 : exp.x2] = 255
        writer.write(mask)
        pbar.update(1)

    pbar.close()
    writer.release()


def build_solid_fill_chunk_filter(
    tracks: list[Track],
    chunk_start: float,
    chunk_dur: float,
    persistence: float,
    padding: int,
    frame_w: int,
    frame_h: int,
    speed: float = 1.0,
) -> tuple[str, str, str]:
    """チャンクごとに drawbox + speed を組み立てる filter_complex.

    chunk 内に visible (persistence 込みで) な track のみ対象にし、
    enable 時刻を chunk-relative に変換 (subtract chunk_start).
    """
    parts: list[str] = []
    chunk_end = chunk_start + chunk_dur

    relevant: list[Track] = []
    for tr in tracks:
        vis_start = max(0.0, tr.t_start - persistence)
        vis_end = tr.t_end + persistence
        if vis_end < chunk_start or vis_start > chunk_end:
            continue
        relevant.append(tr)

    if not relevant:
        if abs(speed - 1.0) < 1e-6:
            parts.append("[0:v]copy[vout]")
            parts.append("[0:a]anull[aout]")
        else:
            parts.append(f"[0:v]setpts=PTS/{speed}[vout]")
            parts.append(f"[0:a]atempo={speed}[aout]")
        return ";".join(parts), "[vout]", "[aout]"

    prev = "0:v"
    for i, tr in enumerate(relevant):
        ub = _track_union_bbox(tr, padding, frame_w, frame_h)
        w = ub.x2 - ub.x1
        h = ub.y2 - ub.y1
        # chunk-relative 時刻に変換 + chunk 内にクランプ
        t_start = max(0.0, (tr.t_start - persistence) - chunk_start)
        t_end = min(chunk_dur, (tr.t_end + persistence) - chunk_start)
        b, g, r = tr.fill_color
        color_hex = f"0x{r:02X}{g:02X}{b:02X}"
        is_last = i == len(relevant) - 1
        out_label = "vmerged" if is_last else f"v{i}"
        if w <= 0 or h <= 0:
            parts.append(f"[{prev}]null[{out_label}]")
        else:
            parts.append(
                f"[{prev}]drawbox=x={ub.x1}:y={ub.y1}:w={w}:h={h}"
                f":color={color_hex}@1:t=fill"
                f":enable='between(t,{t_start:.3f},{t_end:.3f})'[{out_label}]"
            )
        prev = out_label

    if abs(speed - 1.0) < 1e-6:
        parts.append("[vmerged]copy[vout]")
        parts.append("[0:a]anull[aout]")
    else:
        parts.append(f"[vmerged]setpts=PTS/{speed}[vout]")
        parts.append(f"[0:a]atempo={speed}[aout]")

    return ";".join(parts), "[vout]", "[aout]"


def _process_one_chunk(args_tuple) -> int:
    """1 つのチャンクを ffmpeg で処理. ProcessPoolExecutor から呼ばれる worker."""
    (
        chunk_idx, input_video, output_chunk, chunk_start, chunk_dur,
        filter_complex, video_label, audio_label,
        encoder, crf, preset, bitrate,
    ) = args_tuple
    output_chunk = Path(output_chunk)
    output_chunk.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".filterscript", delete=False) as f:
        f.write(filter_complex)
        script_path = f.name
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{chunk_start:.3f}",
            "-t", f"{chunk_dur:.3f}",  # input option: 入力読み取り時間
            "-i", str(input_video),
            "-filter_complex_script", script_path,
            "-map", video_label, "-map", audio_label,
        ]
        cmd.extend(_build_video_codec_args(encoder, crf, preset, bitrate))
        cmd.extend([
            "-c:a", "aac", "-b:a", "192k",
            "-loglevel", "error",
            str(output_chunk),
        ])
        subprocess.run(cmd, check=True)
    finally:
        Path(script_path).unlink(missing_ok=True)
    return chunk_idx


def apply_ffmpeg_blur_chunked(
    input_video: Path,
    output: Path,
    tracks: list[Track],
    duration: float,
    persistence: float,
    padding: int,
    frame_w: int,
    frame_h: int,
    speed: float,
    n_chunks: int,
    encoder: str = "h264_videotoolbox",
    crf: int = 20,
    preset: str = "medium",
    bitrate: str = "8M",
) -> None:
    """動画を N チャンクに分割して ffmpeg を並列実行 → concat で結合."""
    import concurrent.futures as futures

    output.parent.mkdir(parents=True, exist_ok=True)
    chunk_dur = duration / n_chunks

    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmpdir = Path(tmpdir_s)
        chunk_paths: list[Path] = []
        worker_args = []

        for i in range(n_chunks):
            chunk_start = i * chunk_dur
            # 最終チャンクは duration までしっかり拾う
            this_dur = (duration - chunk_start) if i == n_chunks - 1 else chunk_dur
            filter_str, vout, aout = build_solid_fill_chunk_filter(
                tracks=tracks,
                chunk_start=chunk_start,
                chunk_dur=this_dur,
                persistence=persistence,
                padding=padding,
                frame_w=frame_w,
                frame_h=frame_h,
                speed=speed,
            )
            chunk_path = tmpdir / f"chunk_{i:04d}.mp4"
            chunk_paths.append(chunk_path)
            worker_args.append((
                i, str(input_video), str(chunk_path),
                chunk_start, this_dur,
                filter_str, vout, aout,
                encoder, crf, preset, bitrate,
            ))

        # 並列 ffmpeg 実行
        with futures.ProcessPoolExecutor(max_workers=n_chunks) as pool:
            done_count = 0
            for fut in futures.as_completed([pool.submit(_process_one_chunk, a) for a in worker_args]):
                fut.result()
                done_count += 1
                print(f"[blur]   chunk {done_count}/{n_chunks} 完了")

        # concat demuxer で結合
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
            str(output),
        ]
        subprocess.run(cmd, check=True)


def sample_track_fill_colors(
    tracks: list[Track],
    video_path: Path,
    padding: int,
    border_width: int = 10,
) -> None:
    """各 track の中央時刻フレームから縁色をサンプリングして fill_color に格納."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    for tr in tracks:
        t_mid = (tr.t_start + tr.t_end) / 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_mid * fps)))
        ret, frame = cap.read()
        if not ret:
            continue
        ub = _track_union_bbox(tr, padding, width, height)
        tr.fill_color = sample_edge_color(frame, ub, border_width=border_width)

    cap.release()


def build_solid_fill_filter_complex(
    tracks: list[Track],
    persistence: float,
    padding: int,
    frame_w: int,
    frame_h: int,
    speed: float = 1.0,
) -> tuple[str, str, str]:
    """solid fill (drawbox) の filter_complex.

    各 track の領域を fill_color (BGR) で塗りつぶし. ffmpeg の drawbox は超軽量.
    """
    parts: list[str] = []
    n = len(tracks)

    if n == 0:
        if abs(speed - 1.0) < 1e-6:
            parts.append("[0:v]copy[vout]")
            parts.append("[0:a]anull[aout]")
        else:
            parts.append(f"[0:v]setpts=PTS/{speed}[vout]")
            parts.append(f"[0:a]atempo={speed}[aout]")
        return ";".join(parts), "[vout]", "[aout]"

    prev = "0:v"
    for i, tr in enumerate(tracks):
        ub = _track_union_bbox(tr, padding, frame_w, frame_h)
        w = ub.x2 - ub.x1
        h = ub.y2 - ub.y1
        t_start = max(0.0, tr.t_start - persistence)
        t_end = tr.t_end + persistence
        # BGR → RGB hex
        b, g, r = tr.fill_color
        color_hex = f"0x{r:02X}{g:02X}{b:02X}"
        is_last = i == n - 1
        out_label = "vmerged" if is_last else f"v{i}"
        if w <= 0 or h <= 0:
            # スキップ用 noop
            parts.append(f"[{prev}]null[{out_label}]")
        else:
            parts.append(
                f"[{prev}]drawbox=x={ub.x1}:y={ub.y1}:w={w}:h={h}"
                f":color={color_hex}@1:t=fill"
                f":enable='between(t,{t_start:.3f},{t_end:.3f})'[{out_label}]"
            )
        prev = out_label

    if abs(speed - 1.0) < 1e-6:
        parts.append("[vmerged]copy[vout]")
        parts.append("[0:a]anull[aout]")
    else:
        parts.append(f"[vmerged]setpts=PTS/{speed}[vout]")
        parts.append(f"[0:a]atempo={speed}[aout]")

    return ";".join(parts), "[vout]", "[aout]"


def build_mask_blur_filter_complex(
    sigma: float = 30.0,
    speed: float = 1.0,
    mask_feather: float = 15.0,
) -> tuple[str, str, str]:
    """マスク方式の filter_complex.

    入力: [0:v] = 元動画, [1:v] = マスク動画 (白=blur 領域, 黒=元のまま)

    色滲み対策:
      blur 入力に「マスク内だけ元画像、外は黒」を渡すのではなく、
      maskedmerge で「ピクセル単位に元 or blur を選ぶ」形にする.
      maskedmerge は通常 blur が周囲の色を引き込むのを完全には防げないが、
      mask_feather でマスク境界を gblur することで視覚的な不自然さを軽減.

    構造:
        [0:v]split[orig][src];
        [src]gblur=sigma=S[blurred];
        [1:v]format=gray,gblur=sigma=F[mask_soft];
        [orig][blurred][mask_soft]maskedmerge[merged];
        [merged]setpts=PTS/SPEED[vout];
        [0:a]atempo=SPEED[aout]

    maskedmerge: out = (255-mask)/255 * orig + mask/255 * blurred
    → mask=255 の場所は完全に blurred、mask=0 の場所は完全に orig、
       中間値はリニア合成 (フェザー).
    """
    parts: list[str] = []
    parts.append("[0:v]split[orig][src]")
    parts.append(f"[src]gblur=sigma={sigma}[blurred]")
    # alphamerge は mask の各 pixel から alpha を取るので gray スケールに変換.
    # mask に gblur をかけて soft edge にすることで境界を自然にする.
    if mask_feather > 0:
        parts.append(f"[1:v]format=gray,gblur=sigma={mask_feather}[mask_soft]")
    else:
        parts.append("[1:v]format=gray[mask_soft]")
    # blurred を alpha 付き RGBA にして overlay → orig 上に乗せる.
    parts.append("[blurred][mask_soft]alphamerge[blur_alpha]")
    parts.append("[orig][blur_alpha]overlay[merged]")
    if abs(speed - 1.0) < 1e-6:
        parts.append("[merged]copy[vout]")
        parts.append("[0:a]anull[aout]")
    else:
        parts.append(f"[merged]setpts=PTS/{speed}[vout]")
        parts.append(f"[0:a]atempo={speed}[aout]")
    return ";".join(parts), "[vout]", "[aout]"
