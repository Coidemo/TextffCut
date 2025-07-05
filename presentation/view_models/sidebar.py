"""
サイドバーのViewModel

サイドバーの状態管理を担当します。
"""

from dataclasses import dataclass, field
from typing import Any

from presentation.view_models.base import BaseViewModel


@dataclass
class SidebarViewModel(BaseViewModel):
    """
    サイドバーのViewModel

    リカバリー、プロセス、設定などサイドバーの状態を管理します。
    """

    # リカバリー状態
    recovery_available: bool = False
    recovery_items: list[dict[str, Any]] = field(default_factory=list)
    recovery_timestamp: str | None = None

    # プロセス管理
    process_status: str = "ready"  # ready, running, stopped
    process_message: str = ""
    process_details: list[str] = field(default_factory=list)

    # 設定 - 無音検出
    remove_silence_enabled: bool = False
    silence_threshold: float = -35.0
    min_silence_duration: float = 0.3
    min_segment_duration: float = 0.3
    silence_pad_start: float = 0.1
    silence_pad_end: float = 0.1

    # 設定 - API
    use_api: bool = False
    api_key: str | None = None
    api_model: str = "whisper-1"

    # 設定 - 高度な設定
    show_advanced_settings: bool = False
    model_size: str = "medium"
    audio_language: str = "ja"
    whisper_compute_type: str = "float16"
    whisper_device: str = "cuda"

    # UI状態
    show_help_dialog: bool = False
    show_settings_dialog: bool = False
    show_recovery_dialog: bool = False
    show_process_dialog: bool = False

    # エラー状態
    has_error: bool = False
    error_message: str | None = None

    @property
    def is_running(self) -> bool:
        """プロセスが実行中かどうか"""
        return self.process_status == "running"

    @property
    def can_recover(self) -> bool:
        """リカバリー可能かどうか"""
        return self.recovery_available and len(self.recovery_items) > 0

    @property
    def api_configured(self) -> bool:
        """APIが設定されているかどうか"""
        return self.use_api and bool(self.api_key)

    def update_recovery_state(self, items: list[dict[str, Any]], timestamp: str | None = None) -> None:
        """リカバリー状態を更新"""
        self.recovery_items = items
        self.recovery_available = len(items) > 0
        self.recovery_timestamp = timestamp
        self.notify()

    def update_process_status(self, status: str, message: str = "", details: list[str] = None) -> None:
        """プロセス状態を更新"""
        self.process_status = status
        self.process_message = message
        self.process_details = details or []
        self.notify()

    def update_silence_settings(
        self,
        enabled: bool,
        threshold: float = -35.0,
        min_duration: float = 0.3,
        pad_start: float = 0.3,
        pad_end: float = 0.3,
    ) -> None:
        """無音検出設定を更新"""
        self.remove_silence_enabled = enabled
        self.silence_threshold = threshold
        self.min_silence_duration = min_duration
        self.silence_pad_start = pad_start
        self.silence_pad_end = pad_end
        self.notify()

    def update_api_settings(self, use_api: bool, api_key: str | None = None, model: str = "whisper-1") -> None:
        """API設定を更新"""
        self.use_api = use_api
        if api_key is not None:
            self.api_key = api_key
        self.api_model = model
        self.notify()

    def update_advanced_settings(
        self, model_size: str = "medium", language: str = "ja", compute_type: str = "float16", device: str = "cuda"
    ) -> None:
        """高度な設定を更新"""
        self.model_size = model_size
        self.audio_language = language
        self.whisper_compute_type = compute_type
        self.whisper_device = device
        self.notify()

    def toggle_help_dialog(self) -> None:
        """ヘルプダイアログの表示を切り替え"""
        self.show_help_dialog = not self.show_help_dialog
        self.notify()

    def toggle_settings_dialog(self) -> None:
        """設定ダイアログの表示を切り替え"""
        self.show_settings_dialog = not self.show_settings_dialog
        self.notify()

    def toggle_recovery_dialog(self) -> None:
        """リカバリーダイアログの表示を切り替え"""
        self.show_recovery_dialog = not self.show_recovery_dialog
        self.notify()

    def toggle_process_dialog(self) -> None:
        """プロセスダイアログの表示を切り替え"""
        self.show_process_dialog = not self.show_process_dialog
        self.notify()

    def toggle_advanced_settings(self) -> None:
        """高度な設定の表示を切り替え"""
        self.show_advanced_settings = not self.show_advanced_settings
        self.notify()

    def set_error(self, message: str) -> None:
        """エラーを設定"""
        self.has_error = True
        self.error_message = message
        self.notify()

    def clear_error(self) -> None:
        """エラーをクリア"""
        self.has_error = False
        self.error_message = None
        self.notify()

    def reset(self) -> None:
        """状態をリセット"""
        self.recovery_available = False
        self.recovery_items.clear()
        self.recovery_timestamp = None
        self.process_status = "ready"
        self.process_message = ""
        self.process_details.clear()
        self.clear_error()
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "recovery_available": self.recovery_available,
            "recovery_items_count": len(self.recovery_items),
            "process_status": self.process_status,
            "remove_silence_enabled": self.remove_silence_enabled,
            "silence_threshold": self.silence_threshold,
            "use_api": self.use_api,
            "api_configured": self.api_configured,
            "model_size": self.model_size,
            "show_advanced_settings": self.show_advanced_settings,
        }

    def validate(self) -> str | None:
        """ViewModelの妥当性を検証"""
        # 無音検出設定の検証
        if self.remove_silence_enabled:
            if not (-60 <= self.silence_threshold <= 0):
                return "無音閾値は-60dBから0dBの間である必要があります"
            if self.min_silence_duration <= 0:
                return "最小無音時間は0より大きい必要があります"
            if self.silence_pad_start < 0 or self.silence_pad_end < 0:
                return "パディング値は0以上である必要があります"

        # API設定の検証
        if self.use_api and not self.api_key:
            return "APIキーが設定されていません"

        return None
