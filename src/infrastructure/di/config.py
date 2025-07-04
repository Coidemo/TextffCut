"""
DI設定クラス

DIコンテナ用の設定を管理
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionKeys:
    """セッションキーの一元管理（型安全）"""

    TRANSCRIPTION_RESULT = "transcription_result"
    EDITED_TEXT = "edited_text"
    VIDEO_PATH = "video_path"
    TIME_RANGES = "time_ranges"
    ADJUSTED_TIME_RANGES = "adjusted_time_ranges"
    EXPORT_SETTINGS = "export_settings"
    SILENCE_THRESHOLD = "silence_threshold"
    MIN_SILENCE_DURATION = "min_silence_duration"
    MIN_SEGMENT_DURATION = "min_segment_duration"
    VIDEO_INFO = "video_info"
    SELECTED_VIDEO = "selected_video"


@dataclass
class DIConfig:
    """DIコンテナ用の設定"""

    # アプリケーション基本設定
    app_name: str = "TextffCut"
    version: str = "2.1"
    debug: bool = False

    # パス設定
    base_dir: Path = field(default_factory=lambda: Path.cwd())
    videos_dir: Path = field(default_factory=lambda: Path("videos"))
    temp_dir: Path = field(default_factory=lambda: Path("temp"))

    # FFmpeg設定
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None

    # WhisperX設定
    whisper_model_size: str = "large-v2"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "float32"
    whisper_language: str = "ja"

    # 無音検出設定
    silence_threshold: float = -35.0
    min_silence_duration: float = 0.3
    min_segment_duration: float = 0.3

    # エクスポート設定
    fcpxml_fps: float = 29.97
    edl_fps: float = 29.97
    srt_max_line_length: int = 40
    srt_max_lines: int = 2

    # パフォーマンス設定
    max_workers: int = 4
    chunk_size: int = 1024 * 1024  # 1MB

    # セッションキー
    session_keys: SessionKeys = field(default_factory=SessionKeys)

    def __post_init__(self):
        """設定の検証と初期化"""
        # ディレクトリの作成
        self.videos_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)

        # 相対パスを絶対パスに変換
        if not self.videos_dir.is_absolute():
            self.videos_dir = self.base_dir / self.videos_dir
        if not self.temp_dir.is_absolute():
            self.temp_dir = self.base_dir / self.temp_dir

    def to_legacy_config(self) -> dict[str, Any]:
        """
        既存コードとの互換性のための変換

        Returns:
            レガシーConfig形式の辞書
        """
        return {
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
            "model_size": self.whisper_model_size,
            "device": self.whisper_device,
            "compute_type": self.whisper_compute_type,
            "language": self.whisper_language,
            "silence_threshold": self.silence_threshold,
            "min_silence_duration": self.min_silence_duration,
            "min_segment_duration": self.min_segment_duration,
            "fps": self.fcpxml_fps,
            "srt_max_line_length": self.srt_max_line_length,
            "srt_max_lines": self.srt_max_lines,
        }
