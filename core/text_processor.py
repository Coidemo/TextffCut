"""
テキスト処理モジュール（差分検出、位置特定など）
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Tuple, Set, Optional, Any

from .transcription import TranscriptionResult, TranscriptionSegment
from utils.logging import get_logger

logger = get_logger(__name__)


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
        not_found_positions = []
        
        for pos in self.common_positions:
            start_time, end_time = self._get_timestamp_for_position(
                transcription.segments, 
                pos.start, 
                pos.end
            )
            if start_time is not None and end_time is not None:
                time_ranges.append((start_time, end_time))
            else:
                # 見つからなかった位置の詳細を記録
                not_found_info = {
                    'text': pos.text[:50] + ('...' if len(pos.text) > 50 else ''),
                    'position': f"{pos.start}-{pos.end}",
                    'start_found': start_time is not None,
                    'end_found': end_time is not None
                }
                not_found_positions.append(not_found_info)
                logger.warning(
                    f"タイムスタンプが見つかりません: '{not_found_info['text']}' "
                    f"(位置: {not_found_info['position']}, "
                    f"開始: {'✓' if not_found_info['start_found'] else '✗'}, "
                    f"終了: {'✓' if not_found_info['end_found'] else '✗'})"
                )
        
        # 見つからなかった位置が多い場合は詳細なエラーを表示
        if len(not_found_positions) > 0:
            total_positions = len(self.common_positions)
            not_found_count = len(not_found_positions)
            not_found_ratio = not_found_count / total_positions if total_positions > 0 else 0
            
            if not_found_ratio > 0.1:  # 10%以上が見つからない場合
                from utils.exceptions import VideoProcessingError
                error_msg = (
                    f"多くのテキスト位置でタイムスタンプが見つかりません。\n"
                    f"見つからなかった箇所: {not_found_count}/{total_positions} ({not_found_ratio:.1%})\n\n"
                )
                
                # 最初の3つの例を表示
                for i, info in enumerate(not_found_positions[:3]):
                    error_msg += f"例{i+1}: {info['text']} (位置: {info['position']})\n"
                
                if not_found_count > 3:
                    error_msg += f"...他{not_found_count - 3}件\n"
                
                error_msg += "\n文字起こしを再実行するか、テキストの編集内容を確認してください。"
                
                raise VideoProcessingError(error_msg)
            elif not_found_count > 0:
                logger.info(
                    f"一部のテキスト位置でタイムスタンプが見つかりませんでした "
                    f"({not_found_count}/{total_positions})。処理を続行します。"
                )
        
        return time_ranges
    
    def _get_timestamp_for_position(
        self, 
        segments: List[TranscriptionSegment], 
        start_pos: int, 
        end_pos: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """文字位置からタイムスタンプを取得（改善版：フォールバック階層アプローチ）"""
        # デバッグ情報の収集
        target_text = ""
        if hasattr(self, 'original_text'):
            target_text = self.original_text[start_pos:min(end_pos, start_pos + 50)]
        
        debug_info = {
            'target_position': f"{start_pos}-{end_pos}",
            'target_text': target_text,
            'segments_checked': 0,
            'words_checked': 0,
            'words_without_timestamp': 0
        }
        
        try:
            start_time = None
            end_time = None
            current_pos = 0
            
            # タイムスタンプが欠落した場合の推定用
            last_valid_timestamp = None
            next_valid_timestamp = None
            
            for seg_idx, seg in enumerate(segments):
                debug_info['segments_checked'] += 1
                
                # wordsが必須 - ない場合はエラー
                if not seg.words or len(seg.words) == 0:
                    from utils.exceptions import VideoProcessingError
                    raise VideoProcessingError(
                        f"検索に必要な詳細な文字位置情報がありません。"
                        f"文字起こしを再実行してください。"
                        f"\n(セグメント{seg_idx}: {seg.text[:30]}...)"
                    )
                
                for word_idx, word in enumerate(seg.words):
                    debug_info['words_checked'] += 1
                    
                    try:
                        # WordInfoオブジェクトか辞書かを判定
                        if hasattr(word, 'word'):
                            # WordInfoオブジェクトの場合
                            word_text = word.word
                            word_start = word.start
                            word_end = word.end
                        else:
                            # 辞書の場合
                            word_text = word.get('word', '')
                            word_start = word.get('start')
                            word_end = word.get('end')
                        
                        word_len = len(word_text)
                        
                        # タイムスタンプが欠落している場合
                        if word_start is None or word_end is None:
                            debug_info['words_without_timestamp'] += 1
                            logger.warning(f"タイムスタンプが欠落しているword: {word_text}")
                            
                            # フォールバック階層アプローチで推定
                            # TextProcessorのインスタンスを取得
                            text_processor = TextProcessor()
                            estimated_start, estimated_end = text_processor._estimate_timestamp_fallback(
                                seg, word_idx, word_text
                            )
                            
                            # 推定値を使用して処理を続行
                            if start_time is None and current_pos <= start_pos < current_pos + word_len:
                                start_time = estimated_start
                            if end_time is None and current_pos < end_pos <= current_pos + word_len:
                                end_time = estimated_end
                            
                            current_pos += word_len
                            continue
                            
                        # 通常の処理（タイムスタンプあり）
                        if start_time is None and current_pos <= start_pos < current_pos + word_len:
                            start_time = word_start
                        if end_time is None and current_pos < end_pos <= current_pos + word_len:
                            end_time = word_end
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
            
            # デバッグ情報をログに出力
            logger.error(f"タイムスタンプ取得エラー - デバッグ情報: {debug_info}")
            
            if isinstance(e, VideoProcessingError):
                raise
            raise VideoProcessingError(
                f"タイムスタンプ取得エラー: {str(e)}\n"
                f"対象テキスト: '{debug_info['target_text']}'\n"
                f"確認したセグメント数: {debug_info['segments_checked']}\n"
                f"確認したword数: {debug_info['words_checked']}\n"
                f"タイムスタンプ欠落word数: {debug_info['words_without_timestamp']}"
            )


class TextProcessor:
    """テキスト処理クラス"""
    
    DEFAULT_SEPARATOR = "---"
    
    @staticmethod
    def normalize_text(text: str, preserve_newlines: bool = False) -> str:
        """テキストを正規化（空白の統一など）
        
        Args:
            text: 正規化するテキスト
            preserve_newlines: 改行を保持するかどうか
        """
        # 全角スペースを半角に変換
        text = text.replace('　', ' ')
        
        if preserve_newlines:
            # 改行を一時的にマーカーに置換
            text = text.replace('\r\n', '\n')  # Windows改行を統一
            text = text.replace('\r', '\n')    # Mac改行を統一
            lines = text.split('\n')
            
            # 各行内の連続する空白を1つに
            normalized_lines = []
            for line in lines:
                line = re.sub(r'[ \t]+', ' ', line.strip())
                normalized_lines.append(line)
            
            # 空行を除去して結合
            text = '\n'.join(line for line in normalized_lines if line)
        else:
            # 連続する空白（改行含む）を1つのスペースに
            text = re.sub(r'\s+', ' ', text)
        
        # 前後の空白を削除
        return text.strip()
    
    @staticmethod
    def remove_spaces(text: str) -> str:
        """テキストから空白を除去"""
        return re.sub(r'\s+', '', text)
    
    @staticmethod
    def normalize_for_matching(text: str, language: str = 'ja') -> str:
        """マッチング用のテキスト正規化（言語対応）
        
        Args:
            text: 正規化するテキスト
            language: 言語コード（'ja', 'en'など）
        """
        # 全角スペースを半角に変換
        text = text.replace('　', ' ')
        
        if language == 'ja':
            # 日本語の場合：単語間のスペースは基本的に削除
            # ただし、英数字の前後のスペースは保持
            
            # 英数字と日本語文字の境界にマーカーを挿入
            text = re.sub(r'([a-zA-Z0-9]+)([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])', r'\1 \2', text)
            text = re.sub(r'([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])([a-zA-Z0-9]+)', r'\1 \2', text)
            
            # 連続するスペースを1つに
            text = re.sub(r'\s+', ' ', text)
            
            # 記号の前後のスペースを削除（句読点など）
            text = re.sub(r'\s*([。、！？])\s*', r'\1', text)
            
        else:
            # 英語の場合：連続するスペースのみ正規化
            text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
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
    
    def _estimate_timestamp_fallback(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[float, float]:
        """
        フォールバック階層アプローチでタイムスタンプを推定
        
        Args:
            seg: 現在のセグメント
            word_idx: word のインデックス
            word_text: word のテキスト
            
        Returns:
            (推定開始時間, 推定終了時間)
        """
        # Step 1: 近隣の有効なタイムスタンプから推定
        result = self._estimate_from_nearby_timestamps(seg, word_idx, word_text)
        if result[0] is not None:
            return result
        
        # Step 2: セグメント内の発話速度から推定
        result = self._estimate_from_speech_rate(seg, word_idx, word_text)
        if result[0] is not None:
            return result
        
        # Step 3: セグメント境界から推定（改善版）
        result = self._estimate_from_segment_bounds(seg, word_idx, word_text)
        return result
    
    def _estimate_from_nearby_timestamps(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        近隣の有効なタイムスタンプから推定
        
        Returns:
            (推定開始時間, 推定終了時間) または (None, None)
        """
        # 前後の有効なタイムスタンプを収集
        prev_timestamps = []
        next_timestamps = []
        
        # 前方検索（最大10個まで拡張）
        for prev_idx in range(max(0, word_idx - 10), word_idx):
            prev_word = seg.words[prev_idx]
            ts_start, ts_end = self._extract_timestamp(prev_word)
            if ts_start is not None and ts_end is not None:
                prev_timestamps.append((prev_idx, ts_start, ts_end))
        
        # 後方検索（最大10個まで拡張）
        for next_idx in range(word_idx + 1, min(len(seg.words), word_idx + 11)):
            next_word = seg.words[next_idx]
            ts_start, ts_end = self._extract_timestamp(next_word)
            if ts_start is not None and ts_end is not None:
                next_timestamps.append((next_idx, ts_start, ts_end))
        
        # 推定処理
        if prev_timestamps and next_timestamps:
            # 両方ある場合：線形補間
            prev_idx, prev_start, prev_end = prev_timestamps[-1]
            next_idx, next_start, next_end = next_timestamps[0]
            
            # より精密な補間（文字数も考慮）
            char_count_before = sum(len(self._get_word_text(seg.words[i])) 
                                  for i in range(prev_idx, word_idx))
            char_count_after = sum(len(self._get_word_text(seg.words[i])) 
                                 for i in range(word_idx + 1, next_idx + 1))
            char_count_current = len(word_text)
            
            total_chars = char_count_before + char_count_current + char_count_after
            if total_chars > 0:
                # 文字数ベースの位置比率
                position_ratio = char_count_before / total_chars
            else:
                # インデックスベースにフォールバック
                position_ratio = (word_idx - prev_idx) / (next_idx - prev_idx)
            
            # 時間を推定
            time_gap = next_start - prev_end
            estimated_start = prev_end + time_gap * position_ratio
            
            # 終了時間は局所的な平均発話速度から
            local_speed = (char_count_before + char_count_after) / (next_end - prev_start)
            if local_speed > 0:
                estimated_duration = char_count_current / local_speed
            else:
                estimated_duration = (prev_end - prev_start + next_end - next_start) / 2
            
            estimated_end = estimated_start + estimated_duration
            
            logger.info(f"タイムスタンプを近隣から推定（補間）: {word_text} "
                       f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
            
        elif prev_timestamps:
            # 前のタイムスタンプのみ
            prev_idx, prev_start, prev_end = prev_timestamps[-1]
            
            # 前の単語からの文字数
            char_count = sum(len(self._get_word_text(seg.words[i])) 
                           for i in range(prev_idx + 1, word_idx + 1))
            
            # 前の単語の発話速度を使用
            prev_duration = prev_end - prev_start
            prev_chars = len(self._get_word_text(seg.words[prev_idx]))
            
            if prev_chars > 0 and prev_duration > 0:
                char_per_sec = prev_chars / prev_duration
                estimated_duration = len(word_text) / char_per_sec
                estimated_start = prev_end + 0.05  # 小さなギャップ
            else:
                estimated_duration = 0.2  # デフォルト
                estimated_start = prev_end + 0.1
            
            estimated_end = estimated_start + estimated_duration
            
            logger.info(f"タイムスタンプを前方から推定: {word_text} "
                       f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
            
        elif next_timestamps:
            # 後のタイムスタンプのみ
            next_idx, next_start, next_end = next_timestamps[0]
            
            # 次の単語までの文字数
            char_count = sum(len(self._get_word_text(seg.words[i])) 
                           for i in range(word_idx, next_idx))
            
            # 次の単語の発話速度を使用
            next_duration = next_end - next_start
            next_chars = len(self._get_word_text(seg.words[next_idx]))
            
            if next_chars > 0 and next_duration > 0:
                char_per_sec = next_chars / next_duration
                estimated_duration = len(word_text) / char_per_sec
                estimated_end = next_start - 0.05  # 小さなギャップ
            else:
                estimated_duration = 0.2  # デフォルト
                estimated_end = next_start - 0.1
            
            estimated_start = estimated_end - estimated_duration
            
            logger.info(f"タイムスタンプを後方から推定: {word_text} "
                       f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
        
        # 近隣にタイムスタンプがない場合
        return None, None
    
    def _estimate_from_speech_rate(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        セグメント内の発話速度から推定
        
        Returns:
            (推定開始時間, 推定終了時間) または (None, None)
        """
        # セグメント内の有効なタイムスタンプを持つwordを収集
        valid_words = []
        for i, word in enumerate(seg.words):
            ts_start, ts_end = self._extract_timestamp(word)
            if ts_start is not None and ts_end is not None:
                valid_words.append({
                    'index': i,
                    'text': self._get_word_text(word),
                    'start': ts_start,
                    'end': ts_end
                })
        
        if len(valid_words) < 2:
            # 発話速度を計算するには少なくとも2つの有効なwordが必要
            return None, None
        
        # 最初と最後の有効なタイムスタンプ
        first_valid = valid_words[0]
        last_valid = valid_words[-1]
        
        # 実際の発話範囲
        speech_start = first_valid['start']
        speech_end = last_valid['end']
        speech_duration = speech_end - speech_start
        
        # 総文字数を計算
        total_chars = sum(len(w['text']) for w in valid_words)
        
        if speech_duration > 0 and total_chars > 0:
            # 平均発話速度（文字/秒）
            avg_char_per_sec = total_chars / speech_duration
            
            # 現在のwordまでの文字数
            chars_before = sum(len(self._get_word_text(seg.words[i])) 
                             for i in range(word_idx))
            
            # 推定時間
            if word_idx < first_valid['index']:
                # 最初の有効タイムスタンプより前
                # 発話開始前の時間を推定
                chars_to_first = sum(len(self._get_word_text(seg.words[i])) 
                                   for i in range(word_idx, first_valid['index']))
                time_before = chars_to_first / avg_char_per_sec
                estimated_start = max(seg.start, speech_start - time_before)
                estimated_duration = len(word_text) / avg_char_per_sec
                estimated_end = estimated_start + estimated_duration
            else:
                # 通常の推定
                estimated_time = speech_start + (chars_before / avg_char_per_sec)
                estimated_duration = len(word_text) / avg_char_per_sec
                estimated_start = estimated_time
                estimated_end = estimated_start + estimated_duration
            
            logger.info(f"タイムスタンプを発話速度から推定: {word_text} "
                       f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒) "
                       f"[速度: {avg_char_per_sec:.1f}文字/秒]")
            return estimated_start, estimated_end
        
        return None, None
    
    def _estimate_from_segment_bounds(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[float, float]:
        """
        セグメント境界から推定（改善版）
        最終手段として使用
        
        Returns:
            (推定開始時間, 推定終了時間)
        """
        # セグメント内の最初と最後の有効なタイムスタンプを探す
        first_valid_time = None
        last_valid_time = None
        
        for word in seg.words:
            ts_start, ts_end = self._extract_timestamp(word)
            if ts_start is not None:
                if first_valid_time is None:
                    first_valid_time = ts_start
                last_valid_time = ts_end
        
        # 実際の発話範囲を推定
        if first_valid_time is not None and last_valid_time is not None:
            # 有効なタイムスタンプがある場合
            speech_start = first_valid_time
            speech_end = last_valid_time
            speech_duration = speech_end - speech_start
        else:
            # 全くタイムスタンプがない場合（最悪のケース）
            # セグメントの前後に少し余裕を持たせる
            speech_start = seg.start + 0.5
            speech_end = seg.end - 0.5
            speech_duration = speech_end - speech_start
        
        # 位置比率で推定
        if len(seg.words) > 0:
            word_ratio = word_idx / len(seg.words)
            estimated_start = speech_start + speech_duration * word_ratio
            
            # 単純な長さ推定
            avg_word_duration = speech_duration / len(seg.words)
            estimated_end = estimated_start + avg_word_duration
        else:
            # フォールバックのフォールバック
            estimated_start = seg.start
            estimated_end = seg.start + 0.2
        
        logger.warning(f"タイムスタンプをセグメント境界から推定（最終手段）: {word_text} "
                      f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
        return estimated_start, estimated_end
    
    def _extract_timestamp(self, word: Any) -> Tuple[Optional[float], Optional[float]]:
        """
        wordオブジェクトからタイムスタンプを抽出
        
        Returns:
            (start, end) または (None, None)
        """
        if hasattr(word, 'start') and hasattr(word, 'end'):
            return word.start, word.end
        elif isinstance(word, dict):
            return word.get('start'), word.get('end')
        return None, None
    
    def _get_word_text(self, word: Any) -> str:
        """
        wordオブジェクトからテキストを取得
        
        Returns:
            wordのテキスト
        """
        if hasattr(word, 'word'):
            return word.word
        elif isinstance(word, dict):
            return word.get('word', '')
        return ''