"""
最終動画（MP4）生成

FFmpegのfilter_complexを使用して、
クリップ結合 + フレームオーバーレイ + タイトル画像 + 字幕画像 + BGM + SEを
1つの完成動画として出力する。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def db_to_linear(db: float) -> float:
    """dB値をリニア音量に変換"""
    return 10 ** (db / 20)


def generate_final_video(
    video_path: Path,
    time_ranges: list[tuple[float, float]],
    output_path: Path,
    *,
    # 字幕
    subtitle_images: list[tuple] | None = None,
    subtitle_position: str = "bottom",
    subtitle_margin_bottom: int = 80,
    # タイトル画像
    title_image_path: Path | None = None,
    title_duration: float = 5.0,
    # フレームオーバーレイ
    frame_path: Path | None = None,
    # BGM
    bgm_path: Path | None = None,
    bgm_volume_db: float = -25,
    bgm_loop: bool = True,
    # 効果音
    se_placements: list | None = None,
    se_volume_db: float = -20,
    # 出力設定
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    crf: int = 18,
    progress_callback: Callable | None = None,
) -> Path:
    """最終動画を生成する

    処理フロー:
    1. 時間範囲からconcatリスト生成 → ffmpeg concat demuxerで結合
    2. filter_complexでオーバーレイ（フレーム、タイトル、字幕）
    3. 音声ミックス（元音声 + BGM + SE）
    4. 出力

    Args:
        video_path: 入力動画パス
        time_ranges: 切り抜き時間範囲 [(start, end), ...]
        output_path: 出力MP4パス
        subtitle_images: [(SubtitleEntry, Path), ...] 字幕画像リスト
        subtitle_position: 字幕位置 ("bottom" or "top")
        subtitle_margin_bottom: 字幕下マージン（px）
        title_image_path: タイトル画像パス（透過PNG）
        title_duration: タイトル表示秒数
        frame_path: フレーム画像パス（透過PNG）
        bgm_path: BGMファイルパス
        bgm_volume_db: BGM音量（dB）
        bgm_loop: BGMをループさせるか
        se_placements: SEPlacementのリスト
        se_volume_db: SE音量（dB）
        resolution: 出力解像度 (width, height)
        fps: フレームレート
        video_codec: 映像コーデック
        audio_codec: 音声コーデック
        crf: 品質パラメータ（低いほど高品質）
        progress_callback: 進捗コールバック

    Returns:
        出力MP4パス
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Phase 1: クリップ結合
        if progress_callback:
            progress_callback("クリップ結合中...")
        base_video = tmpdir / "base.mp4"
        _concat_clips(video_path, time_ranges, base_video, fps)

        # Phase 2-4: filter_complex + 音声ミックス + 出力
        if progress_callback:
            progress_callback("映像・音声合成中...")
        _compose_final(
            base_video=base_video,
            output_path=output_path,
            subtitle_images=subtitle_images,
            subtitle_position=subtitle_position,
            subtitle_margin_bottom=subtitle_margin_bottom,
            title_image_path=title_image_path,
            title_duration=title_duration,
            frame_path=frame_path,
            bgm_path=bgm_path,
            bgm_volume_db=bgm_volume_db,
            bgm_loop=bgm_loop,
            se_placements=se_placements,
            se_volume_db=se_volume_db,
            resolution=resolution,
            fps=fps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            crf=crf,
        )

    logger.info(f"最終動画生成完了: {output_path}")
    if progress_callback:
        progress_callback("完了")
    return output_path


def _concat_clips(
    video_path: Path,
    time_ranges: list[tuple[float, float]],
    output_path: Path,
    fps: int,
) -> None:
    """時間範囲から動画クリップを結合する"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 各クリップを抽出
        clip_paths = []
        for i, (start, end) in enumerate(time_ranges):
            clip_path = tmpdir / f"clip_{i:04d}.mp4"
            duration = end - start
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", str(video_path),
                "-c:v", "libx264", "-crf", "18",
                "-c:a", "aac",
                "-r", str(fps),
                "-avoid_negative_ts", "make_zero",
                str(clip_path),
            ]
            _run_ffmpeg(cmd, timeout=max(30, int(duration * 5)))
            clip_paths.append(clip_path)

        # concatリスト生成（パス中のシングルクォートをエスケープ）
        concat_list = tmpdir / "concat.txt"

        def _escape_concat_path(p: Path) -> str:
            # FFmpeg concat形式: シングルクォート内の ' は '\'' でエスケープ
            return str(p).replace("'", "'\\''")

        concat_list.write_text(
            "\n".join(f"file '{_escape_concat_path(p)}'" for p in clip_paths),
            encoding="utf-8",
        )

        # 結合
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        total_dur = sum(e - s for s, e in time_ranges)
        _run_ffmpeg(cmd, timeout=max(30, int(total_dur * 3)))

    logger.info(f"クリップ結合完了: {len(time_ranges)}クリップ → {output_path.name}")


def _compose_final(
    base_video: Path,
    output_path: Path,
    *,
    subtitle_images: list[tuple] | None,
    subtitle_position: str,
    subtitle_margin_bottom: int,
    title_image_path: Path | None,
    title_duration: float,
    frame_path: Path | None,
    bgm_path: Path | None,
    bgm_volume_db: float,
    bgm_loop: bool,
    se_placements: list | None,
    se_volume_db: float,
    resolution: tuple[int, int],
    fps: int,
    video_codec: str,
    audio_codec: str,
    crf: int,
) -> None:
    """映像・音声を合成して最終出力を生成する"""
    cmd = ["ffmpeg", "-y"]
    input_index = 0

    # --- 入力ファイル ---
    # [0] ベース動画
    cmd.extend(["-i", str(base_video)])
    base_idx = input_index
    input_index += 1

    # フレーム画像
    frame_idx = None
    if frame_path and frame_path.exists():
        cmd.extend(["-i", str(frame_path)])
        frame_idx = input_index
        input_index += 1

    # タイトル画像
    title_idx = None
    if title_image_path and title_image_path.exists():
        cmd.extend(["-i", str(title_image_path)])
        title_idx = input_index
        input_index += 1

    # 字幕画像
    subtitle_indices = []
    if subtitle_images:
        for entry, img_path in subtitle_images:
            if img_path.exists():
                cmd.extend(["-i", str(img_path)])
                subtitle_indices.append((input_index, entry))
                input_index += 1

    # BGM
    bgm_idx = None
    if bgm_path and bgm_path.exists():
        if bgm_loop:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-i", str(bgm_path)])
        bgm_idx = input_index
        input_index += 1

    # SE
    se_indices = []
    if se_placements:
        for placement in se_placements:
            se_path = Path(placement.se_file)
            if se_path.exists():
                cmd.extend(["-i", str(se_path)])
                se_indices.append((input_index, placement))
                input_index += 1

    # --- filter_complex構築 ---
    filters, video_out, audio_out = build_filter_complex(
        base_idx=base_idx,
        resolution=resolution,
        frame_idx=frame_idx,
        title_idx=title_idx,
        title_duration=title_duration,
        subtitle_indices=subtitle_indices,
        subtitle_position=subtitle_position,
        subtitle_margin_bottom=subtitle_margin_bottom,
        bgm_idx=bgm_idx,
        bgm_volume_db=bgm_volume_db,
        se_indices=se_indices,
        se_volume_db=se_volume_db,
    )

    if filters:
        cmd.extend(["-filter_complex", filters])
        cmd.extend(["-map", f"[{video_out}]", "-map", f"[{audio_out}]"])
    else:
        cmd.extend(["-map", f"{base_idx}:v", "-map", f"{base_idx}:a"])

    # --- 出力設定 ---
    cmd.extend([
        "-c:v", video_codec,
        "-crf", str(crf),
        "-c:a", audio_codec,
        "-b:a", "192k",
        "-r", str(fps),
        "-shortest",
        str(output_path),
    ])

    # ベース動画の長さからタイムアウトを推定
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(base_video)],
        capture_output=True, text=True, timeout=10,
    )
    try:
        duration = float(probe.stdout.strip())
    except (ValueError, AttributeError):
        duration = 120.0

    _run_ffmpeg(cmd, timeout=max(60, int(duration * 10)))


def build_filter_complex(
    *,
    base_idx: int,
    resolution: tuple[int, int],
    frame_idx: int | None = None,
    title_idx: int | None = None,
    title_duration: float = 5.0,
    subtitle_indices: list[tuple[int, object]] | None = None,
    subtitle_position: str = "bottom",
    subtitle_margin_bottom: int = 80,
    bgm_idx: int | None = None,
    bgm_volume_db: float = -25,
    se_indices: list[tuple[int, object]] | None = None,
    se_volume_db: float = -20,
) -> tuple[str, str, str]:
    """filter_complex文字列を構築する

    Returns:
        (filter_complex_str, video_output_label, audio_output_label)
        フィルタが不要な場合は ("", "", "") を返す
    """
    has_video_filters = frame_idx is not None or title_idx is not None or subtitle_indices
    has_audio_filters = bgm_idx is not None or se_indices

    if not has_video_filters and not has_audio_filters:
        return ("", "", "")

    w, h = resolution
    filters = []
    current_video = f"[{base_idx}:v]"

    # スケール（解像度合わせ）
    scale_label = "scaled"
    filters.append(f"{current_video}scale={w}:{h}:force_original_aspect_ratio=decrease,"
                   f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2[{scale_label}]")
    current_video = f"[{scale_label}]"

    # フレームオーバーレイ（全編）
    if frame_idx is not None:
        out_label = "framed"
        filters.append(
            f"[{frame_idx}:v]scale={w}:{h}[frame_scaled];"
            f"{current_video}[frame_scaled]overlay=0:0[{out_label}]"
        )
        current_video = f"[{out_label}]"

    # タイトル画像オーバーレイ（冒頭のみ）
    if title_idx is not None:
        out_label = "titled"
        filters.append(
            f"[{title_idx}:v]scale={w}:{h}[title_scaled];"
            f"{current_video}[title_scaled]overlay=0:0:"
            f"enable='between(t,0,{title_duration})'[{out_label}]"
        )
        current_video = f"[{out_label}]"

    # 字幕画像オーバーレイ
    if subtitle_indices:
        for i, (idx, entry) in enumerate(subtitle_indices):
            out_label = f"sub{i}"
            if subtitle_position == "top":
                y_expr = str(subtitle_margin_bottom)
            else:
                y_expr = f"H-h-{subtitle_margin_bottom}"
            filters.append(
                f"{current_video}[{idx}:v]overlay=x=(W-w)/2:y={y_expr}:"
                f"enable='between(t,{entry.start_time:.3f},{entry.end_time:.3f})'[{out_label}]"
            )
            current_video = f"[{out_label}]"

    video_out = current_video.strip("[]")

    # --- 音声フィルタ ---
    audio_parts = [f"[{base_idx}:a]"]

    if bgm_idx is not None:
        bgm_vol = db_to_linear(bgm_volume_db)
        bgm_label = "bgm_vol"
        filters.append(f"[{bgm_idx}:a]volume={bgm_vol:.6f}[{bgm_label}]")
        audio_parts.append(f"[{bgm_label}]")

    if se_indices:
        for i, (idx, placement) in enumerate(se_indices):
            se_vol = db_to_linear(se_volume_db)
            delay_ms = int(placement.timestamp * 1000)
            se_label = f"se{i}"
            filters.append(
                f"[{idx}:a]volume={se_vol:.6f},"
                f"adelay={delay_ms}|{delay_ms}[{se_label}]"
            )
            audio_parts.append(f"[{se_label}]")

    if len(audio_parts) > 1:
        audio_out = "outa"
        amix_inputs = "".join(audio_parts)
        filters.append(
            f"{amix_inputs}amix=inputs={len(audio_parts)}:"
            f"duration=first:dropout_transition=2[{audio_out}]"
        )
    else:
        audio_out = f"{base_idx}:a"

    filter_complex = ";".join(filters)
    return (filter_complex, video_out, audio_out)


def generate_concat_list(time_ranges: list[tuple[float, float]]) -> str:
    """concatリスト用のFFmpegフィルタ式を生成する（テスト用に公開）"""
    parts = []
    for i, (start, end) in enumerate(time_ranges):
        parts.append(f"# clip {i}: {start:.3f} - {end:.3f} ({end - start:.3f}s)")
    return "\n".join(parts)


def _run_ffmpeg(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """FFmpegコマンドを実行する"""
    logger.debug(f"FFmpeg: {' '.join(str(c) for c in cmd[:10])}...")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr[-500:] if result.stderr else "(no stderr)"
        raise RuntimeError(f"FFmpeg failed (rc={result.returncode}): {stderr}")
    return result
