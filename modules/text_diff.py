"""
テキスト差分処理のモジュール
"""

import difflib
from typing import List, Tuple, Dict, Any
from ..utils import BuzzClipError

def find_differences(text1: str, text2: str) -> List[Tuple[str, int, int, int, int]]:
    """2つのテキスト間の差分を検出"""
    try:
        # 差分の検出
        differ = difflib.SequenceMatcher(None, text1, text2)
        differences = []
        
        for tag, i1, i2, j1, j2 in differ.get_opcodes():
            if tag != 'equal':  # 変更があった部分のみを取得
                differences.append((tag, i1, i2, j1, j2))
        
        return differences
    except Exception as e:
        raise BuzzClipError(f"テキスト差分の検出に失敗: {str(e)}")

def get_changed_segments(segments: List[Dict[str, Any]], differences: List[Tuple[str, int, int, int, int]]) -> List[Dict[str, Any]]:
    """変更があったセグメントを抽出"""
    try:
        changed_segments = []
        current_pos = 0
        
        for segment in segments:
            segment_text = segment["text"]
            segment_length = len(segment_text)
            
            # セグメントが変更範囲内にあるかチェック
            for tag, i1, i2, j1, j2 in differences:
                if (current_pos <= i1 < current_pos + segment_length or
                    current_pos < i2 <= current_pos + segment_length):
                    changed_segments.append(segment)
                    break
            
            current_pos += segment_length
        
        return changed_segments
    except Exception as e:
        raise BuzzClipError(f"変更セグメントの抽出に失敗: {str(e)}")

def get_segment_time_ranges(changed_segments: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """変更セグメントの時間範囲を取得"""
    try:
        time_ranges = []
        
        for segment in changed_segments:
            start = segment["start"]
            end = segment["end"]
            time_ranges.append((start, end))
        
        return time_ranges
    except Exception as e:
        raise BuzzClipError(f"時間範囲の取得に失敗: {str(e)}")

def merge_overlapping_ranges(time_ranges: List[Tuple[float, float]], min_gap: float = 0.3) -> List[Tuple[float, float]]:
    """重複する時間範囲をマージ"""
    try:
        if not time_ranges:
            return []
        
        # 開始時間でソート
        sorted_ranges = sorted(time_ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        
        for current in sorted_ranges[1:]:
            previous = merged[-1]
            
            # 現在の範囲が前の範囲と重複または近接している場合
            if current[0] <= previous[1] + min_gap:
                # 範囲をマージ
                merged[-1] = (previous[0], max(previous[1], current[1]))
            else:
                merged.append(current)
        
        return merged
    except Exception as e:
        raise BuzzClipError(f"時間範囲のマージに失敗: {str(e)}") 