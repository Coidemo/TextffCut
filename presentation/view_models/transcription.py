"""
文字起こしのViewModel

文字起こし機能の状態管理を担当します。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from presentation.view_models.base import BaseViewModel


@dataclass
class TranscriptionCache:
    """文字起こしキャッシュ情報"""

    file_path: Path
    mode: str  # "local" or "api"
    model_size: str
    modified_time: float
    is_api: bool
    actual_filename: str | None = None  # 実際のファイル名（拡張子なし）


@dataclass
class TranscriptionViewModel(BaseViewModel):
    """
    文字起こしのViewModel

    文字起こし処理の状態とUIデータを管理します。
    """

    # キャッシュ関連
    available_caches: list[TranscriptionCache] = field(default_factory=list)
    selected_cache: TranscriptionCache | None = None
    use_cache: bool = False

    # 処理モード
    use_api: bool = False
    api_key: str | None = None
    model_size: str = "medium"  # ローカルモデルサイズ

    # 動画情報
    video_path: Path | None = None
    video_duration_minutes: float = 0.0
    video_duration_text: str = ""

    # 料金情報（APIモード時）
    estimated_cost_usd: float = 0.0
    estimated_cost_jpy: float = 0.0

    # 処理状態
    is_processing: bool = False
    should_run: bool = False
    is_cancelled: bool = False
    progress: float = 0.0
    status_message: str = ""

    # 結果
    transcription_result: Any | None = None  # TranscriptionResult型

    # エラー
    error_message: str | None = None
    error_details: dict[str, Any] | None = None

    @property
    def is_ready_to_run(self) -> bool:
        """実行可能な状態かどうか"""
        if self.use_api:
            return bool(self.video_path and self.api_key)
        return bool(self.video_path)

    @property
    def has_result(self) -> bool:
        """文字起こし結果があるかどうか"""
        return self.transcription_result is not None

    @property
    def mode_text(self) -> str:
        """現在のモードのテキスト表現"""
        return "API" if self.use_api else "ローカル"

    @property
    def model_text(self) -> str:
        """現在のモデルのテキスト表現"""
        if self.use_api:
            return "whisper-1"
        return self.model_size

    @property
    def cost_text(self) -> str:
        """料金のテキスト表現"""
        if self.use_api:
            return f"${self.estimated_cost_usd:.3f} (約{self.estimated_cost_jpy:.0f}円)"
        return "無料（ローカル処理）"

    def reset_processing_state(self) -> None:
        """処理状態をリセット"""
        self.is_processing = False
        self.should_run = False
        self.is_cancelled = False
        self.progress = 0.0
        self.status_message = ""
        self.error_message = None
        self.error_details = None
        self.notify()

    def start_processing(self) -> None:
        """処理を開始"""
        self.is_processing = True
        self.is_cancelled = False
        self.progress = 0.0
        self.status_message = "文字起こしを開始しています..."
        self.notify()

    def update_progress(self, progress: float, status: str) -> None:
        """進捗を更新"""
        self.progress = min(progress, 1.0)
        self.status_message = status
        self.notify()

    def cancel_processing(self) -> None:
        """処理をキャンセル"""
        self.is_cancelled = True
        self.status_message = "処理をキャンセルしています..."
        self.notify()

    def complete_processing(self, result: Any) -> None:
        """処理を完了"""
        self.transcription_result = result
        self.is_processing = False
        self.progress = 1.0
        self.status_message = "文字起こしが完了しました"
        self.notify()

    def set_error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """エラーを設定"""
        self.error_message = message
        self.error_details = details
        self.is_processing = False
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "available_caches": [
                {
                    "file_path": str(cache.file_path),
                    "mode": cache.mode,
                    "model_size": cache.model_size,
                    "modified_time": cache.modified_time,
                    "is_api": cache.is_api,
                }
                for cache in self.available_caches
            ],
            "selected_cache": (
                {
                    "file_path": str(self.selected_cache.file_path),
                    "mode": self.selected_cache.mode,
                    "model_size": self.selected_cache.model_size,
                    "modified_time": self.selected_cache.modified_time,
                    "is_api": self.selected_cache.is_api,
                    "actual_filename": self.selected_cache.actual_filename,
                }
                if self.selected_cache
                else None
            ),
            "use_cache": self.use_cache,
            "use_api": self.use_api,
            "api_key": self.api_key,
            "model_size": self.model_size,
            "video_path": str(self.video_path) if self.video_path else None,
            "video_duration_minutes": self.video_duration_minutes,
            "video_duration_text": self.video_duration_text,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_cost_jpy": self.estimated_cost_jpy,
            "is_processing": self.is_processing,
            "should_run": self.should_run,
            "is_cancelled": self.is_cancelled,
            "progress": self.progress,
            "status_message": self.status_message,
            "has_result": self.has_result,
            "error_message": self.error_message,
            "error_details": self.error_details,
        }

    def validate(self) -> bool:
        """検証"""
        # 基本的な検証
        if self.use_api and not self.api_key:
            return False

        if self.progress < 0 or self.progress > 1:
            return False

        return True
