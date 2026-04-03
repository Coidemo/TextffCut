"""
タイムスタンプ付き文字情報エンティティ

文字起こしのwords配列から構築される、文字単位のタイムスタンプ情報を保持する。
日本語の場合、各wordは1文字に対応する。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CharacterWithTimestamp:
    """
    タイムスタンプ付き文字情報

    Attributes:
        char: 文字（1文字）
        start: 開始時間（秒）
        end: 終了時間（秒）
        segment_id: 所属セグメントID
        word_index: 元のwords配列でのインデックス
        original_position: 元のテキストでの文字位置
        confidence: 認識信頼度（0.0-1.0）
    """

    char: str
    start: float
    end: float
    segment_id: str
    word_index: int
    original_position: int
    confidence: float = 1.0

    def __post_init__(self):
        """バリデーション"""
        if len(self.char) != 1:
            raise ValueError(f"charは1文字である必要があります: '{self.char}'")
        if self.start < 0 or self.end < 0:
            raise ValueError(f"時間は正の値である必要があります: start={self.start}, end={self.end}")
        if self.start > self.end:
            raise ValueError(f"開始時間は終了時間より前である必要があります: start={self.start}, end={self.end}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"信頼度は0.0-1.0の範囲である必要があります: {self.confidence}")

    @property
    def duration(self) -> float:
        """文字の継続時間（秒）"""
        return self.end - self.start

    def overlaps_with(self, other: "CharacterWithTimestamp") -> bool:
        """他の文字と時間的に重なっているか"""
        return not (self.end <= other.start or other.end <= self.start)
