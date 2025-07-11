"""
SequenceMatcherベースのテキスト処理ゲートウェイ

v0.9.7で使用されていたdifflib.SequenceMatcherアルゴリズムを
クリーンアーキテクチャに統合した実装。
"""

from difflib import SequenceMatcher
from typing import List, Optional, Tuple
from uuid import uuid4
import re

from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult
from domain.value_objects import TimeRange
from use_cases.interfaces.text_processor_gateway import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class SequenceMatcherTextProcessorGateway(ITextProcessorGateway):
    """
    difflib.SequenceMatcherを使用したテキスト処理ゲートウェイ
    
    v0.9.7の実装をベースに、ブロック単位の自然なマッチングを提供。
    LCSアルゴリズムと比較して、より連続的で人間の直感に近い結果を生成。
    """
    
    def __init__(self):
        logger.info("SequenceMatcherTextProcessorGatewayを初期化しました")
        self.DEFAULT_SEPARATOR = "---"
        self._transcription_result = None  # TranscriptionResultをキャッシュ
        self._char_array_text = None  # CharacterArrayBuilderで構築したテキストをキャッシュ
    
    def set_transcription_result(self, transcription_result: TranscriptionResult) -> None:
        """TranscriptionResultを設定し、CharacterArrayBuilderでテキストを構築"""
        if self._transcription_result != transcription_result:
            from domain.use_cases.character_array_builder import CharacterArrayBuilder
            builder = CharacterArrayBuilder()
            _, self._char_array_text = builder.build_from_transcription(transcription_result)
            self._transcription_result = transcription_result
            logger.info(f"TranscriptionResultを設定: CharacterArrayBuilderで構築 - {len(self._char_array_text)}文字")
    
    def normalize_for_comparison(self, text: str) -> str:
        """比較用にテキストを正規化"""
        # スペース（全角・半角）と改行を全て削除
        text = text.replace('　', '').replace(' ', '')
        text = text.replace('\n', '').replace('\r', '')
        return text
    
    def remove_spaces(self, text: str) -> str:
        """テキストから空白を除去"""
        return re.sub(r'\s+', '', text)
    
    
    def find_differences(
        self,
        original_text: str,
        edited_text: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        元のテキストと編集後のテキストの差分を検出
        
        SequenceMatcherを使用して、ブロック単位の自然なマッチングを行う。
        """
        logger.info("SequenceMatcherベースの差分検出を開始します")
        import time
        
        try:
            # CharacterArrayBuilderで構築したテキストが利用可能な場合は使用
            if self._char_array_text is not None:
                logger.info(f"CharacterArrayBuilderのテキストを使用: {len(self._char_array_text)}文字")
                original_text = self._char_array_text
            
            # 元のテキストは一切変更しない
            # 編集テキストのみ正規化（境界調整マーカーは除去）
            cleaned_edited = self.remove_boundary_markers(edited_text)
            
            # 文脈マーカーを抽出（位置情報の保持のため）
            context_markers = self.extract_context_markers(cleaned_edited)
            
            # 正規化（文脈マーカーは含めたまま）
            normalized_edited = self.normalize_for_comparison(cleaned_edited)
            
            logger.info(f"原文: {len(original_text)}文字, 編集: {len(normalized_edited)}文字")
            
            # SequenceMatcherで直接比較
            start_time = time.time()
            matcher = SequenceMatcher(None, original_text, normalized_edited)
            logger.debug(f"SequenceMatcher作成: {time.time() - start_time:.3f}秒")
            
            # 差分を収集
            differences = []
            
            start_time = time.time()
            opcodes = list(matcher.get_opcodes())
            logger.debug(f"get_opcodes: {time.time() - start_time:.3f}秒")
            
            start_time = time.time()
            for tag, i1, i2, j1, j2 in opcodes:
                if tag == 'equal':
                    # 共通部分：元のテキストの位置をそのまま使用
                    actual_text = original_text[i1:i2]
                    differences.append((
                        DifferenceType.UNCHANGED,
                        actual_text,
                        [(i1, i2)]
                    ))
                    
                elif tag == 'delete':
                    # 削除された部分
                    actual_text = original_text[i1:i2]
                    differences.append((
                        DifferenceType.DELETED,
                        actual_text,
                        [(i1, i2)]
                    ))
                    
                elif tag == 'insert':
                    # 追加された部分
                    added_text = normalized_edited[j1:j2]
                    differences.append((
                        DifferenceType.ADDED,
                        added_text,
                        None
                    ))
                    
                elif tag == 'replace':
                    # 置換された部分（削除と追加に分解）
                    # 削除部分
                    actual_text = original_text[i1:i2]
                    differences.append((
                        DifferenceType.DELETED,
                        actual_text,
                        [(i1, i2)]
                    ))
                    
                    # 追加部分
                    added_text = normalized_edited[j1:j2]
                    differences.append((
                        DifferenceType.ADDED,
                        added_text,
                        None
                    ))
            
            logger.debug(f"opcodes処理: {time.time() - start_time:.3f}秒")
            
            # ログ出力
            unchanged_count = sum(1 for d in differences if d[0] == DifferenceType.UNCHANGED)
            deleted_count = sum(1 for d in differences if d[0] == DifferenceType.DELETED)
            added_count = sum(1 for d in differences if d[0] == DifferenceType.ADDED)
            
            logger.info(f"差分検出完了: {unchanged_count}個の一致, {deleted_count}個の削除, {added_count}個の追加")
            
            result = TextDifference(
                id=str(uuid4()),
                original_text=original_text,
                edited_text=edited_text,
                differences=differences
            )
            
            # 後で境界調整で使用するために差分結果を保存
            self._last_diff_result = result
            
            # 文脈マーカー情報も保存（後で使用するため）
            self._context_markers = context_markers
            
            return result
            
        except Exception as e:
            logger.error(f"差分検出エラー: {str(e)}", exc_info=True)
            # エラー時は空の差分を返す
            return TextDifference(
                id=str(uuid4()),
                original_text=original_text,
                edited_text=edited_text,
                differences=[]
            )
    
    def _find_differences_for_excerpt(
        self, original: str, excerpt: str, skip_normalization: bool = False
    ) -> TextDifference:
        """
        抜粋テキストの差分を検出（元のテキストから抜粋部分を探す）
        """
        # まず正規化してから検索
        normalized_original = self.normalize_for_comparison(original) if not skip_normalization else original
        normalized_excerpt = self.normalize_for_comparison(excerpt) if not skip_normalization else excerpt
        
        # 正規化したテキストで位置を探す
        position = normalized_original.find(normalized_excerpt)
        
        if position == -1:
            # スペースも除去して再検索
            excerpt_no_space = self.remove_spaces(normalized_excerpt)
            original_no_space = self.remove_spaces(normalized_original)
            position_no_space = original_no_space.find(excerpt_no_space)
            
            if position_no_space != -1:
                # スペースなしで見つかった場合、元のテキストでの位置を推定
                position = self._convert_position_with_spaces(normalized_original, original_no_space, position_no_space)
                logger.info(f"スペースを除去して抜粋を発見: 位置={position}")
        
        if position == -1:
            # 見つからない場合は空の差分を返す
            logger.warning(f"抜粋テキストが元のテキストに見つかりません（抜粋: {len(excerpt)}文字）")
            return TextDifference(
                id=str(uuid4()),
                original_text=original,
                edited_text=excerpt,
                differences=[(DifferenceType.ADDED, excerpt, None)]
            )
        
        # 正規化したテキストでの位置から、元のテキストでの位置を計算
        actual_position = self._find_position_in_original(original, normalized_original, position)
        
        # マッチしたテキストの長さを計算
        matched_length = len(normalized_excerpt)
        
        # 元のテキストでの実際の長さを調整
        actual_end = actual_position
        normalized_count = 0
        while normalized_count < matched_length and actual_end < len(original):
            if self.normalize_for_comparison(original[actual_position:actual_end + 1]) == normalized_excerpt[:normalized_count + 1]:
                normalized_count += 1
            actual_end += 1
        
        found_text = original[actual_position:actual_end]
        
        differences = [(
            DifferenceType.UNCHANGED,
            found_text,
            [(actual_position, actual_end)]
        )]
        
        # 編集テキストに追加された文字を検出
        if len(excerpt) > len(found_text):
            # 正規化前の編集テキストと比較
            added_text = ""
            for char in excerpt:
                if char not in found_text:
                    added_text += char
            
            if added_text:
                differences.append((
                    DifferenceType.ADDED,
                    added_text,
                    None
                ))
        
        return TextDifference(
            id=str(uuid4()),
            original_text=original,
            edited_text=excerpt,
            differences=differences
        )
    
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
    
    def _find_position_in_original(self, original: str, normalized: str, normalized_pos: int) -> int:
        """正規化されたテキストの位置から、元のテキストでの位置を推定
        
        注：現在は使用されていない（高速化のため直接検索を使用）
        """
        # シンプルに同じ位置を返す（元のテキストを正規化していないため）
        return min(normalized_pos, len(original) - 1)
    
    def get_time_ranges(
        self, text_difference: TextDifference, transcription_result: TranscriptionResult
    ) -> List[TimeRange]:
        """差分情報から時間範囲を計算（境界調整マーカーと文脈マーカーも処理）"""
        logger.info("時間範囲の計算を開始します")
        
        # CharacterArrayBuilderで再構築したテキストを使用
        from domain.use_cases.character_array_builder import CharacterArrayBuilder
        builder = CharacterArrayBuilder()
        char_array, full_text = builder.build_from_transcription(transcription_result)
        
        logger.info(f"CharacterArrayBuilderで再構築: {len(full_text)}文字")
        
        # 編集テキストからマーカーを抽出
        edited_text = text_difference.edited_text
        logger.info(f"[get_time_ranges] edited_text: {edited_text[:50]}...")
        boundary_markers = self._extract_boundary_markers(edited_text)
        context_markers = self.extract_context_markers(edited_text)
        
        if boundary_markers:
            logger.info(f"[境界調整] {len(boundary_markers)}個のマーカーを検出")
            for marker in boundary_markers:
                logger.info(f"  - {marker['marker']} (位置: {marker['position']}, タイプ: {marker['type']})")
        
        if context_markers:
            logger.info(f"[文脈マーカー] {len(context_markers)}個のマーカーを検出")
            for marker in context_markers:
                logger.info(f"  - {marker['full_match']} (位置: {marker['start']}-{marker['end']})")
        
        # 差分から時間範囲を抽出
        time_ranges = []
        range_index = 0  # 実際の時間範囲のインデックス
        
        for i, (diff_type, text, positions) in enumerate(text_difference.differences):
            if diff_type == DifferenceType.UNCHANGED and positions:
                for start_pos, end_pos in positions:
                    # 文字配列から時間情報を取得
                    if 0 <= start_pos < len(char_array) and 0 <= end_pos <= len(char_array):
                        start_char = char_array[start_pos]
                        
                        # 終了時間の計算：次の文字の開始時間を使用
                        if end_pos < len(char_array):
                            next_char = char_array[end_pos]
                            end_time = next_char.start
                        else:
                            end_char = char_array[end_pos - 1]
                            end_time = end_char.end
                        
                        if start_char.start is not None and end_time is not None:
                            # 境界調整マーカーのチェック
                            start_adjustment = 0
                            end_adjustment = 0
                            
                            # このセクションの直前にマーカーがあるかチェック
                            section_text = text
                            for marker_info in boundary_markers:
                                marker = marker_info['marker']
                                marker_type = marker_info['type']
                                amount = marker_info['amount']
                                marker_pos = marker_info['position']
                                
                                # マーカーの直後のテキストを取得
                                text_after = edited_text[marker_pos + len(marker):marker_pos + len(marker) + 20].strip()
                                
                                logger.debug(f"[境界調整デバッグ] 差分{i}(範囲{range_index}): '{section_text[:20]}...', "
                                           f"マーカー後テキスト: '{text_after}'")
                                
                                # このセクションの開始部分と比較
                                if section_text.startswith(text_after) or text_after.startswith(section_text[:20]):
                                    if marker_type == 'advance_next':  # [<数値]
                                        start_adjustment = -amount
                                        logger.info(f"[境界調整] 範囲 {range_index + 1} の開始を {amount}秒早めます: '{section_text[:20]}...'")
                                    elif marker_type == 'delay_next':  # [>数値]
                                        start_adjustment = amount
                                        logger.info(f"[境界調整] 範囲 {range_index + 1} の開始を {amount}秒遅らせます: '{section_text[:20]}...'")
                            
                            # 調整を適用
                            adjusted_start = max(0, start_char.start + start_adjustment)
                            adjusted_end = max(adjusted_start, end_time + end_adjustment)
                            
                            time_ranges.append(TimeRange(
                                start=adjusted_start,
                                end=adjusted_end
                            ))
                            range_index += 1  # 実際の範囲を追加したのでインクリメント
        
        # マージ前の範囲をログ出力
        logger.debug(f"マージ前の時間範囲: {len(time_ranges)}個")
        for idx, tr in enumerate(time_ranges):
            logger.debug(f"  範囲{idx+1}: {tr.start:.3f} - {tr.end:.3f}秒")
        
        # 文脈マーカー部分を除外
        if context_markers:
            time_ranges = self._exclude_context_marker_ranges(time_ranges, context_markers, char_array, edited_text)
            logger.info(f"文脈マーカー除外後: {len(time_ranges)}個の範囲")
        
        # マージはしない（境界調整を正確に反映するため）
        logger.info(f"時間範囲を計算しました: {len(time_ranges)}個の範囲")
        return time_ranges
    
    def _merge_time_ranges(
        self, time_ranges: List[TimeRange], gap_threshold: float = 1.0
    ) -> List[TimeRange]:
        """時間範囲をマージ（近い範囲を結合）"""
        if not time_ranges:
            return []
        
        # 開始時間でソート
        sorted_ranges = sorted(time_ranges, key=lambda r: r.start)
        merged = [sorted_ranges[0]]
        
        for current in sorted_ranges[1:]:
            last = merged[-1]
            
            # 重複または近い範囲はマージ
            if current.start <= last.end + gap_threshold:
                merged[-1] = TimeRange(
                    start=last.start,
                    end=max(last.end, current.end)
                )
            else:
                merged.append(current)
        
        return merged
    
    def apply_boundary_adjustments(self, text: str, time_ranges: list[TimeRange]) -> tuple[str, list[TimeRange]]:
        """境界調整マーカーを適用"""
        import re
        
        # マーカーを除去したテキスト
        cleaned_text = self.remove_boundary_markers(text)
        
        # マーカーを抽出して解析
        adjustments = []
        
        # マーカーパターン（負の数値にも対応）
        marker_patterns = [
            (r'\[(-?\d+(?:\.\d+)?)<\]', 'shrink_prev'),   # [1.0<] 前のクリップを縮める
            (r'\[(-?\d+(?:\.\d+)?)>\]', 'extend_prev'),   # [1.0>] 前のクリップを延ばす
            (r'\[<(-?\d+(?:\.\d+)?)\]', 'advance_next'),  # [<1.0] 次のクリップを早める
            (r'\[>(-?\d+(?:\.\d+)?)\]', 'delay_next'),    # [>1.0] 次のクリップを遅らせる
        ]
        
        # 各マーカーを探してその位置を特定
        for pattern, adj_type in marker_patterns:
            for match in re.finditer(pattern, text):
                amount = float(match.group(1))
                marker_pos = match.start()
                
                # マーカーの前のテキストで位置を特定
                text_before_marker = text[:marker_pos]
                # マーカーを除去したテキストでの位置を計算
                cleaned_text_before = self.remove_boundary_markers(text_before_marker)
                
                # どのセグメントの境界かを特定
                # マーカーの前後のテキストを取得
                marker_end_pos = marker_pos + len(match.group(0))
                text_after_marker = text[marker_end_pos:marker_end_pos + 20]  # マーカー直後の20文字
                
                # マーカー直後のテキストがどのセグメントに属するか確認
                target_segment = 0
                
                if hasattr(self, '_last_diff_result') and self._last_diff_result:
                    # 差分結果から各セグメントを確認
                    for i, (diff_type, segment_text, positions) in enumerate(self._last_diff_result.differences):
                        if diff_type == DifferenceType.UNCHANGED:
                            # マーカー後のテキストがこのセグメントの開始部分と一致するか確認
                            if segment_text.startswith(text_after_marker.strip()):
                                # [<数値]の場合、このセグメントの開始に影響
                                if adj_type == 'advance_next' or adj_type == 'delay_next':
                                    target_segment = i
                                else:
                                    # [数値>]や[数値<]の場合、前のセグメントの終了に影響
                                    target_segment = max(0, i - 1)
                                break
                            # 部分一致も確認（スペースや改行の違いを吸収）
                            elif text_after_marker.strip() and text_after_marker.strip() in segment_text:
                                if adj_type == 'advance_next' or adj_type == 'delay_next':
                                    target_segment = i
                                else:
                                    target_segment = max(0, i - 1)
                                break
                else:
                    # フォールバック：単純な比率計算
                    if len(cleaned_text) > 0:
                        marker_position_ratio = len(cleaned_text_before) / len(cleaned_text)
                        estimated_segment = int(marker_position_ratio * len(time_ranges))
                        target_segment = min(estimated_segment, len(time_ranges) - 1)
                
                adjustments.append({
                    'type': adj_type,
                    'amount': amount,
                    'segment': target_segment,
                    'position': marker_pos
                })
                
                logger.debug(f"マーカー {match.group(0)} を検出: "
                           f"位置={marker_pos}, "
                           f"マーカー後のテキスト='{text_after_marker.strip()[:10]}...', "
                           f"対象セグメント={target_segment}, "
                           f"タイプ={adj_type}")
        
        # 時間範囲を調整
        if adjustments and time_ranges:
            adjusted_ranges = []
            for i, tr in enumerate(time_ranges):
                start = tr.start
                end = tr.end
                
                # このセグメントに対する調整を適用
                for adj in adjustments:
                    # [<数値] は次のセグメントの開始に影響を与える
                    if adj['type'] == 'advance_next' and adj['segment'] + 1 == i:
                        # 次のクリップ（このクリップ）を早める
                        start -= adj['amount']
                        logger.debug(f"セグメント{i}の開始を{adj['amount']}秒早めました")
                    elif adj['type'] == 'delay_next' and adj['segment'] + 1 == i:
                        # 次のクリップ（このクリップ）を遅らせる
                        start += adj['amount']
                    elif adj['type'] == 'shrink_prev' and i > 0 and adj['segment'] == i:
                        # 前のクリップの終了を早める（このクリップには影響なし）
                        pass
                    elif adj['type'] == 'extend_prev' and i > 0 and adj['segment'] == i:
                        # 前のクリップの終了を延ばす（このクリップには影響なし）
                        pass
                
                # 前のクリップに対する調整（次のセグメントの境界調整）
                if i > 0:
                    for adj in adjustments:
                        if adj['type'] == 'shrink_prev' and adj['segment'] == i:
                            # このセグメントの前のクリップを縮める
                            if i - 1 < len(adjusted_ranges):
                                prev_range = adjusted_ranges[i - 1]
                                adjusted_ranges[i - 1] = TimeRange(
                                    start=prev_range.start,
                                    end=prev_range.end - adj['amount']
                                )
                        elif adj['type'] == 'extend_prev' and adj['segment'] == i:
                            # このセグメントの前のクリップを延ばす
                            if i - 1 < len(adjusted_ranges):
                                prev_range = adjusted_ranges[i - 1]
                                adjusted_ranges[i - 1] = TimeRange(
                                    start=prev_range.start,
                                    end=prev_range.end + adj['amount']
                                )
                
                # 調整後の範囲を追加（時間が正の値であることを確認）
                adjusted_ranges.append(TimeRange(
                    start=max(0, start),
                    end=max(start, end)
                ))
            
            logger.info(f"境界調整を適用: {len(adjustments)}個のマーカー")
            return cleaned_text, adjusted_ranges
        
        return cleaned_text, time_ranges
    
    def normalize_text(self, text: str) -> str:
        """テキストを正規化"""
        return self.normalize_for_comparison(text)
    
    def search_text(
        self, query: str, transcription_result: TranscriptionResult, case_sensitive: bool = False
    ) -> list[tuple[str, TimeRange]]:
        """文字起こし結果からテキストを検索"""
        # TranscriptionResultからテキストを取得
        if hasattr(transcription_result, 'text'):
            full_text = transcription_result.text
        else:
            # セグメントから結合
            full_text = "".join(seg.text for seg in transcription_result.segments)
        
        normalized_text = self.normalize_for_comparison(full_text)
        normalized_query = self.normalize_for_comparison(query)
        
        if not case_sensitive:
            normalized_text = normalized_text.lower()
            normalized_query = normalized_query.lower()
        
        results = []
        start = 0
        while True:
            pos = normalized_text.find(normalized_query, start)
            if pos == -1:
                break
            
            # 簡易的な時間計算（文字位置から推定）
            if transcription_result.segments:
                total_duration = transcription_result.segments[-1].end
                char_duration = total_duration / len(normalized_text) if normalized_text else 0
                time_range = TimeRange(
                    start=pos * char_duration,
                    end=(pos + len(normalized_query)) * char_duration
                )
                results.append((full_text[pos:pos + len(query)], time_range))
            
            start = pos + 1
        
        return results
    
    def split_text_by_separator(self, text: str, separator: str = None) -> List[str]:
        """区切り文字でテキストを分割"""
        if separator is None:
            separator = self.DEFAULT_SEPARATOR
        
        # 区切り文字で分割
        sections = text.split(separator)
        
        # 空のセクションを除去し、前後の空白を削除
        sections = [section.strip() for section in sections if section.strip()]
        
        return sections
    
    def find_differences_with_separator(
        self,
        source_text: str,
        target_text: str,
        transcription_result: TranscriptionResult,
        separator: str = None,
        skip_normalization: bool = False
    ) -> Optional[TextDifference]:
        """区切り文字に対応した差分検索"""
        if separator is None:
            separator = self.DEFAULT_SEPARATOR
        
        # TranscriptionResultが渡された場合、CharacterArrayBuilderで構築したテキストを使用
        if transcription_result:
            # キャッシュをチェック
            if self._transcription_result != transcription_result:
                from domain.use_cases.character_array_builder import CharacterArrayBuilder
                builder = CharacterArrayBuilder()
                _, self._char_array_text = builder.build_from_transcription(transcription_result)
                self._transcription_result = transcription_result
                logger.info(f"CharacterArrayBuilderで再構築: {len(self._char_array_text)}文字")
            
            # CharacterArrayBuilderで構築したテキストを使用
            source_text = self._char_array_text
        
        # 区切り文字で分割
        sections = self.split_text_by_separator(target_text, separator)
        
        all_differences = []
        
        # 各セクションについて個別に差分検索
        for section in sections:
            if not section.strip():
                continue
            
            # セクションの差分を検出
            section_diff = self.find_differences(source_text, section, skip_normalization)
            
            # 結果をマージ
            if section_diff.differences:
                all_differences.extend(section_diff.differences)
        
        if not all_differences:
            return None
        
        return TextDifference(
            id=str(uuid4()),
            original_text=source_text,
            edited_text=target_text,
            differences=all_differences
        )
    
    def remove_boundary_markers(self, text: str) -> str:
        """境界調整マーカーと文脈マーカーを除去"""
        # マーカーパターン（負の数値にも対応）
        import re
        marker_pattern = re.compile(r'\[(-?\d+(?:\.\d+)?)[<>]\]|\[[<>](-?\d+(?:\.\d+)?)\]')
        
        # 境界調整マーカーを除去
        cleaned_text = marker_pattern.sub('', text)
        
        # 文脈マーカーも除去（内容は含める）
        # 注: 検索時には文脈マーカーを含めたいので、ここでは除去しない
        # cleaned_text = self.remove_context_markers(cleaned_text)
        
        # stripのみ実行（空白の正規化はしない）
        return cleaned_text.strip()
    
    def _extract_boundary_markers(self, text: str) -> list[dict]:
        """テキストから境界調整マーカーを抽出"""
        import re
        markers = []
        
        # マーカーパターン
        marker_patterns = [
            (r'\[(-?\d+(?:\.\d+)?)<\]', 'shrink_prev'),   # [1.0<] 前のクリップを縮める
            (r'\[(-?\d+(?:\.\d+)?)>\]', 'extend_prev'),   # [1.0>] 前のクリップを延ばす
            (r'\[<(-?\d+(?:\.\d+)?)\]', 'advance_next'),  # [<1.0] 次のクリップを早める
            (r'\[>(-?\d+(?:\.\d+)?)\]', 'delay_next'),    # [>1.0] 次のクリップを遅らせる
        ]
        
        for pattern, marker_type in marker_patterns:
            for match in re.finditer(pattern, text):
                markers.append({
                    'marker': match.group(0),
                    'type': marker_type,
                    'amount': float(match.group(1)),
                    'position': match.start()
                })
        
        # 位置順にソート
        markers.sort(key=lambda m: m['position'])
        return markers
    
    def extract_existing_markers(self, text: str) -> dict:
        """テキストから既存マーカー情報を抽出"""
        import re
        markers = {}
        lines = text.split('\n')
        
        for line in lines:
            # 例: [<0.5]ハイパー企業ラジオっていう[1.0>]
            start_match = re.search(r'\[<(-?\d+(?:\.\d+)?)\]', line)
            end_match = re.search(r'\[(-?\d+(?:\.\d+)?)>\]', line)
            
            if start_match and end_match:
                # マーカーを除去したテキストを取得
                segment_text = re.sub(r'\[<?-?\d+(?:\.\d+)?>?\]', '', line).strip()
                if segment_text:
                    markers[segment_text] = {
                        'start': float(start_match.group(1)),
                        'end': float(end_match.group(1))
                    }
        
        return markers
    
    def extract_context_markers(self, text: str) -> list[dict]:
        """テキストから文脈マーカー {} を抽出"""
        import re
        markers = []
        
        # {} で囲まれた部分を検索
        pattern = r'\{([^}]+)\}'
        for match in re.finditer(pattern, text):
            markers.append({
                'content': match.group(1),  # {} 内のテキスト
                'full_match': match.group(0),  # {} を含む全体
                'start': match.start(),
                'end': match.end()
            })
        
        logger.debug(f"文脈マーカーを{len(markers)}個検出")
        return markers
    
    def remove_context_markers(self, text: str) -> str:
        """文脈マーカー {} とその内容を削除"""
        import re
        # {} とその中身を削除
        cleaned = re.sub(r'\{[^}]+\}', '', text)
        return cleaned
    
    def remove_context_markers_preserve_positions(self, text: str) -> str:
        """文脈マーカーの内容を空白で置換（位置を保持）"""
        import re
        # {} 内のテキストを同じ長さの空白で置換
        def replace_with_spaces(match):
            return '{' + ' ' * len(match.group(1)) + '}'
        
        return re.sub(r'\{([^}]+)\}', replace_with_spaces, text)
    
    def _exclude_context_marker_ranges(
        self, time_ranges: List[TimeRange], context_markers: list[dict], 
        char_array: list, edited_text: str
    ) -> List[TimeRange]:
        """文脈マーカー部分を時間範囲から除外"""
        new_ranges = []
        
        for time_range in time_ranges:
            # この時間範囲に対応するテキスト位置を特定
            # TODO: より正確な実装が必要
            # 現在は簡易的な実装として、文脈マーカーが含まれる範囲をスキップ
            
            # 文脈マーカーがこの範囲に含まれているかチェック
            contains_marker = False
            for marker in context_markers:
                # マーカーの位置が時間範囲内にあるかを判定
                # （これは簡易的な実装で、より正確な位置マッピングが必要）
                contains_marker = True  # 一旦すべてチェック
            
            if not contains_marker:
                new_ranges.append(time_range)
            else:
                # 文脈マーカーを除外した複数の範囲を生成
                # TODO: 実装を改善
                logger.debug(f"文脈マーカーを含む範囲をスキップ: {time_range.start:.2f} - {time_range.end:.2f}")
        
        return new_ranges