"""
タイムライン管理モジュール
動画セグメント間のギャップ調整機能を提供
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from copy import deepcopy


@dataclass
class TimelineSegment:
    """タイムラインの各セグメント情報"""
    index: int
    start_time: float
    end_time: float
    gap_before: float = 0.0  # 前のセグメントとの間隔（元動画から追加で含める秒数）
    gap_after: float = 0.0   # 次のセグメントとの間隔（元動画から追加で含める秒数）
    enabled: bool = True     # セグメントの有効/無効
    
    @property
    def duration(self) -> float:
        """セグメントの長さ"""
        return self.end_time - self.start_time
    
    def get_adjusted_range(self, prev_end: Optional[float] = None, next_start: Optional[float] = None) -> Tuple[float, float]:
        """ギャップを考慮した調整後の時間範囲を取得
        
        Args:
            prev_end: 前のセグメントの終了時刻（重複防止用）
            next_start: 次のセグメントの開始時刻（重複防止用）
            
        Returns:
            調整後の(開始時刻, 終了時刻)
        """
        # 基本の範囲
        adjusted_start = self.start_time - self.gap_before
        adjusted_end = self.end_time + self.gap_after
        
        # 前のセグメントとの重複を防ぐ
        if prev_end is not None and adjusted_start < prev_end:
            adjusted_start = prev_end
        
        # 次のセグメントとの重複を防ぐ
        if next_start is not None and adjusted_end > next_start:
            adjusted_end = next_start
        
        # 最小0に制限
        adjusted_start = max(0, adjusted_start)
        
        return adjusted_start, adjusted_end


@dataclass
class Timeline:
    """タイムライン全体を管理するクラス"""
    segments: List[TimelineSegment] = field(default_factory=list)
    video_duration: float = 0.0
    
    @classmethod
    def from_time_ranges(cls, time_ranges: List[Tuple[float, float]], video_duration: float = 0.0) -> 'Timeline':
        """時間範囲のリストからTimelineを作成
        
        Args:
            time_ranges: [(start, end), ...] の形式の時間範囲リスト
            video_duration: 動画の総時間（制限用）
            
        Returns:
            Timeline インスタンス
        """
        segments = []
        for i, (start, end) in enumerate(time_ranges):
            segments.append(TimelineSegment(
                index=i,
                start_time=start,
                end_time=end
            ))
        
        return cls(segments=segments, video_duration=video_duration)
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """全セグメントの調整後の時間範囲を取得
        
        Returns:
            [(start, end), ...] の形式の調整後時間範囲リスト
        """
        adjusted_ranges = []
        enabled_segments = [seg for seg in self.segments if seg.enabled]
        
        for i, segment in enumerate(enabled_segments):
            # 前後のセグメント情報を取得
            prev_end = None
            next_start = None
            
            if i > 0:
                prev_segment = enabled_segments[i - 1]
                _, prev_end = prev_segment.get_adjusted_range()
            
            if i < len(enabled_segments) - 1:
                next_segment = enabled_segments[i + 1]
                next_start = next_segment.start_time - next_segment.gap_before
            
            # 調整後の範囲を取得
            adjusted_start, adjusted_end = segment.get_adjusted_range(prev_end, next_start)
            
            # 動画の長さを超えないように制限
            if self.video_duration > 0:
                adjusted_end = min(adjusted_end, self.video_duration)
            
            # 有効な範囲のみ追加
            if adjusted_start < adjusted_end:
                adjusted_ranges.append((adjusted_start, adjusted_end))
        
        return adjusted_ranges
    
    def set_all_gaps(self, gap_value: float) -> None:
        """全セグメントのギャップを一括設定
        
        Args:
            gap_value: 設定するギャップ値（秒）
        """
        for segment in self.segments:
            segment.gap_before = gap_value
            segment.gap_after = gap_value
    
    def reset_all_gaps(self) -> None:
        """全セグメントのギャップをリセット"""
        self.set_all_gaps(0.0)
    
    def get_total_duration(self) -> float:
        """調整後の総時間を計算"""
        adjusted_ranges = self.get_adjusted_ranges()
        if not adjusted_ranges:
            return 0.0
        
        total = 0.0
        for start, end in adjusted_ranges:
            total += (end - start)
        
        return total
    
    def get_original_duration(self) -> float:
        """元の総時間を計算"""
        enabled_segments = [seg for seg in self.segments if seg.enabled]
        if not enabled_segments:
            return 0.0
        
        total = 0.0
        for segment in enabled_segments:
            total += segment.duration
        
        return total
    
    def get_gap_at_index(self, index: int) -> float:
        """指定インデックスのつなぎ目のギャップを取得
        
        Args:
            index: つなぎ目のインデックス（0 = 1番目と2番目の間）
            
        Returns:
            ギャップの秒数
        """
        if 0 <= index < len(self.segments) - 1:
            # 前のセグメントのgap_afterと次のセグメントのgap_beforeの大きい方
            return max(
                self.segments[index].gap_after,
                self.segments[index + 1].gap_before
            )
        return 0.0
    
    def set_gap_at_index(self, index: int, gap_value: float) -> None:
        """指定インデックスのつなぎ目のギャップを設定
        
        Args:
            index: つなぎ目のインデックス（0 = 1番目と2番目の間）
            gap_value: 設定するギャップ値（秒）
        """
        if 0 <= index < len(self.segments) - 1:
            # 両方のセグメントに同じ値を設定
            self.segments[index].gap_after = gap_value
            self.segments[index + 1].gap_before = gap_value
    
    def copy(self) -> 'Timeline':
        """タイムラインのディープコピーを作成"""
        return Timeline(
            segments=deepcopy(self.segments),
            video_duration=self.video_duration
        )