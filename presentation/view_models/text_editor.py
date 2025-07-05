"""
テキスト編集のViewModel

テキスト編集画面の状態管理を行います。
"""

from dataclasses import dataclass, field
from typing import Any

from domain.entities import TranscriptionResult
from presentation.view_models.base import BaseViewModel


@dataclass
class TimeRange:
    """時間範囲"""

    start: float
    end: float
    duration: float
    text: str


@dataclass
class TextEditorViewModel(BaseViewModel):
    """
    テキスト編集のViewModel

    編集テキスト、差分情報、時間計算結果などを管理します。
    """

    # 入力データ
    transcription_result: TranscriptionResult | None = None
    full_text: str = ""

    # 編集状態
    edited_text: str = ""
    previous_edited_text: str = ""
    is_editing: bool = False

    # 境界調整マーカー
    has_boundary_markers: bool = False
    cleaned_text: str = ""

    # セクション分割
    separator: str | None = None
    sections: list[str] = field(default_factory=list)

    # 時間範囲
    time_ranges: list[TimeRange] = field(default_factory=list)
    total_duration: float = 0.0

    # 表示用情報
    char_count: int = 0
    section_count: int = 0
    duration_text: str = ""

    # 差分情報（ハイライト表示用）
    differences: Any | None = None

    # エラー状態
    error_message: str | None = None

    # UI表示制御（タイムライン編集機能は削除）

    def __post_init__(self):
        """初期化後の処理"""
        # BaseViewModelにはpost_initがないため、直接初期化処理を行う
        pass

    def update_edited_text(self, text: str) -> None:
        """
        編集テキストを更新

        Args:
            text: 新しいテキスト
        """
        self.previous_edited_text = self.edited_text
        self.edited_text = text
        self.is_editing = True

        # 境界調整マーカーのチェック
        self.has_boundary_markers = any(marker in text for marker in ["[<", "[>", "<]", ">]"])

        # 文字数更新
        self.char_count = len(text)

        self.notify()

    def update_time_ranges(self, time_ranges: list[TimeRange]) -> None:
        """
        時間範囲を更新

        Args:
            time_ranges: 新しい時間範囲リスト
        """
        self.time_ranges = time_ranges

        # 合計時間を計算
        self.total_duration = sum(tr.duration for tr in time_ranges)

        # 時間表示を更新
        from utils.time_utils import format_time

        self.duration_text = format_time(self.total_duration)

        self.notify()

    def update_sections(self, sections: list[str], separator: str) -> None:
        """
        セクション情報を更新

        Args:
            sections: セクションリスト
            separator: 区切り文字
        """
        self.sections = sections
        self.separator = separator
        self.section_count = len(sections)
        self.notify()

    def clear_error(self) -> None:
        """エラーをクリア"""
        self.error_message = None
        self.notify()

    def set_error(self, message: str) -> None:
        """
        エラーメッセージを設定

        Args:
            message: エラーメッセージ
        """
        self.error_message = message
        self.notify()

    def reset(self) -> None:
        """状態をリセット"""
        self.edited_text = ""
        self.previous_edited_text = ""
        self.is_editing = False
        self.has_boundary_markers = False
        self.cleaned_text = ""
        self.separator = None
        self.sections = []
        self.time_ranges = []
        self.total_duration = 0.0
        self.char_count = 0
        self.section_count = 0
        self.duration_text = ""
        self.differences = None
        self.error_message = None
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "edited_text": self.edited_text,
            "has_boundary_markers": self.has_boundary_markers,
            "separator": self.separator,
            "section_count": self.section_count,
            "total_duration": self.total_duration,
            "duration_text": self.duration_text,
            "char_count": self.char_count,
            "error_message": self.error_message,
        }

    def validate(self) -> bool:
        """
        ViewModelの検証

        Returns:
            検証結果
        """
        if not self.transcription_result:
            self.set_error("文字起こし結果がありません")
            return False

        if not self.edited_text.strip():
            self.set_error("切り抜き箇所を入力してください")
            return False

        self.clear_error()
        return True

    @property
    def is_ready(self) -> bool:
        """処理実行可能かどうか"""
        return bool(self.transcription_result and self.edited_text.strip() and not self.error_message)

    @property
    def has_separator(self) -> bool:
        """区切り文字があるかどうか"""
        return self.separator is not None

    @property
    def has_time_ranges(self) -> bool:
        """時間範囲が計算されているかどうか"""
        return len(self.time_ranges) > 0
    
    @property
    def has_edited_text(self) -> bool:
        """編集されたテキストが存在するかどうか"""
        return bool(self.edited_text.strip() and self.has_time_ranges)
