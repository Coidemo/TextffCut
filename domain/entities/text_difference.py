"""
テキスト差分のドメインエンティティ

編集前後のテキストの差分を表すエンティティ。
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum
from uuid import uuid4


class DifferenceType(Enum):
    """差分の種類"""
    ADDED = "added"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


@dataclass
class TextDifference:
    """テキスト差分エンティティ"""
    id: str
    original_text: str
    edited_text: str
    differences: List[Tuple[DifferenceType, str, Optional[Tuple[float, float]]]]
    
    def __post_init__(self):
        """バリデーション"""
        if not self.original_text and not self.edited_text:
            raise ValueError("Both original and edited text cannot be empty")
    
    @property
    def has_changes(self) -> bool:
        """変更があるかどうか"""
        return any(diff[0] != DifferenceType.UNCHANGED for diff in self.differences)
    
    @property
    def added_count(self) -> int:
        """追加された部分の数"""
        return sum(1 for diff in self.differences if diff[0] == DifferenceType.ADDED)
    
    @property
    def deleted_count(self) -> int:
        """削除された部分の数"""
        return sum(1 for diff in self.differences if diff[0] == DifferenceType.DELETED)
    
    @property
    def unchanged_count(self) -> int:
        """変更されていない部分の数"""
        return sum(1 for diff in self.differences if diff[0] == DifferenceType.UNCHANGED)
    
    def get_time_ranges_for_unchanged(self) -> List[Tuple[float, float]]:
        """変更されていない部分の時間範囲を取得"""
        ranges = []
        for diff_type, _, time_range in self.differences:
            if diff_type == DifferenceType.UNCHANGED and time_range:
                ranges.append(time_range)
        return ranges
    
    def get_time_ranges_for_deleted(self) -> List[Tuple[float, float]]:
        """削除された部分の時間範囲を取得"""
        ranges = []
        for diff_type, _, time_range in self.differences:
            if diff_type == DifferenceType.DELETED and time_range:
                ranges.append(time_range)
        return ranges
    
    def get_summary(self) -> str:
        """差分のサマリーを生成"""
        if not self.has_changes:
            return "No changes detected"
        
        parts = []
        if self.added_count > 0:
            parts.append(f"{self.added_count} additions")
        if self.deleted_count > 0:
            parts.append(f"{self.deleted_count} deletions")
        if self.unchanged_count > 0:
            parts.append(f"{self.unchanged_count} unchanged")
        
        return ", ".join(parts)
    
    @classmethod
    def from_text_comparison(
        cls,
        original_text: str,
        edited_text: str,
        word_timestamps: Optional[List[dict]] = None
    ) -> "TextDifference":
        """テキスト比較から差分エンティティを作成"""
        # この実装は仮のもの。実際の差分検出ロジックはuse caseやserviceで実装
        differences = []
        
        if original_text == edited_text:
            differences.append((DifferenceType.UNCHANGED, original_text, None))
        else:
            # 簡単な実装：全体を変更として扱う
            if original_text:
                differences.append((DifferenceType.DELETED, original_text, None))
            if edited_text:
                differences.append((DifferenceType.ADDED, edited_text, None))
        
        return cls(
            id=str(uuid4()),
            original_text=original_text,
            edited_text=edited_text,
            differences=differences
        )