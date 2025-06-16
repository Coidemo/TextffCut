"""
タイムライン編集機能のデータ構造とロジック
"""
from dataclasses import dataclass
from typing import List, Tuple, Optional
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimelineSegment:
    """タイムラインセグメント
    
    各セグメントの情報と、前後のギャップ調整値を保持する
    """
    index: int                  # セグメントのインデックス（0開始）
    start_time: float          # 元の開始時間
    end_time: float            # 元の終了時間
    gap_before: float = 0.0    # 前のセグメントとのギャップ（秒）
    gap_after: float = 0.0     # 次のセグメントとのギャップ（秒）
    enabled: bool = True       # このセグメントを含めるかどうか
    
    @property
    def duration(self) -> float:
        """セグメントの長さ（秒）"""
        return self.end_time - self.start_time
    
    def get_adjusted_range(self, prev_segment: Optional['TimelineSegment'] = None, 
                          next_segment: Optional['TimelineSegment'] = None) -> Tuple[float, float]:
        """ギャップ調整後の時間範囲を取得
        
        Args:
            prev_segment: 前のセグメント（重複チェック用）
            next_segment: 次のセグメント（重複チェック用）
            
        Returns:
            (adjusted_start, adjusted_end)
        """
        # 基本の時間範囲
        adjusted_start = self.start_time
        adjusted_end = self.end_time
        
        # 無効な時間範囲のチェック
        if adjusted_start >= adjusted_end:
            logger.warning(f"セグメント{self.index}の時間範囲が無効です: {adjusted_start} >= {adjusted_end}")
            return adjusted_start, adjusted_end
        
        # 前のセグメントとのギャップを適用
        if self.gap_before > 0:
            # 前のセグメントとの間から追加で取得
            adjusted_start = max(0, self.start_time - self.gap_before)
            
            # 前のセグメントとの重複を防ぐ
            if prev_segment:
                # 前のセグメントの終了時刻（ギャップ調整後）より後にする
                prev_end_adjusted = prev_segment.end_time + prev_segment.gap_after
                if adjusted_start < prev_end_adjusted:
                    adjusted_start = prev_end_adjusted
                    logger.warning(f"セグメント{self.index}の開始時刻を調整: {self.start_time - self.gap_before:.2f} -> {adjusted_start:.2f} (重複回避)")
        
        # 次のセグメントとのギャップを適用
        if self.gap_after > 0:
            # 次のセグメントとの間まで追加で取得
            adjusted_end = self.end_time + self.gap_after
            
            # 次のセグメントとの重複を防ぐ
            if next_segment:
                # 次のセグメントの開始時刻（ギャップ調整後）より前にする
                next_start_adjusted = next_segment.start_time - next_segment.gap_before
                if adjusted_end > next_start_adjusted:
                    adjusted_end = next_start_adjusted
                    logger.warning(f"セグメント{self.index}の終了時刻を調整: {self.end_time + self.gap_after:.2f} -> {adjusted_end:.2f} (重複回避)")
        
        return adjusted_start, adjusted_end


class Timeline:
    """タイムライン全体を管理するクラス"""
    
    def __init__(self, time_ranges: List[Tuple[float, float]]):
        """
        Args:
            time_ranges: 元の時間範囲のリスト [(start, end), ...]
        """
        self.segments: List[TimelineSegment] = []
        
        # 時間範囲からセグメントを作成
        for i, (start, end) in enumerate(time_ranges):
            segment = TimelineSegment(
                index=i,
                start_time=start,
                end_time=end
            )
            self.segments.append(segment)
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """ギャップ調整後の時間範囲リストを取得
        
        Returns:
            [(adjusted_start, adjusted_end), ...] 有効なセグメントのみ
        """
        adjusted_ranges = []
        
        for i, segment in enumerate(self.segments):
            if not segment.enabled:
                continue
            
            # 前後のセグメントを取得（有効なもののみ）
            prev_segment = None
            next_segment = None
            
            # 前の有効なセグメントを探す
            for j in range(i - 1, -1, -1):
                if self.segments[j].enabled:
                    prev_segment = self.segments[j]
                    break
            
            # 次の有効なセグメントを探す
            for j in range(i + 1, len(self.segments)):
                if self.segments[j].enabled:
                    next_segment = self.segments[j]
                    break
            
            # 調整後の範囲を取得
            adjusted_range = segment.get_adjusted_range(prev_segment, next_segment)
            adjusted_ranges.append(adjusted_range)
        
        return adjusted_ranges
    
    def set_all_gaps(self, gap_value: float):
        """全セグメントのギャップを一括設定
        
        Args:
            gap_value: 設定するギャップ値（秒）
        """
        for segment in self.segments:
            segment.gap_before = gap_value
            segment.gap_after = gap_value
    
    def reset_all_gaps(self):
        """全セグメントのギャップをリセット"""
        self.set_all_gaps(0.0)
    
    def get_total_duration(self) -> float:
        """有効なセグメントの合計時間を取得（ギャップ調整後）"""
        total = 0.0
        adjusted_ranges = self.get_adjusted_ranges()
        
        for start, end in adjusted_ranges:
            total += (end - start)
        
        return total
    
    def get_enabled_count(self) -> int:
        """有効なセグメントの数を取得"""
        return sum(1 for segment in self.segments if segment.enabled)