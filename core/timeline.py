from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import copy


@dataclass
class TimelineSegment:
    """タイムライン上の1つのセグメントを表すクラス"""
    index: int
    start_time: float
    end_time: float
    gap_before: float = 0.0  # 前のセグメントとのギャップ（秒）
    gap_after: float = 0.0   # 次のセグメントとのギャップ（秒）
    enabled: bool = True     # セグメントの有効/無効
    
    @property
    def duration(self) -> float:
        """セグメントの長さ（秒）"""
        return self.end_time - self.start_time
    
    def get_adjusted_range(self, prev_end: Optional[float] = None, next_start: Optional[float] = None) -> Tuple[float, float]:
        """
        ギャップを考慮した調整後の時間範囲を返す
        
        Args:
            prev_end: 前のセグメントの終了時刻（重複防止用）
            next_start: 次のセグメントの開始時刻（重複防止用）
            
        Returns:
            (調整後の開始時刻, 調整後の終了時刻)
        """
        # ギャップを考慮した開始・終了時刻
        adjusted_start = max(0, self.start_time - self.gap_before)
        adjusted_end = self.end_time + self.gap_after
        
        # 前のセグメントとの重複を防ぐ
        if prev_end is not None and adjusted_start < prev_end:
            adjusted_start = prev_end
            
        # 次のセグメントとの重複を防ぐ
        if next_start is not None and adjusted_end > next_start:
            adjusted_end = next_start
            
        return adjusted_start, adjusted_end


@dataclass
class Timeline:
    """複数のセグメントを管理するタイムラインクラス"""
    segments: List[TimelineSegment] = field(default_factory=list)
    
    def add_segment(self, start_time: float, end_time: float) -> TimelineSegment:
        """新しいセグメントを追加"""
        segment = TimelineSegment(
            index=len(self.segments),
            start_time=start_time,
            end_time=end_time
        )
        self.segments.append(segment)
        return segment
    
    def get_enabled_segments(self) -> List[TimelineSegment]:
        """有効なセグメントのみを返す"""
        return [seg for seg in self.segments if seg.enabled]
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """
        全セグメントの調整後の時間範囲を返す（重複防止付き）
        
        Returns:
            [(開始時刻, 終了時刻), ...]のリスト
        """
        enabled_segments = self.get_enabled_segments()
        if not enabled_segments:
            return []
        
        adjusted_ranges = []
        for i, segment in enumerate(enabled_segments):
            # 前後のセグメントの時刻を取得
            prev_end = adjusted_ranges[-1][1] if i > 0 else None
            next_start = enabled_segments[i + 1].start_time if i < len(enabled_segments) - 1 else None
            
            # 調整後の範囲を計算
            adjusted_range = segment.get_adjusted_range(prev_end, next_start)
            adjusted_ranges.append(adjusted_range)
            
        return adjusted_ranges
    
    def get_total_duration(self, adjusted: bool = True) -> float:
        """
        タイムラインの合計時間を返す
        
        Args:
            adjusted: True の場合はギャップ調整後の時間、False の場合は元の時間
        """
        if adjusted:
            ranges = self.get_adjusted_ranges()
            return sum(end - start for start, end in ranges)
        else:
            enabled_segments = self.get_enabled_segments()
            return sum(seg.duration for seg in enabled_segments)
    
    def set_all_gaps(self, gap_value: float):
        """全セグメントのギャップを一括設定"""
        for segment in self.segments:
            segment.gap_before = gap_value
            segment.gap_after = gap_value
    
    def reset_all_gaps(self):
        """全セグメントのギャップをリセット"""
        self.set_all_gaps(0.0)
    
    def copy(self) -> 'Timeline':
        """タイムラインのディープコピーを作成"""
        return Timeline(segments=[copy.deepcopy(seg) for seg in self.segments])
    
    @classmethod
    def from_time_ranges(cls, time_ranges: List[Tuple[float, float]]) -> 'Timeline':
        """時間範囲のリストからタイムラインを作成"""
        timeline = cls()
        for start, end in time_ranges:
            timeline.add_segment(start, end)
        return timeline