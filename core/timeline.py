"""
タイムライン管理モジュール
動画セグメント間のギャップ調整機能を提供
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from copy import deepcopy


@dataclass
class TimelineSegment:
    """タイムラインセグメント
    
    元の時間範囲と調整後の時間範囲を管理
    """
    index: int
    original_start: float
    original_end: float
    gap_before: float = 0.0  # 前のセグメントとの間に追加する時間（秒）
    gap_after: float = 0.0   # 次のセグメントとの間に追加する時間（秒）
    enabled: bool = True     # セグメントの有効/無効
    
    @property
    def duration(self) -> float:
        """セグメントの長さ"""
        return self.original_end - self.original_start
    
    def get_adjusted_range(self, video_duration: float, prev_segment: Optional['TimelineSegment'] = None, next_segment: Optional['TimelineSegment'] = None) -> Tuple[float, float]:
        """調整後の時間範囲を取得
        
        Args:
            video_duration: 元動画の長さ
            prev_segment: 前のセグメント
            next_segment: 次のセグメント
            
        Returns:
            (開始時刻, 終了時刻)
        """
        if not self.enabled:
            return (self.original_start, self.original_end)
        
        # ギャップを考慮した開始・終了時刻を計算
        adjusted_start = max(0, self.original_start - self.gap_before)
        adjusted_end = min(video_duration, self.original_end + self.gap_after)
        
        # 前のセグメントとの重複を防ぐ
        if prev_segment and prev_segment.enabled:
            prev_end = prev_segment.original_end + prev_segment.gap_after
            adjusted_start = max(adjusted_start, prev_end)
        
        # 次のセグメントとの重複を防ぐ
        if next_segment and next_segment.enabled:
            next_start = next_segment.original_start - next_segment.gap_before
            adjusted_end = min(adjusted_end, next_start)
        
        # 開始時刻が終了時刻を超えないように調整
        if adjusted_start >= adjusted_end:
            # 最小限の長さを確保
            adjusted_end = adjusted_start + 0.1
        
        return (adjusted_start, adjusted_end)


@dataclass
class Timeline:
    """タイムライン全体を管理"""
    segments: List[TimelineSegment] = field(default_factory=list)
    video_duration: float = 0.0
    
    @classmethod
    def from_time_ranges(cls, time_ranges: List[Tuple[float, float]], video_duration: float) -> 'Timeline':
        """時間範囲のリストからタイムラインを作成
        
        Args:
            time_ranges: [(開始時刻, 終了時刻), ...]のリスト
            video_duration: 元動画の長さ
            
        Returns:
            Timeline インスタンス
        """
        segments = []
        for i, (start, end) in enumerate(time_ranges):
            segment = TimelineSegment(
                index=i,
                original_start=start,
                original_end=end
            )
            segments.append(segment)
        
        return cls(segments=segments, video_duration=video_duration)
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """すべてのセグメントの調整後の時間範囲を取得
        
        Returns:
            [(開始時刻, 終了時刻), ...]のリスト
        """
        adjusted_ranges = []
        
        for i, segment in enumerate(self.segments):
            if not segment.enabled:
                continue
                
            prev_segment = self.segments[i-1] if i > 0 else None
            next_segment = self.segments[i+1] if i < len(self.segments) - 1 else None
            
            adjusted_range = segment.get_adjusted_range(
                self.video_duration,
                prev_segment,
                next_segment
            )
            adjusted_ranges.append(adjusted_range)
        
        return adjusted_ranges
    
    def set_gap(self, segment_index: int, gap_before: Optional[float] = None, gap_after: Optional[float] = None):
        """特定のセグメントのギャップを設定
        
        Args:
            segment_index: セグメントのインデックス
            gap_before: 前との間隔（Noneの場合は変更なし）
            gap_after: 後との間隔（Noneの場合は変更なし）
        """
        if 0 <= segment_index < len(self.segments):
            segment = self.segments[segment_index]
            if gap_before is not None:
                segment.gap_before = max(0, gap_before)
            if gap_after is not None:
                segment.gap_after = max(0, gap_after)
    
    def set_all_gaps(self, gap: float):
        """すべてのセグメントのギャップを一括設定
        
        Args:
            gap: 設定するギャップ（秒）
        """
        for segment in self.segments:
            segment.gap_before = max(0, gap)
            segment.gap_after = max(0, gap)
    
    def reset_gaps(self):
        """すべてのギャップをリセット"""
        for segment in self.segments:
            segment.gap_before = 0.0
            segment.gap_after = 0.0
    
    def toggle_segment(self, segment_index: int):
        """セグメントの有効/無効を切り替え
        
        Args:
            segment_index: セグメントのインデックス
        """
        if 0 <= segment_index < len(self.segments):
            self.segments[segment_index].enabled = not self.segments[segment_index].enabled
    
    def get_total_duration(self) -> float:
        """調整後の合計時間を取得"""
        adjusted_ranges = self.get_adjusted_ranges()
        return sum(end - start for start, end in adjusted_ranges)
    
    def clone(self) -> 'Timeline':
        """タイムラインのディープコピーを作成"""
        return deepcopy(self)