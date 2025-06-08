"""
テキスト編集サービス

テキストの編集、差分検出、セグメント管理のビジネスロジックを提供。
"""

from typing import List, Tuple, Optional, Dict, Any
import difflib
import re

from .base import BaseService, ServiceResult, ValidationError, ProcessingError
from config import Config
from core.text_processor import TextProcessor
from core.models import Segment, TranscriptionResult, DiffSegment
from utils.time_utils import format_time, parse_time


class TextEditingService(BaseService):
    """テキスト編集と差分検出のビジネスロジック
    
    責任:
    - 編集されたテキストと元のセグメントの差分検出
    - セグメントの結合・分割
    - タイムスタンプの調整
    - 編集履歴の管理
    """
    
    def _initialize(self):
        """サービス固有の初期化"""
        self.text_processor = TextProcessor()
    
    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド（find_differencesにデリゲート）"""
        return self.find_differences(**kwargs)
    
    def find_differences(
        self,
        original_segments: List[Segment],
        edited_text: str,
        merge_threshold: float = 0.5
    ) -> ServiceResult:
        """編集されたテキストとの差分を検出
        
        Args:
            original_segments: 元のセグメントリスト
            edited_text: 編集されたテキスト
            merge_threshold: セグメント結合の閾値（秒）
            
        Returns:
            ServiceResult: 差分セグメントを含む結果
        """
        try:
            # 入力検証
            if not original_segments:
                raise ValidationError("元のセグメントが空です")
            
            if not edited_text or not edited_text.strip():
                raise ValidationError("編集されたテキストが空です")
            
            # 差分検出実行
            self.logger.info(f"差分検出開始: {len(original_segments)} セグメント")
            
            diff_segments = self.text_processor.find_differences(
                original_segments,
                edited_text
            )
            
            # 結果の分析
            stats = self._analyze_differences(original_segments, diff_segments)
            
            # メタデータの作成
            metadata = {
                'original_segments': len(original_segments),
                'diff_segments': len(diff_segments),
                'added_segments': stats['added'],
                'removed_segments': stats['removed'],
                'modified_segments': stats['modified'],
                'total_duration': stats['total_duration'],
                'diff_duration': stats['diff_duration'],
                'change_ratio': stats['change_ratio']
            }
            
            self.logger.info(
                f"差分検出完了: {len(diff_segments)} セグメント "
                f"(追加: {stats['added']}, 削除: {stats['removed']}, 変更: {stats['modified']})"
            )
            
            return self.create_success_result(
                data=diff_segments,
                metadata=metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"差分検出エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"差分検出中にエラーが発生しました: {str(e)}")
            )
    
    def merge_segments(
        self,
        segments: List[Segment],
        max_gap: float = 0.5,
        max_duration: float = 30.0
    ) -> ServiceResult:
        """近接したセグメントを結合
        
        Args:
            segments: セグメントリスト
            max_gap: 結合する最大ギャップ（秒）
            max_duration: 結合後の最大時間（秒）
            
        Returns:
            ServiceResult: 結合されたセグメント
        """
        try:
            if not segments:
                return self.create_success_result(data=[], metadata={'merged_count': 0})
            
            merged_segments = []
            current_segment = None
            merged_count = 0
            
            for segment in sorted(segments, key=lambda s: s.start):
                if current_segment is None:
                    # 最初のセグメント
                    current_segment = Segment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text,
                        words=segment.words.copy() if segment.words else []
                    )
                else:
                    # ギャップと時間をチェック
                    gap = segment.start - current_segment.end
                    new_duration = segment.end - current_segment.start
                    
                    if gap <= max_gap and new_duration <= max_duration:
                        # 結合
                        current_segment.end = segment.end
                        current_segment.text += " " + segment.text
                        if segment.words:
                            current_segment.words.extend(segment.words)
                        merged_count += 1
                    else:
                        # 新しいセグメントとして追加
                        merged_segments.append(current_segment)
                        current_segment = Segment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text,
                            words=segment.words.copy() if segment.words else []
                        )
            
            # 最後のセグメントを追加
            if current_segment:
                merged_segments.append(current_segment)
            
            metadata = {
                'original_count': len(segments),
                'merged_count': len(merged_segments),
                'segments_merged': merged_count
            }
            
            self.logger.info(
                f"セグメント結合完了: {len(segments)} → {len(merged_segments)} "
                f"({merged_count} 個結合)"
            )
            
            return self.create_success_result(
                data=merged_segments,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"セグメント結合エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"セグメント結合中にエラーが発生しました: {str(e)}")
            )
    
    def split_segments(
        self,
        segments: List[Segment],
        max_duration: float = 10.0
    ) -> ServiceResult:
        """長いセグメントを分割
        
        Args:
            segments: セグメントリスト
            max_duration: 最大セグメント時間（秒）
            
        Returns:
            ServiceResult: 分割されたセグメント
        """
        try:
            split_segments = []
            split_count = 0
            
            for segment in segments:
                duration = segment.end - segment.start
                
                if duration <= max_duration:
                    # 分割不要
                    split_segments.append(segment)
                else:
                    # 分割が必要
                    num_splits = int(duration / max_duration) + 1
                    split_duration = duration / num_splits
                    
                    # テキストを分割（単語境界で）
                    words = segment.text.split()
                    words_per_split = max(1, len(words) // num_splits)
                    
                    for i in range(num_splits):
                        start_time = segment.start + (i * split_duration)
                        end_time = min(
                            segment.start + ((i + 1) * split_duration),
                            segment.end
                        )
                        
                        # テキストの範囲を計算
                        start_word = i * words_per_split
                        end_word = min((i + 1) * words_per_split, len(words))
                        split_text = " ".join(words[start_word:end_word])
                        
                        # 分割されたセグメントを作成
                        split_segment = Segment(
                            start=start_time,
                            end=end_time,
                            text=split_text,
                            words=None  # 単語レベルのタイミングは再計算が必要
                        )
                        
                        split_segments.append(split_segment)
                        split_count += 1
            
            metadata = {
                'original_count': len(segments),
                'split_count': len(split_segments),
                'segments_split': split_count - len(segments)
            }
            
            self.logger.info(
                f"セグメント分割完了: {len(segments)} → {len(split_segments)} "
                f"({split_count - len(segments)} 個分割)"
            )
            
            return self.create_success_result(
                data=split_segments,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"セグメント分割エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"セグメント分割中にエラーが発生しました: {str(e)}")
            )
    
    def format_segments_as_text(
        self,
        segments: List[Segment],
        include_timestamps: bool = True
    ) -> ServiceResult:
        """セグメントをテキスト形式にフォーマット
        
        Args:
            segments: セグメントリスト
            include_timestamps: タイムスタンプを含めるかどうか
            
        Returns:
            ServiceResult: フォーマットされたテキスト
        """
        try:
            lines = []
            
            for segment in segments:
                if include_timestamps:
                    timestamp = f"[{format_time(segment.start)} - {format_time(segment.end)}]"
                    lines.append(f"{timestamp} {segment.text}")
                else:
                    lines.append(segment.text)
            
            formatted_text = "\n".join(lines)
            
            metadata = {
                'segments_count': len(segments),
                'total_characters': len(formatted_text),
                'include_timestamps': include_timestamps
            }
            
            return self.create_success_result(
                data=formatted_text,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"テキストフォーマットエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"テキストフォーマット中にエラーが発生しました: {str(e)}")
            )
    
    def parse_text_with_timestamps(
        self,
        text: str
    ) -> ServiceResult:
        """タイムスタンプ付きテキストをパース
        
        Args:
            text: タイムスタンプ付きテキスト
            
        Returns:
            ServiceResult: パースされたセグメント
        """
        try:
            segments = []
            
            # タイムスタンプのパターン: [00:00:00 - 00:00:05] テキスト
            pattern = r'\[(\d{2}:\d{2}:\d{2}(?:\.\d{3})?)\s*-\s*(\d{2}:\d{2}:\d{2}(?:\.\d{3})?)\]\s*(.+)'
            
            for line in text.strip().split('\n'):
                match = re.match(pattern, line.strip())
                if match:
                    start_str, end_str, segment_text = match.groups()
                    
                    segment = Segment(
                        start=parse_time(start_str),
                        end=parse_time(end_str),
                        text=segment_text.strip(),
                        words=None
                    )
                    
                    segments.append(segment)
                elif line.strip():
                    # タイムスタンプがない行（前のセグメントに追加）
                    if segments:
                        segments[-1].text += " " + line.strip()
            
            metadata = {
                'parsed_segments': len(segments),
                'lines_processed': len(text.strip().split('\n'))
            }
            
            return self.create_success_result(
                data=segments,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"テキストパースエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"テキストパース中にエラーが発生しました: {str(e)}")
            )
    
    def _analyze_differences(
        self,
        original_segments: List[Segment],
        diff_segments: List[DiffSegment]
    ) -> Dict[str, Any]:
        """差分の統計情報を分析
        
        Args:
            original_segments: 元のセグメント
            diff_segments: 差分セグメント
            
        Returns:
            統計情報
        """
        stats = {
            'added': 0,
            'removed': 0,
            'modified': 0,
            'unchanged': 0,
            'total_duration': 0.0,
            'diff_duration': 0.0,
            'change_ratio': 0.0
        }
        
        # 元の総時間を計算
        for segment in original_segments:
            stats['total_duration'] += segment.end - segment.start
        
        # 差分セグメントを分析
        for diff_segment in diff_segments:
            duration = diff_segment.end - diff_segment.start
            stats['diff_duration'] += duration
            
            # 変更タイプをカウント（簡易的な判定）
            if hasattr(diff_segment, 'change_type'):
                if diff_segment.change_type == 'added':
                    stats['added'] += 1
                elif diff_segment.change_type == 'removed':
                    stats['removed'] += 1
                elif diff_segment.change_type == 'modified':
                    stats['modified'] += 1
            else:
                stats['modified'] += 1
        
        # 変更率を計算
        if stats['total_duration'] > 0:
            stats['change_ratio'] = stats['diff_duration'] / stats['total_duration']
        
        return stats