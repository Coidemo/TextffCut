"""
時間関連のユーティリティ関数
"""


def format_time(seconds: float) -> str:
    """秒数を時間:分:秒の形式に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours}時間{minutes}分{seconds}秒"
    elif minutes > 0:
        return f"{minutes}分{seconds}秒"
    else:
        return f"{seconds}秒"


def format_timestamp(seconds: float, fps: float | None = None) -> str:
    """秒数をSRT形式のタイムスタンプに変換"""
    # フレームレートが指定されている場合はフレーム境界に調整
    if fps:
        frame_number = round(seconds * fps)
        seconds = frame_number / fps

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"


def time_to_seconds(time_str: str) -> float:
    """SRT形式のタイムスタンプを秒数に変換"""
    hours, minutes, seconds = time_str.replace(",", ".").split(":")
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)


def seconds_to_timecode(seconds: float, fps: int = 30) -> str:
    """秒数をタイムコード形式に変換 (HH:MM:SS:FF)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    frames = int((seconds % 1) * fps)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def frames_to_timecode(frames: int, fps: int = 30) -> str:
    """フレーム数をタイムコード形式に変換"""
    seconds = frames / fps
    return seconds_to_timecode(seconds, fps)


def seconds_to_srt_time(seconds: float) -> str:
    """秒数をSRT形式のタイムスタンプに変換 (HH:MM:SS,mmm)

    Args:
        seconds: 秒数

    Returns:
        SRT形式のタイムスタンプ (例: "00:01:23,456")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def calculate_frame_boundaries(start: float, end: float, fps: float, timeline_fps: int = 30) -> tuple[int, int]:
    """
    開始・終了時間をフレーム境界に変換

    Args:
        start: 開始時間（秒）
        end: 終了時間（秒）
        fps: ソース動画のFPS
        timeline_fps: タイムラインのFPS

    Returns:
        タイムライン上の開始フレーム、期間フレーム数
    """
    # ソース動画のフレーム番号に変換
    start_frames = int(round(start * fps))
    duration_frames = int(round((end - start) * fps))

    # タイムラインのフレームレートに合わせて変換
    timeline_start_frames = int(round(start_frames * (timeline_fps / fps)))
    timeline_duration_frames = int(round(duration_frames * (timeline_fps / fps)))

    return timeline_start_frames, timeline_duration_frames
