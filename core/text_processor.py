"""
テキスト処理モジュール（差分検出、位置特定など）
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Tuple, Set, Optional

from .transcription import TranscriptionResult, TranscriptionSegment


@dataclass
class TextPosition:
    """テキスト内の位置情報"""
    start: int
    end: int
    text: str
    
    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass 
class TextDifference:
    """テキストの差分情報"""
    original_text: str
    edited_text: str
    common_positions: List[TextPosition]
    added_chars: Set[str]
    added_positions: List[TextPosition] = None  # 追加文字の位置情報
    
    def has_additions(self) -> bool:
        """追加された文字があるか"""
        return len(self.added_chars) > 0
    
    def get_time_ranges(self, transcription: TranscriptionResult) -> List[Tuple[float, float]]:
        """共通部分のタイムスタンプを取得"""
        time_ranges = []
        
        for pos in self.common_positions:
            start_time, end_time = self._get_timestamp_for_position(
                transcription.segments, 
                pos.start, 
                pos.end
            )
            if start_time is not None and end_time is not None:
                time_ranges.append((start_time, end_time))
        
        return time_ranges
    
    def _get_timestamp_for_position(
        self, 
        segments: List[TranscriptionSegment], 
        start_pos: int, 
        end_pos: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """文字位置からタイムスタンプを取得"""
        try:
            start_time = None
            end_time = None
            current_pos = 0
            
            for seg in segments:
                # wordsが必須 - ない場合はエラー
                if not seg.words or len(seg.words) == 0:
                    from utils.exceptions import VideoProcessingError
                    raise VideoProcessingError(
                        f"検索に必要な詳細な文字位置情報がありません。"
                        f"文字起こしを再実行してください。"
                    )
                
                for word in seg.words:
                    try:
                        word_len = len(word['word'])
                        if start_time is None and current_pos <= start_pos < current_pos + word_len:
                            start_time = word['start']
                        if end_time is None and current_pos < end_pos <= current_pos + word_len:
                            end_time = word['end']
                        current_pos += word_len
                    except (KeyError, TypeError) as e:
                        # 不正なword形式の場合はエラー
                        from utils.exceptions import VideoProcessingError
                        raise VideoProcessingError(
                            f"文字位置情報の形式が不正です。"
                            f"文字起こしを再実行してください。"
                        )
                
                if start_time is not None and end_time is not None:
                    break
            
            return start_time, end_time
            
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            if isinstance(e, VideoProcessingError):
                raise
            raise VideoProcessingError(f"タイムスタンプ取得エラー: {str(e)}")


class TextProcessor:
    """テキスト処理クラス"""
    
    DEFAULT_SEPARATOR = "---"
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """テキストを正規化（空白の統一など）"""
        # 全角スペースを半角に変換
        text = text.replace('　', ' ')
        # 連続する空白を1つに
        text = re.sub(r'\s+', ' ', text)
        # 前後の空白を削除
        return text.strip()
    
    @staticmethod
    def remove_spaces(text: str) -> str:
        """テキストから空白を除去"""
        return re.sub(r'\s+', '', text)
    
    def find_differences(self, original: str, edited: str) -> TextDifference:
        """
        元のテキストと編集後のテキストの差分を検出
        
        Args:
            original: 元のテキスト
            edited: 編集後のテキスト
            
        Returns:
            TextDifference: 差分情報
        """
        try:
            # 入力検証
            if not isinstance(original, str) or not isinstance(edited, str):
                from utils.exceptions import VideoProcessingError
                raise VideoProcessingError("テキスト差分検出: 入力は文字列である必要があります")
            
            # テキストを正規化
            original = self.normalize_text(original)
            edited = self.normalize_text(edited)
            
            # 空白を除去したテキストで差分を計算
            original_no_spaces = self.remove_spaces(original)
            edited_no_spaces = self.remove_spaces(edited)
            
            # 差分を計算
            matcher = SequenceMatcher(None, original_no_spaces, edited_no_spaces)
            common_positions = []
            added_chars = set()
            added_positions = []
            
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"テキスト差分検出エラー: {str(e)}")
        
        try:
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    # 元のテキストでの位置を計算
                    original_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                    length = self._calculate_length_with_spaces(original, original_pos, i2 - i1)
                    
                    common_positions.append(TextPosition(
                        start=original_pos,
                        end=original_pos + length,
                        text=original[original_pos:original_pos + length]
                    ))
                    
                elif tag in ['insert', 'replace']:
                    # 追加された文字を収集
                    added_text = edited_no_spaces[j1:j2]
                    added_chars.update(c for c in added_text if not c.isspace())
                    
                    # 追加文字の位置情報を記録（編集後テキストでの位置）
                    if tag == 'insert':
                        # 挿入の場合：元テキストでの挿入位置を特定
                        insert_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                        added_positions.append(TextPosition(
                            start=insert_pos,
                            end=insert_pos,  # 挿入位置なので長さは0
                            text=edited_no_spaces[j1:j2]
                        ))
                    elif tag == 'replace':
                        # 置換の場合：元テキストでの置換位置
                        replace_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                        replace_length = self._calculate_length_with_spaces(original, replace_pos, i2 - i1)
                        added_positions.append(TextPosition(
                            start=replace_pos,
                            end=replace_pos + replace_length,
                            text=edited_no_spaces[j1:j2]
                        ))
            
            return TextDifference(
                original_text=original,
                edited_text=edited,
                common_positions=common_positions,
                added_chars=added_chars,
                added_positions=added_positions
            )
            
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"差分計算処理エラー: {str(e)}")
    
    def _convert_position_with_spaces(self, text_with_spaces: str, text_no_spaces: str, pos_no_spaces: int) -> int:
        """空白を除去したテキストの位置を、元のテキストの位置に変換"""
        original_pos = 0
        no_spaces_pos = 0
        
        while no_spaces_pos < pos_no_spaces and original_pos < len(text_with_spaces):
            if not text_with_spaces[original_pos].isspace():
                no_spaces_pos += 1
            original_pos += 1
        
        return original_pos
    
    def _calculate_length_with_spaces(self, text: str, start_pos: int, length_no_spaces: int) -> int:
        """空白を除去した長さから、元のテキストでの長さを計算"""
        length = 0
        no_spaces_count = 0
        
        while no_spaces_count < length_no_spaces and start_pos + length < len(text):
            if not text[start_pos + length].isspace():
                no_spaces_count += 1
            length += 1
        
        return length
    
    def split_text_into_lines(self, text: str, chars_per_line: int, max_lines: int) -> List[str]:
        """
        テキストを行数と文字数制限に基づいて分割（字幕用）
        
        Args:
            text: 分割するテキスト
            chars_per_line: 1行あたりの最大文字数
            max_lines: 最大行数
            
        Returns:
            分割されたテキストのリスト
        """
        print(f"split_text_into_lines: 入力テキスト='{text}', 1行{chars_per_line}文字, 最大{max_lines}行")
        
        # 空文字列の場合は空リストを返す
        if not text.strip():
            print("  結果: 空テキストのため空リスト")
            return []
        
        # 文末で分割（簡単な方法に変更）
        # 句読点や助詞での自然な区切りを考慮
        text = text.strip()
        
        # まず文字数制限内に収まる場合はそのまま返す
        if len(text) <= chars_per_line * max_lines:
            # 単純に文字数で分割
            lines = []
            for i in range(0, len(text), chars_per_line):
                line = text[i:i+chars_per_line]
                if line.strip():
                    lines.append(line.strip())
            print(f"  単純分割結果: {lines}")
            return lines
        
        # 長いテキストの場合は既存の方法
        sentences = re.split(r'([。．！？、])', text)
        sentences = [''.join(i) for i in zip(sentences[::2], sentences[1::2] + [''])]
        sentences = [s for s in sentences if s.strip()]  # 空文字列を除去
        print(f"  文に分割: {sentences}")
        
        lines = []
        current_line = ""
        
        for sentence in sentences:
            potential_line = current_line + sentence
            
            if len(potential_line) <= chars_per_line:
                current_line = potential_line
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                
                # 文が1行の文字数制限を超える場合は分割
                if len(sentence) > chars_per_line:
                    words = re.findall(r'[一-龯ぁ-んァ-ンa-zA-Z0-9]+|[^一-龯ぁ-んァ-ンa-zA-Z0-9]', sentence)
                    temp_line = ""
                    
                    for word in words:
                        if len(temp_line + word) <= chars_per_line:
                            temp_line += word
                        else:
                            if temp_line:
                                lines.append(temp_line)
                            temp_line = word if len(word) <= chars_per_line else word[:chars_per_line]
                    
                    if temp_line:
                        current_line = temp_line
                else:
                    current_line = sentence
        
        # 最後の行を追加
        if current_line:
            lines.append(current_line)
        
        # 行数制限を適用
        if len(lines) > max_lines:
            lines = lines[:max_lines-1]
            last_line = ' '.join(lines[max_lines-1:])
            if len(last_line) > chars_per_line:
                last_line = last_line[:chars_per_line-3] + '...'
            lines.append(last_line)
        
        print(f"  最終結果: {lines}")
        return lines
    
    def split_text_by_separator(self, text: str, separator: str = None) -> List[str]:
        """
        区切り文字でテキストを分割
        
        Args:
            text: 分割するテキスト
            separator: 区切り文字（デフォルト: ---）
            
        Returns:
            分割されたテキストのリスト
        """
        if separator is None:
            separator = self.DEFAULT_SEPARATOR
        
        # 区切り文字で分割
        sections = text.split(separator)
        
        # 空のセクションを除去し、前後の空白を削除
        sections = [section.strip() for section in sections if section.strip()]
        
        return sections
    
    def find_differences_with_separator(self, original: str, edited: str, transcription, separator: str = None) -> List[Tuple[float, float]]:
        """
        区切り文字に対応した差分検索
        
        Args:
            original: 元のテキスト（文字起こし結果）
            edited: 編集後のテキスト（区切り文字を含む可能性）
            transcription: 文字起こし結果
            separator: 区切り文字（デフォルト: ---）
            
        Returns:
            時間範囲のリスト
        """
        if separator is None:
            separator = self.DEFAULT_SEPARATOR
        
        # 区切り文字が含まれているかチェック
        if separator not in edited:
            # 区切り文字がない場合は通常の処理
            diff = self.find_differences(original, edited)
            return diff.get_time_ranges(transcription)
        
        # 区切り文字で分割
        sections = self.split_text_by_separator(edited, separator)
        
        all_time_ranges = []
        
        # 各セクションについて個別に差分検索
        for i, section in enumerate(sections):
            if not section.strip():
                continue
                
            # 各セクションで差分検索
            diff = self.find_differences(original, section)
            section_ranges = diff.get_time_ranges(transcription)
            
            # 結果をマージ
            all_time_ranges.extend(section_ranges)
        
        # 時間範囲をソートしてマージ
        merged_ranges = self.merge_time_ranges(all_time_ranges)
        
        return merged_ranges
    
    def merge_time_ranges(self, time_ranges: List[Tuple[float, float]], gap_threshold: float = 1.0) -> List[Tuple[float, float]]:
        """
        時間範囲をマージ（近い範囲を結合）
        
        Args:
            time_ranges: 時間範囲のリスト
            gap_threshold: マージする閾値（秒）
            
        Returns:
            マージされた時間範囲のリスト
        """
        if not time_ranges:
            return []
        
        # 開始時間でソート
        sorted_ranges = sorted(time_ranges)
        merged = [sorted_ranges[0]]
        
        for current_start, current_end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            
            # 重複または近い範囲はマージ
            if current_start <= last_end + gap_threshold:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))
        
        return merged