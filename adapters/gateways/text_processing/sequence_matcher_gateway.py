"""
SequenceMatcherベースのテキスト処理ゲートウェイ（修正版）

文脈マーカー処理の問題を修正した実装。
"""

from difflib import SequenceMatcher
from typing import List, Optional, Tuple, Dict
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
    
    修正版：文脈マーカー処理を正しく実装
    """
    
    def __init__(self):
        logger.info("SequenceMatcherTextProcessorGatewayを初期化しました")
        self.DEFAULT_SEPARATOR = "---"
        self._transcription_result = None
        self._char_array_text = None
    
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
    
    def normalize_with_position_tracking(self, text: str, markers: List[dict] = None) -> Tuple[str, List[dict], List[int]]:
        """
        テキストを正規化しながら位置を追跡
        
        Args:
            text: 正規化するテキスト
            markers: 更新する位置情報を持つマーカーのリスト（オプション）
            
        Returns:
            (正規化されたテキスト, 更新されたマーカー, 位置マッピング)
        """
        normalized = ""
        pos_map = []  # 元の位置 → 正規化後の位置のマッピング
        
        for i, char in enumerate(text):
            if char not in ' 　\n\r':  # スペース・改行以外
                pos_map.append(len(normalized))
                normalized += char
            else:
                pos_map.append(len(normalized))  # スペースは次の文字と同じ位置
        
        # 最後の位置を追加
        pos_map.append(len(normalized))
        
        # マーカー位置を更新
        updated_markers = []
        if markers:
            for marker in markers:
                # 正規化後の位置を計算
                new_start = pos_map[marker['start']] if marker['start'] < len(pos_map) else len(normalized)
                new_end = pos_map[marker['end']] if marker['end'] < len(pos_map) else len(normalized)
                
                # 内容も正規化
                normalized_content = self.normalize_for_comparison(marker['content'])
                
                updated_markers.append({
                    'content': normalized_content,
                    'full_match': marker.get('full_match', ''),
                    'start': new_start,
                    'end': new_end,
                    'original_start': marker['start'],  # 元の位置も保持
                    'original_end': marker['end']
                })
        
        return normalized, updated_markers, pos_map
    
    def find_differences(
        self,
        original_text: str,
        edited_text: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        元のテキストと編集後のテキストの差分を検出
        
        修正版アプローチ：
        1. 文脈マーカーの位置を記録
        2. 正規化（スペース削除）しながら位置を追跡
        3. 文脈マーカーを削除（{}だけを削除、中身は残す）
        4. 差分検出
        5. 差分検出結果を文脈マーカー位置で分割
        """
        logger.info("SequenceMatcherベースの差分検出を開始します（修正版）")
        import time
        
        try:
            # CharacterArrayBuilderで構築したテキストが利用可能な場合は使用
            if self._char_array_text is not None:
                logger.info(f"CharacterArrayBuilderのテキストを使用: {len(self._char_array_text)}文字")
                original_text = self._char_array_text
            
            # 編集テキストの前処理
            # 1. 境界調整マーカーを除去
            cleaned_edited = self.remove_boundary_markers(edited_text)
            
            # 2. 文脈マーカーを抽出（元の位置で）
            context_markers_original = self.extract_context_markers(cleaned_edited)
            logger.info(f"[find_differences] 文脈マーカー検出: {len(context_markers_original)}個")
            
            # 3. 正規化しながら位置を追跡
            normalized_edited, context_markers_normalized, pos_map = self.normalize_with_position_tracking(
                cleaned_edited, context_markers_original
            )
            logger.info(f"正規化後: {len(normalized_edited)}文字")
            
            # 4. 文脈マーカーを削除（{}だけを削除、中身は残す）
            comparison_text = normalized_edited
            
            # {}の位置を記録（削除前）
            bracket_positions = []
            for marker in context_markers_normalized:
                # { の位置
                bracket_positions.append(marker['start'])
                # } の位置（内容の長さを考慮）
                bracket_positions.append(marker['start'] + len(marker['content']) + 1)
            
            # {}を削除（逆順で処理）
            for marker in sorted(context_markers_normalized, key=lambda m: m['start'], reverse=True):
                # {} を削除（中身は残す）
                comparison_text = (
                    comparison_text[:marker['start']] + 
                    marker['content'] +
                    comparison_text[marker['end']:]
                )
            
            logger.info(f"文脈マーカー削除後: {len(comparison_text)}文字")
            
            # 文脈マーカーの新しい位置を計算（{}削除後）
            adjusted_markers = []
            offset = 0
            for marker in sorted(context_markers_normalized, key=lambda m: m['start']):
                new_start = marker['start'] - offset
                new_end = new_start + len(marker['content'])
                adjusted_markers.append({
                    'content': marker['content'],
                    'start': new_start,
                    'end': new_end
                })
                offset += 2  # {}の分
            
            # 5. SequenceMatcherで差分検出
            start_time = time.time()
            matcher = SequenceMatcher(None, original_text, comparison_text)
            logger.debug(f"SequenceMatcher作成: {time.time() - start_time:.3f}秒")
            
            # 差分を収集
            differences = []
            
            start_time = time.time()
            opcodes = list(matcher.get_opcodes())
            logger.debug(f"get_opcodes: {time.time() - start_time:.3f}秒")
            
            for tag, i1, i2, j1, j2 in opcodes:
                if tag == 'equal':
                    # 共通部分：文脈マーカーで分割
                    actual_text = original_text[i1:i2]
                    
                    # この範囲を文脈マーカー位置で分割
                    # j1-j2は{}削除後のテキストでの位置
                    ranges_to_keep = self._split_range_excluding_markers(
                        i1, i2, j1, j2, adjusted_markers
                    )
                    
                    # 分割された範囲を差分として追加
                    for orig_start, orig_end in ranges_to_keep:
                        if orig_start < orig_end:  # 有効な範囲のみ
                            actual_text = original_text[orig_start:orig_end]
                            differences.append((
                                DifferenceType.UNCHANGED,
                                actual_text,
                                [(orig_start, orig_end)]
                            ))
                            logger.debug(f"UNCHANGED範囲追加: {orig_start}-{orig_end} '{actual_text}'")
                    
                elif tag == 'delete':
                    # 削除された部分
                    actual_text = original_text[i1:i2]
                    differences.append((
                        DifferenceType.DELETED,
                        actual_text,
                        [(i1, i2)]
                    ))
                    logger.debug(f"DELETED範囲追加: {i1}-{i2} '{actual_text}'")
                    
                elif tag == 'insert':
                    # 追加された部分
                    added_text = comparison_text[j1:j2]
                    differences.append((
                        DifferenceType.ADDED,
                        added_text,
                        None
                    ))
                    logger.debug(f"ADDED範囲追加: '{added_text}'")
                    
                elif tag == 'replace':
                    # 置換された部分（削除と追加に分解）
                    # 削除部分
                    actual_text = original_text[i1:i2]
                    differences.append((
                        DifferenceType.DELETED,
                        actual_text,
                        [(i1, i2)]
                    ))
                    logger.debug(f"DELETED（置換）範囲追加: {i1}-{i2} '{actual_text}'")
                    
                    # 追加部分
                    added_text = comparison_text[j1:j2]
                    differences.append((
                        DifferenceType.ADDED,
                        added_text,
                        None
                    ))
                    logger.debug(f"ADDED（置換）範囲追加: '{added_text}'")
            
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
            
            return result
            
        except Exception as e:
            logger.error(f"差分検出中にエラーが発生しました: {str(e)}", exc_info=True)
            raise
    
    def _split_range_excluding_markers(self, 
                                     orig_start: int, 
                                     orig_end: int,
                                     edit_start: int,
                                     edit_end: int,
                                     markers: List[Dict]) -> List[Tuple[int, int]]:
        """
        範囲を文脈マーカー位置で分割し、マーカー部分を除外
        
        Args:
            orig_start: 元テキストの開始位置
            orig_end: 元テキストの終了位置
            edit_start: 編集テキストの開始位置（{}削除後）
            edit_end: 編集テキストの終了位置（{}削除後）
            markers: 文脈マーカーのリスト（{}削除後の位置）
            
        Returns:
            マーカー部分を除外した範囲のリスト [(start, end), ...]
        """
        # 初期範囲
        ranges = [(orig_start, orig_end, edit_start, edit_end)]
        
        # 各マーカーで分割
        for marker in markers:
            new_ranges = []
            
            for o_start, o_end, e_start, e_end in ranges:
                # マーカーがこの範囲と重なるかチェック
                if marker['start'] >= e_end or marker['end'] <= e_start:
                    # 重ならない
                    new_ranges.append((o_start, o_end, e_start, e_end))
                elif marker['start'] <= e_start and marker['end'] >= e_end:
                    # 完全に含まれる（この範囲は除外）
                    logger.debug(f"範囲 ({o_start}, {o_end}) は文脈マーカーに完全に含まれるため除外")
                elif marker['start'] > e_start and marker['end'] < e_end:
                    # 中間で分割
                    # 前半（マーカーの前）
                    len_before = marker['start'] - e_start
                    if len_before > 0:
                        new_ranges.append((o_start, o_start + len_before, e_start, marker['start']))
                    
                    # 後半（マーカーの後）
                    len_after = e_end - marker['end']
                    if len_after > 0:
                        # 元テキストでの位置を計算
                        # マーカーの長さ分スキップ
                        o_start_after = o_start + (marker['end'] - e_start)
                        new_ranges.append((o_start_after, o_end, marker['end'], e_end))
                elif marker['start'] > e_start:
                    # 後半が重なる
                    len_before = marker['start'] - e_start
                    if len_before > 0:
                        new_ranges.append((o_start, o_start + len_before, e_start, marker['start']))
                else:
                    # 前半が重なる
                    len_after = e_end - marker['end']
                    if len_after > 0:
                        o_start_after = o_start + (marker['end'] - e_start)
                        new_ranges.append((o_start_after, o_end, marker['end'], e_end))
            
            ranges = new_ranges
        
        # 元テキストの範囲のみを返す
        return [(o_start, o_end) for o_start, o_end, _, _ in ranges]
    
    def extract_context_markers(self, text: str) -> List[dict]:
        """文脈マーカー {} を抽出して位置情報を返す"""
        pattern = r'\{([^}]+)\}'
        markers = []
        
        for match in re.finditer(pattern, text):
            markers.append({
                'content': match.group(1),
                'full_match': match.group(0),
                'start': match.start(),
                'end': match.end()
            })
        
        logger.debug(f"文脈マーカーを{len(markers)}個検出しました")
        return markers
    
    def remove_boundary_markers(self, text: str) -> str:
        """境界調整マーカーを除去"""
        # 境界調整マーカーのパターン
        patterns = [
            r'\[<\d+(?:\.\d+)?\]',  # 前方調整: [<0.1]
            r'\[\d+(?:\.\d+)?>\]',  # 後方調整: [0.1>]
        ]
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned)
        
        return cleaned
    
    def remove_spaces(self, text: str) -> str:
        """テキストから空白を除去"""
        return re.sub(r'\s+', '', text)
    
    def find_differences_with_separator(
        self,
        original_text: str,
        edited_text: str,
        separator: str = None
    ) -> TextDifference:
        """区切り文字を考慮した差分検出（未実装）"""
        raise NotImplementedError("区切り文字を考慮した差分検出は未実装です")
    
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
        position_ranges = []  # 文字位置の範囲を先に収集
        range_index = 0  # 実際の時間範囲のインデックス
        
        # まず、全てのUNCHANGED部分の位置範囲を収集
        for i, diff_item in enumerate(text_difference.differences):
            # タプルの長さをチェックして、追加属性があるか確認
            if len(diff_item) >= 4:
                diff_type, text, positions, extra_attrs = diff_item
            else:
                diff_type, text, positions = diff_item
                extra_attrs = None
            
            if diff_type == DifferenceType.UNCHANGED and positions:
                # 文脈マーカー部分は既に除外されているはず
                position_ranges.extend(positions)
        
        # 位置範囲から時間範囲に変換
        for start_pos, end_pos in position_ranges:
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
                    # 境界調整マーカーのチェック（TODO: 境界調整の実装を改善する必要がある）
                    start_adjustment = 0
                    end_adjustment = 0
                    
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
        
        # マージはしない（境界調整を正確に反映するため）
        logger.info(f"時間範囲を計算しました: {len(time_ranges)}個の範囲")
        return time_ranges
    
    def _extract_boundary_markers(self, text: str) -> List[dict]:
        """境界調整マーカーを抽出"""
        markers = []
        
        # 前方調整マーカー
        for match in re.finditer(r'\[<(\d+(?:\.\d+)?)\]', text):
            markers.append({
                'marker': match.group(0),
                'value': float(match.group(1)),
                'position': match.start(),
                'type': 'backward'
            })
        
        # 後方調整マーカー
        for match in re.finditer(r'\[(\d+(?:\.\d+)?)>\]', text):
            markers.append({
                'marker': match.group(0),
                'value': float(match.group(1)),
                'position': match.start(),
                'type': 'forward'
            })
        
        return sorted(markers, key=lambda x: x['position'])