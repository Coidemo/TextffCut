"""
タイムライン編集機能のデータ構造
"""
from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TimelineSegment:
    """タイムラインセグメント"""
    index: int
    start: float
    end: float
    gap_before: float = 0.0  # 前のセグメントからの追加余白（秒）
    gap_after: float = 0.0   # 次のセグメントへの追加余白（秒）
    enabled: bool = True
    
    @property
    def duration(self) -> float:
        """セグメントの長さ"""
        return self.end - self.start
    
    def get_adjusted_range(self, prev_end: Optional[float] = None, next_start: Optional[float] = None) -> Tuple[float, float]:
        """ギャップ調整後の時間範囲を取得
        
        Args:
            prev_end: 前のセグメントの終了時刻（重複防止用）
            next_start: 次のセグメントの開始時刻（重複防止用）
            
        Returns:
            調整後の(開始時刻, 終了時刻)
        """
        # ギャップを適用
        adjusted_start = max(0, self.start - self.gap_before)
        adjusted_end = self.end + self.gap_after
        
        # 前のセグメントとの重複を防ぐ
        if prev_end is not None and adjusted_start < prev_end:
            adjusted_start = prev_end
            logger.debug(f"セグメント{self.index}: 前のセグメントとの重複を回避 (start: {adjusted_start})")
        
        # 次のセグメントとの重複を防ぐ
        if next_start is not None and adjusted_end > next_start:
            adjusted_end = next_start
            logger.debug(f"セグメント{self.index}: 次のセグメントとの重複を回避 (end: {adjusted_end})")
        
        return adjusted_start, adjusted_end


class Timeline:
    """タイムライン管理クラス"""
    
    def __init__(self, time_ranges: List[Tuple[float, float]]):
        """
        Args:
            time_ranges: 元の時間範囲のリスト [(start, end), ...]
        """
        self.segments: List[TimelineSegment] = []
        
        # TimelineSegmentに変換
        for i, (start, end) in enumerate(time_ranges):
            segment = TimelineSegment(
                index=i,
                start=start,
                end=end
            )
            self.segments.append(segment)
    
    def get_segment_count(self) -> int:
        """有効なセグメント数を取得"""
        return sum(1 for seg in self.segments if seg.enabled)
    
    def get_total_duration(self) -> float:
        """調整前の合計時間を取得"""
        return sum(seg.duration for seg in self.segments if seg.enabled)
    
    def get_adjusted_duration(self) -> float:
        """ギャップ調整後の合計時間を取得"""
        adjusted_ranges = self.get_adjusted_ranges()
        return sum(end - start for start, end in adjusted_ranges)
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """ギャップ調整後の時間範囲リストを取得"""
        adjusted_ranges = []
        enabled_segments = [seg for seg in self.segments if seg.enabled]
        
        for i, segment in enumerate(enabled_segments):
            # 前後のセグメントの境界を取得
            prev_end = None
            next_start = None
            
            if i > 0:
                prev_seg = enabled_segments[i-1]
                _, prev_end = prev_seg.get_adjusted_range()
            
            if i < len(enabled_segments) - 1:
                next_seg = enabled_segments[i+1]
                next_start = next_seg.start
            
            # 調整後の範囲を取得
            adjusted_start, adjusted_end = segment.get_adjusted_range(prev_end, next_start)
            
            # 有効な範囲のみ追加
            if adjusted_start < adjusted_end:
                adjusted_ranges.append((adjusted_start, adjusted_end))
        
        return adjusted_ranges
    
    def set_all_gaps(self, gap_before: float = 0.0, gap_after: float = 0.0):
        """全セグメントのギャップを一括設定"""
        for segment in self.segments:
            segment.gap_before = gap_before
            segment.gap_after = gap_after
    
    def reset_all_gaps(self):
        """全セグメントのギャップをリセット"""
        self.set_all_gaps(0.0, 0.0)
    
    def validate_gaps(self) -> bool:
        """ギャップ設定の妥当性を検証"""
        enabled_segments = [seg for seg in self.segments if seg.enabled]
        
        for i, segment in enumerate(enabled_segments):
            # ギャップが負の値でないことを確認
            if segment.gap_before < 0 or segment.gap_after < 0:
                logger.warning(f"セグメント{segment.index}: 負のギャップ値が設定されています")
                return False
            
            # 前後のセグメントとの関係を確認
            if i > 0:
                prev_seg = enabled_segments[i-1]
                if (prev_seg.end + prev_seg.gap_after) > (segment.start - segment.gap_before):
                    logger.warning(f"セグメント{segment.index}: 前のセグメントと重複する可能性があります")
        
        return True