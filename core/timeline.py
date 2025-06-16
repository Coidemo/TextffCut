"""
タイムライン管理モジュール

動画セグメントの繋ぎ目調整機能を提供
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from copy import deepcopy


@dataclass
class TimelineSegment:
    """タイムライン上の個別セグメント"""
    index: int
    start_time: float
    end_time: float
    gap_before: float = 0.0  # 前のセグメントとの間隔（秒）
    gap_after: float = 0.0   # 次のセグメントとの間隔（秒）
    enabled: bool = True     # このセグメントを含めるか
    
    @property
    def duration(self) -> float:
        """セグメントの長さ"""
        return self.end_time - self.start_time
    
    def get_adjusted_range(self, prev_end: Optional[float], next_start: Optional[float]) -> Tuple[float, float]:
        """
        ギャップ調整後の時間範囲を取得
        
        Args:
            prev_end: 前のセグメントの終了時刻（なければNone）
            next_start: 次のセグメントの開始時刻（なければNone）
            
        Returns:
            (調整後の開始時刻, 調整後の終了時刻)
        """
        if not self.enabled:
            return None, None
            
        # 開始時刻の調整
        adjusted_start = self.start_time - self.gap_before
        if prev_end is not None and adjusted_start < prev_end:
            # 前のセグメントと重複しないよう調整
            adjusted_start = prev_end
            
        # 終了時刻の調整
        adjusted_end = self.end_time + self.gap_after
        if next_start is not None and adjusted_end > next_start:
            # 次のセグメントと重複しないよう調整
            adjusted_end = next_start
            
        # 調整後の範囲が有効かチェック
        if adjusted_start >= adjusted_end:
            # ギャップ調整により無効な範囲になった場合は元の範囲を返す
            return self.start_time, self.end_time
            
        return adjusted_start, adjusted_end


@dataclass
class Timeline:
    """タイムライン全体の管理"""
    segments: List[TimelineSegment] = field(default_factory=list)
    
    def add_segment(self, start: float, end: float) -> TimelineSegment:
        """セグメントを追加"""
        # 入力検証
        if start < 0 or end < 0:
            raise ValueError("開始時刻と終了時刻は0以上である必要があります")
        if start >= end:
            raise ValueError("終了時刻は開始時刻より後である必要があります")
            
        index = len(self.segments)
        segment = TimelineSegment(
            index=index,
            start_time=start,
            end_time=end
        )
        self.segments.append(segment)
        return segment
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """
        全セグメントの調整後の時間範囲を取得
        
        Returns:
            [(開始時刻, 終了時刻), ...] のリスト（無効なセグメントは除外）
        """
        adjusted_ranges = []
        
        for i, segment in enumerate(self.segments):
            if not segment.enabled:
                continue
                
            # 前後のセグメントの時刻を取得
            prev_end = None
            if i > 0:
                prev_segment = self.segments[i - 1]
                if prev_segment.enabled:
                    prev_end = prev_segment.end_time
                    
            next_start = None
            if i < len(self.segments) - 1:
                next_segment = self.segments[i + 1]
                if next_segment.enabled:
                    next_start = next_segment.start_time
            
            # 調整後の範囲を計算
            adj_start, adj_end = segment.get_adjusted_range(prev_end, next_start)
            if adj_start is not None and adj_end is not None:
                adjusted_ranges.append((adj_start, adj_end))
                
        return adjusted_ranges
    
    def get_total_duration(self) -> Tuple[float, float]:
        """
        調整前後の合計時間を取得
        
        Returns:
            (調整前の合計時間, 調整後の合計時間)
        """
        original_duration = 0.0
        adjusted_duration = 0.0
        
        # 調整前の合計時間
        for segment in self.segments:
            if segment.enabled:
                original_duration += segment.duration
        
        # 調整後の合計時間
        adjusted_ranges = self.get_adjusted_ranges()
        for start, end in adjusted_ranges:
            adjusted_duration += (end - start)
            
        return original_duration, adjusted_duration
    
    def set_all_gaps(self, gap_before: float, gap_after: float):
        """全セグメントのギャップを一括設定"""
        # 入力検証
        if gap_before < 0 or gap_after < 0:
            raise ValueError("ギャップ値は0以上である必要があります")
            
        for segment in self.segments:
            segment.gap_before = gap_before
            segment.gap_after = gap_after
    
    def reset_all_gaps(self):
        """全セグメントのギャップをリセット"""
        self.set_all_gaps(0.0, 0.0)
    
    def toggle_segment(self, index: int):
        """セグメントの有効/無効を切り替え"""
        if not (0 <= index < len(self.segments)):
            raise IndexError(f"インデックス {index} は範囲外です")
        self.segments[index].enabled = not self.segments[index].enabled
    
    def get_enabled_segments(self) -> List[TimelineSegment]:
        """有効なセグメントのみを取得"""
        return [seg for seg in self.segments if seg.enabled]
    
    def clone(self) -> 'Timeline':
        """タイムラインのディープコピーを作成"""
        return Timeline(segments=[deepcopy(seg) for seg in self.segments])