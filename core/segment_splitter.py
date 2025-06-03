"""
セグメント分割モジュール
長いセグメントを適切なサイズに分割してアライメント成功率を向上させる
"""
import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SplitSegment:
    """分割されたセグメント"""
    text: str
    estimated_start: float
    estimated_end: float
    original_segment_idx: int


class SegmentSplitter:
    """セグメント分割クラス"""
    
    # 分割に使用する区切り文字（優先順位順）
    SPLIT_PATTERNS = [
        (r'。', 1.0),      # 句点
        (r'！', 1.0),      # 感嘆符
        (r'？', 1.0),      # 疑問符
        (r'、', 0.5),      # 読点（優先度低め）
        (r'\s+', 0.3),     # 空白（さらに優先度低め）
    ]
    
    # 理想的なセグメント長（秒）
    IDEAL_SEGMENT_LENGTH = 10.0
    MIN_SEGMENT_LENGTH = 5.0
    MAX_SEGMENT_LENGTH = 15.0
    
    def __init__(self):
        # 日本語の平均発話速度（文字/秒）
        self.avg_chars_per_second = 5.0
    
    def should_split_segment(self, segment: Dict[str, Any], chunk_duration: float) -> bool:
        """セグメントを分割すべきか判定"""
        # セグメントの長さを計算
        segment_duration = segment.get('end', 0) - segment.get('start', 0)
        
        # チャンクの長さより長い場合は分割が必要
        if segment_duration > chunk_duration * 0.9:
            return True
        
        # テキストの長さから推定
        text_length = len(segment.get('text', ''))
        estimated_duration = text_length / self.avg_chars_per_second
        
        # 推定時間が最大セグメント長を超える場合も分割
        return estimated_duration > self.MAX_SEGMENT_LENGTH
    
    def split_segments(self, segments: List[Dict[str, Any]], chunk_duration: float) -> List[Dict[str, Any]]:
        """セグメントリストを適切なサイズに分割"""
        split_segments = []
        
        for idx, segment in enumerate(segments):
            if self.should_split_segment(segment, chunk_duration):
                # 分割が必要
                sub_segments = self._split_single_segment(segment, idx, chunk_duration)
                split_segments.extend(sub_segments)
                logger.debug(f"セグメント {idx} を {len(sub_segments)} 個に分割")
            else:
                # そのまま使用
                split_segments.append(segment)
        
        return split_segments
    
    def _split_single_segment(self, segment: Dict[str, Any], segment_idx: int, chunk_duration: float) -> List[Dict[str, Any]]:
        """単一セグメントを分割"""
        text = segment.get('text', '')
        start_time = segment.get('start', 0)
        end_time = segment.get('end', start_time + len(text) / self.avg_chars_per_second)
        total_duration = end_time - start_time
        
        # 分割点を探す
        split_points = self._find_split_points(text)
        
        if not split_points:
            # 分割点が見つからない場合は強制的に分割
            split_points = self._force_split_points(text)
        
        # セグメントを作成
        sub_segments = []
        last_pos = 0
        
        for i, (pos, priority) in enumerate(split_points):
            sub_text = text[last_pos:pos].strip()
            if not sub_text:
                continue
            
            # 時間を按分
            start_ratio = last_pos / len(text)
            end_ratio = pos / len(text)
            sub_start = start_time + total_duration * start_ratio
            sub_end = start_time + total_duration * end_ratio
            
            sub_segment = {
                'text': sub_text,
                'start': sub_start,
                'end': sub_end,
                'original_idx': segment_idx,
                'sub_idx': i
            }
            sub_segments.append(sub_segment)
            last_pos = pos
        
        # 最後の部分
        if last_pos < len(text):
            sub_text = text[last_pos:].strip()
            if sub_text:
                sub_start = start_time + total_duration * (last_pos / len(text))
                sub_segment = {
                    'text': sub_text,
                    'start': sub_start,
                    'end': end_time,
                    'original_idx': segment_idx,
                    'sub_idx': len(split_points)
                }
                sub_segments.append(sub_segment)
        
        return sub_segments if sub_segments else [segment]
    
    def _find_split_points(self, text: str) -> List[Tuple[int, float]]:
        """テキストから分割点を探す"""
        split_candidates = []
        
        # 各パターンで分割点を探す
        for pattern, priority in self.SPLIT_PATTERNS:
            for match in re.finditer(pattern, text):
                end_pos = match.end()
                split_candidates.append((end_pos, priority))
        
        # 重複を除去して優先度順にソート
        split_candidates = list(set(split_candidates))
        split_candidates.sort(key=lambda x: (-x[1], x[0]))  # 優先度降順、位置昇順
        
        # 適切な分割点を選択
        selected_points = []
        target_chars = int(self.IDEAL_SEGMENT_LENGTH * self.avg_chars_per_second)
        
        last_split = 0
        for pos, priority in split_candidates:
            # 前の分割点からの距離
            distance = pos - last_split
            
            # 最小長以上で、理想的な長さに近い場合は採用
            if distance >= self.MIN_SEGMENT_LENGTH * self.avg_chars_per_second:
                selected_points.append((pos, priority))
                last_split = pos
                
                # 残りが短い場合は終了
                if len(text) - pos < self.MIN_SEGMENT_LENGTH * self.avg_chars_per_second:
                    break
        
        return selected_points
    
    def _force_split_points(self, text: str) -> List[Tuple[int, float]]:
        """強制的に分割点を作成（区切り文字が見つからない場合）"""
        split_points = []
        target_chars = int(self.IDEAL_SEGMENT_LENGTH * self.avg_chars_per_second)
        
        # 固定長で分割
        for i in range(target_chars, len(text), target_chars):
            split_points.append((i, 0.1))  # 低優先度
        
        return split_points
    
    def merge_short_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """短すぎるセグメントを結合"""
        if len(segments) <= 1:
            return segments
        
        merged_segments = []
        current_segment = None
        
        for segment in segments:
            segment_duration = segment.get('end', 0) - segment.get('start', 0)
            
            if current_segment is None:
                current_segment = segment.copy()
            elif segment_duration < self.MIN_SEGMENT_LENGTH:
                # 短いセグメントは前のセグメントと結合
                current_segment['text'] += ' ' + segment['text']
                current_segment['end'] = segment['end']
            else:
                # 現在のセグメントを保存して新しいセグメントを開始
                merged_segments.append(current_segment)
                current_segment = segment.copy()
        
        if current_segment:
            merged_segments.append(current_segment)
        
        return merged_segments