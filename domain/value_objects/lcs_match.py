"""
LCSマッチ情報の値オブジェクト

LCSアルゴリズムで検出された文字の一致情報を表現する。
"""

from dataclasses import dataclass
from typing import List, Optional

from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.entities.text_difference import DifferenceType


@dataclass(frozen=True)
class LCSMatch:
    """
    LCSマッチ情報

    Attributes:
        original_index: 元テキストでのインデックス
        edited_index: 編集テキストでのインデックス
        char: マッチした文字
        timestamp: タイムスタンプ情報
    """

    original_index: int
    edited_index: int
    char: str
    timestamp: CharacterWithTimestamp

    def __post_init__(self):
        """バリデーション"""
        if self.original_index < 0 or self.edited_index < 0:
            raise ValueError("インデックスは非負である必要があります")
        if self.char != self.timestamp.char:
            raise ValueError(f"文字が一致しません: '{self.char}' != '{self.timestamp.char}'")


@dataclass(frozen=True)
class DifferenceBlock:
    """
    差分ブロック（連続した同じ種類の差分）

    Attributes:
        type: 差分の種類（UNCHANGED, ADDED, DELETED）
        text: テキスト内容
        start_time: 開始時間（UNCHANGEDとDELETEDの場合）
        end_time: 終了時間（UNCHANGEDとDELETEDの場合）
        char_positions: 文字位置情報のリスト
        original_start_pos: 元テキストでの開始位置
        original_end_pos: 元テキストでの終了位置
    """

    type: DifferenceType
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    char_positions: List[CharacterWithTimestamp] = None
    original_start_pos: Optional[int] = None
    original_end_pos: Optional[int] = None

    def __post_init__(self):
        """バリデーションと初期化"""
        # char_positionsのデフォルト値設定
        if self.char_positions is None:
            object.__setattr__(self, "char_positions", [])

        # 時間情報の検証
        if self.type in (DifferenceType.UNCHANGED, DifferenceType.DELETED):
            if self.start_time is None or self.end_time is None:
                if self.char_positions:
                    # char_positionsから時間を計算
                    object.__setattr__(self, "start_time", self.char_positions[0].start)
                    object.__setattr__(self, "end_time", self.char_positions[-1].end)
            elif self.start_time > self.end_time:
                raise ValueError(f"開始時間は終了時間より前である必要があります: {self.start_time} > {self.end_time}")

    @property
    def duration(self) -> float:
        """ブロックの継続時間（秒）"""
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return 0.0

    @property
    def char_count(self) -> int:
        """ブロック内の文字数"""
        return len(self.text)

    def is_adjacent_to(self, other: "DifferenceBlock", gap_threshold: float = 0.1) -> bool:
        """他のブロックと隣接しているか（時間的に）"""
        if self.type != other.type:
            return False
        if self.end_time is None or other.start_time is None:
            return False
        # 隣接判定：このブロックの終了時間と次のブロックの開始時間の差が閾値以下
        gap = other.start_time - self.end_time
        return 0 <= gap <= gap_threshold
