"""
メイン画面のViewModel

アプリケーション全体の状態管理を担当します。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from presentation.view_models.base import BaseViewModel


@dataclass
class MainViewModel(BaseViewModel):
    """
    メイン画面のViewModel

    アプリケーション全体の状態とワークフローを管理します。
    """

    # 基本状態
    is_initialized: bool = False
    current_step: str = "video_input"  # video_input, transcription, text_edit, export

    # 各ステップの完了状態
    video_input_completed: bool = False
    transcription_completed: bool = False
    text_edit_completed: bool = False
    export_completed: bool = False

    # 共有データ
    video_path: Path | None = None
    video_duration: float = 0.0

    # エラー状態
    has_error: bool = False
    error_message: str | None = None
    error_context: str | None = None

    # UI制御
    show_help: bool = False
    show_settings: bool = False
    dark_mode: bool = False

    @property
    def can_proceed_to_transcription(self) -> bool:
        """文字起こしステップに進めるか"""
        return self.video_input_completed and self.video_path is not None

    @property
    def can_proceed_to_text_edit(self) -> bool:
        """テキスト編集ステップに進めるか"""
        return self.transcription_completed

    @property
    def can_proceed_to_export(self) -> bool:
        """エクスポートステップに進めるか"""
        return self.text_edit_completed

    @property
    def workflow_progress(self) -> float:
        """ワークフローの進捗率（0.0-1.0）"""
        steps_completed = sum(
            [self.video_input_completed, self.transcription_completed, self.text_edit_completed, self.export_completed]
        )
        return steps_completed / 4.0

    def set_current_step(self, step: str) -> None:
        """現在のステップを設定"""
        valid_steps = ["video_input", "transcription", "text_edit", "export"]
        if step in valid_steps:
            self.current_step = step
            self.notify()

    def complete_video_input(self, video_path: Path, duration: float) -> None:
        """動画入力完了"""
        self.video_path = video_path
        self.video_duration = duration
        self.video_input_completed = True
        self.current_step = "transcription"  # 自動的に文字起こし画面へ
        self.notify()

    def complete_transcription(self) -> None:
        """文字起こし完了"""
        self.transcription_completed = True
        self.current_step = "text_edit"  # 自動的にテキスト編集画面へ
        self.notify()

    def complete_text_edit(self) -> None:
        """テキスト編集完了"""
        self.text_edit_completed = True
        self.current_step = "export"
        self.notify()

    def complete_export(self) -> None:
        """エクスポート完了"""
        self.export_completed = True
        self.notify()

    def reset_workflow(self) -> None:
        """ワークフローをリセット"""
        self.current_step = "video_input"
        self.video_input_completed = False
        self.transcription_completed = False
        self.text_edit_completed = False
        self.export_completed = False
        self.video_path = None
        self.video_duration = 0.0
        self.clear_error()
        self.notify()

    def set_error(self, message: str, context: str | None = None) -> None:
        """エラーを設定"""
        self.has_error = True
        self.error_message = message
        self.error_context = context
        self.notify()

    def clear_error(self) -> None:
        """エラーをクリア"""
        self.has_error = False
        self.error_message = None
        self.error_context = None
        self.notify()

    def toggle_help(self) -> None:
        """ヘルプ表示を切り替え"""
        self.show_help = not self.show_help
        self.notify()

    def toggle_settings(self) -> None:
        """設定表示を切り替え"""
        self.show_settings = not self.show_settings
        self.notify()

    def set_dark_mode(self, enabled: bool) -> None:
        """ダークモードを設定"""
        self.dark_mode = enabled
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "is_initialized": self.is_initialized,
            "current_step": self.current_step,
            "video_input_completed": self.video_input_completed,
            "transcription_completed": self.transcription_completed,
            "text_edit_completed": self.text_edit_completed,
            "export_completed": self.export_completed,
            "video_path": str(self.video_path) if self.video_path else None,
            "video_duration": self.video_duration,
            "workflow_progress": self.workflow_progress,
            "has_error": self.has_error,
            "error_message": self.error_message,
        }

    def validate(self) -> str | None:
        """ViewModelの妥当性を検証"""
        # 基本的な整合性チェック
        if self.text_edit_completed and not self.transcription_completed:
            return "テキスト編集が完了していますが、文字起こしが完了していません"

        if self.export_completed and not self.text_edit_completed:
            return "エクスポートが完了していますが、テキスト編集が完了していません"

        if self.transcription_completed and not self.video_input_completed:
            return "文字起こしが完了していますが、動画入力が完了していません"

        return None
