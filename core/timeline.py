"""タイムライン管理モジュール

動画セグメントとその間のギャップを管理します。
ギャップは元動画から追加で含める時間範囲として実装されます。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import copy


@dataclass
class TimelineSegment:
    """タイムライン上の1つのセグメント"""
    index: int
    original_start: float  # 元動画での開始時刻
    original_end: float    # 元動画での終了時刻
    gap_before: float = 0.0  # このセグメントの前に追加する時間（秒）
    gap_after: float = 0.0   # このセグメントの後に追加する時間（秒）
    enabled: bool = True     # このセグメントを含めるかどうか
    
    @property
    def duration(self) -> float:
        """セグメントの長さ（ギャップを含まない）"""
        return self.original_end - self.original_start
    
    @property
    def adjusted_start(self) -> float:
        """ギャップを考慮した開始時刻"""
        return max(0, self.original_start - self.gap_before)
    
    @property
    def adjusted_end(self) -> float:
        """ギャップを考慮した終了時刻"""
        # 次のセグメントの開始時刻を超えないように制限する必要がある
        return self.original_end + self.gap_after
    
    @property
    def adjusted_duration(self) -> float:
        """ギャップを含めた全体の長さ"""
        return self.adjusted_end - self.adjusted_start


@dataclass
class Timeline:
    """タイムライン全体を管理するクラス"""
    segments: List[TimelineSegment] = field(default_factory=list)
    video_duration: float = 0.0  # 元動画の全体長さ
    
    def add_segment(self, start: float, end: float) -> TimelineSegment:
        """新しいセグメントを追加"""
        index = len(self.segments)
        segment = TimelineSegment(
            index=index,
            original_start=start,
            original_end=end
        )
        self.segments.append(segment)
        return segment
    
    def get_adjusted_ranges(self) -> List[Tuple[float, float]]:
        """ギャップ調整後の時間範囲のリストを返す
        
        Returns:
            List of (start, end) tuples with gap adjustments applied
        """
        adjusted_ranges = []
        
        for i, segment in enumerate(self.segments):
            if not segment.enabled:
                continue
                
            # 調整後の開始・終了時刻を計算
            adj_start = segment.adjusted_start
            adj_end = segment.adjusted_end
            
            # 前後のセグメントとの重複を防ぐ
            if i > 0 and self.segments[i-1].enabled:
                prev_end = self.segments[i-1].original_end
                # 前のセグメントの終了時刻より前には戻らない
                adj_start = max(adj_start, prev_end)
            
            if i < len(self.segments) - 1 and self.segments[i+1].enabled:
                next_start = self.segments[i+1].original_start
                # 次のセグメントの開始時刻を超えない
                adj_end = min(adj_end, next_start)
            
            # 動画の範囲内に収める
            adj_start = max(0, adj_start)
            adj_end = min(self.video_duration, adj_end)
            
            if adj_start < adj_end:
                adjusted_ranges.append((adj_start, adj_end))
        
        return adjusted_ranges
    
    def set_uniform_gap(self, gap_seconds: float):
        """全てのギャップを一括設定"""
        for i, segment in enumerate(self.segments):
            if i > 0:  # 最初のセグメントには前のギャップはない
                segment.gap_before = gap_seconds
            if i < len(self.segments) - 1:  # 最後のセグメントには後のギャップはない
                segment.gap_after = gap_seconds
    
    def reset_gaps(self):
        """全てのギャップをリセット"""
        for segment in self.segments:
            segment.gap_before = 0.0
            segment.gap_after = 0.0
    
    def get_timeline_display_data(self) -> dict:
        """UI表示用のタイムラインデータを生成"""
        data = {
            'segments': [],
            'gaps': [],
            'total_duration': 0.0
        }
        
        current_pos = 0.0
        
        for i, segment in enumerate(self.segments):
            if not segment.enabled:
                continue
                
            ranges = self.get_adjusted_ranges()
            if i < len(ranges):
                start, end = ranges[i]
                
                # セグメント情報
                data['segments'].append({
                    'index': segment.index,
                    'start': current_pos,
                    'end': current_pos + (end - start),
                    'original_start': segment.original_start,
                    'original_end': segment.original_end,
                    'label': f'セグメント {segment.index + 1}'
                })
                
                current_pos += (end - start)
                
                # ギャップ情報（次のセグメントとの間）
                if i < len(self.segments) - 1:
                    next_segment = self.segments[i + 1]
                    if next_segment.enabled:
                        gap_duration = segment.gap_after + next_segment.gap_before
                        if gap_duration > 0:
                            data['gaps'].append({
                                'index': i,
                                'position': current_pos,
                                'duration': gap_duration
                            })
        
        data['total_duration'] = current_pos
        return data
    
    def clone(self) -> 'Timeline':
        """タイムラインのディープコピーを作成"""
        return copy.deepcopy(self)