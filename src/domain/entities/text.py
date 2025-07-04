"""
Text Entity

テキスト処理関連のエンティティ
"""

from dataclasses import dataclass

from ..value_objects import TimeRange


@dataclass
class TextDifference:
    """テキストの差分情報"""

    id: str
    time_range: TimeRange
    original_text: str
    edited_text: str
    operation: str  # "add", "delete", "modify"

    def __post_init__(self):
        """バリデーション"""
        valid_operations = {"add", "delete", "modify"}
        if self.operation not in valid_operations:
            raise ValueError(f"Invalid operation: {self.operation}. Must be one of {valid_operations}")

        # 操作タイプに応じた検証
        if self.operation == "add" and self.original_text:
            raise ValueError("Add operation should not have original_text")
        if self.operation == "delete" and self.edited_text:
            raise ValueError("Delete operation should not have edited_text")
        if self.operation == "modify" and (not self.original_text or not self.edited_text):
            raise ValueError("Modify operation must have both original_text and edited_text")

    @property
    def is_addition(self) -> bool:
        """追加操作かどうか"""
        return self.operation == "add"

    @property
    def is_deletion(self) -> bool:
        """削除操作かどうか"""
        return self.operation == "delete"

    @property
    def is_modification(self) -> bool:
        """変更操作かどうか"""
        return self.operation == "modify"

    @property
    def text_change(self) -> str:
        """テキストの変更内容を取得"""
        if self.is_addition:
            return f"+{self.edited_text}"
        elif self.is_deletion:
            return f"-{self.original_text}"
        else:  # modification
            return f"-{self.original_text}\n+{self.edited_text}"

    def get_display_text(self) -> str:
        """表示用のテキストを取得"""
        if self.is_addition:
            return self.edited_text
        elif self.is_deletion:
            return ""
        else:  # modification
            return self.edited_text
