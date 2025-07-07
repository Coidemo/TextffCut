"""
エクスポート設定のViewModel

エクスポート機能の状態管理を担当します。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from domain.value_objects.time_range import TimeRange
from presentation.view_models.base import BaseViewModel


@dataclass
class ExportSettingsViewModel(BaseViewModel):
    """
    エクスポート設定のViewModel

    エクスポート処理の状態とUIデータを管理します。
    """

    # 入力データ
    video_path: Path | None = None
    transcription_result: Any | None = None
    edited_text: str | None = None
    time_ranges: list[TimeRange] | None = None
    adjusted_time_ranges: list[TimeRange] | None = None

    # 無音削除設定
    remove_silence: bool = True  # デフォルトは無音削除付き
    silence_threshold: float = -35.0
    min_silence_duration: float = 0.3
    silence_pad_start: float = 0.1
    silence_pad_end: float = 0.1

    # エクスポート形式
    export_format: str = "fcpxml"  # video, fcpxml, edl, srt
    include_srt: bool = True  # デフォルトはSRT同時出力
    srt_max_line_length: int = 40
    srt_max_lines: int = 2

    # 処理状態
    is_processing: bool = False
    should_run: bool = False
    progress: float = 0.0
    status_message: str = ""
    current_operation: str = ""

    # 結果
    export_results: list[str] = field(default_factory=list)
    error_message: str | None = None
    error_details: dict[str, Any] | None = None

    @property
    def is_ready_to_export(self) -> bool:
        """エクスポート可能な状態かどうか"""
        return bool(self.video_path and self.edited_text and self.time_ranges and not self.is_processing)

    @property
    def has_adjusted_ranges(self) -> bool:
        """調整済み時間範囲があるかどうか"""
        return self.adjusted_time_ranges is not None and len(self.adjusted_time_ranges) > 0

    @property
    def effective_time_ranges(self) -> list[TimeRange] | None:
        """実際に使用する時間範囲（調整済みがあれば優先）"""
        if self.has_adjusted_ranges:
            return self.adjusted_time_ranges
        return self.time_ranges

    @property
    def export_format_name(self) -> str:
        """エクスポート形式の表示名"""
        format_names = {
            "video": "動画（MP4）",
            "fcpxml": "Final Cut Pro XML",
            "edl": "EDL (DaVinci Resolve)",
            "srt": "SRT字幕のみ",
        }
        return format_names.get(self.export_format, self.export_format)

    def start_processing(self) -> None:
        """処理開始"""
        self.is_processing = True
        self.progress = 0.0
        self.status_message = "処理を開始しています..."
        self.export_results.clear()
        self.error_message = None
        self.error_details = None
        self.notify()

    def update_progress(self, progress: float, message: str, operation: str = "") -> None:
        """進捗更新"""
        self.progress = max(0.0, min(1.0, progress))
        self.status_message = message
        self.current_operation = operation
        self.notify()

    def complete_processing(self, results: list[str]) -> None:
        """処理完了"""
        self.is_processing = False
        self.progress = 1.0
        self.status_message = "エクスポート完了！"
        self.export_results = results
        self.notify()

    def set_error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """エラー設定"""
        self.is_processing = False
        self.error_message = message
        self.error_details = details
        self.notify()

    def reset_processing_state(self) -> None:
        """処理状態をリセット"""
        self.is_processing = False
        self.progress = 0.0
        self.status_message = ""
        self.current_operation = ""
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "video_path": str(self.video_path) if self.video_path else None,
            "remove_silence": self.remove_silence,
            "silence_threshold": self.silence_threshold,
            "min_silence_duration": self.min_silence_duration,
            "silence_pad_start": self.silence_pad_start,
            "silence_pad_end": self.silence_pad_end,
            "export_format": self.export_format,
            "include_srt": self.include_srt,
            "srt_max_line_length": self.srt_max_line_length,
            "srt_max_lines": self.srt_max_lines,
            "is_processing": self.is_processing,
            "progress": self.progress,
            "status_message": self.status_message,
        }

    def validate(self) -> str | None:
        """ViewModelの妥当性を検証"""
        if self.is_processing:
            return None  # 処理中は常に有効

        if not self.video_path:
            return "動画パスが設定されていません"

        if not self.edited_text:
            return "編集されたテキストがありません"

        if not self.time_ranges:
            return "時間範囲が設定されていません"

        return None
