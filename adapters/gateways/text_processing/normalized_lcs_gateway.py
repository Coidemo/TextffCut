"""
正規化機能付きLCSテキスト処理ゲートウェイ

音声認識特有の揺れ（改行、スペース、句読点）を吸収して、
より実用的な差分検出を実現する。
"""

from typing import List, Optional, Dict, Any, Tuple
import re
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult
from domain.value_objects import TimeRange
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from domain.use_cases.time_range_calculator_lcs import TimeRangeCalculatorLCS
from use_cases.interfaces.text_processor_gateway import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class NormalizedLCSTextProcessorGateway(ITextProcessorGateway):
    """
    正規化機能付きLCSベースのテキスト処理ゲートウェイ
    
    音声認識の揺れを吸収しながら、正確な差分検出を実現。
    """
    
    def __init__(self):
        self.detector = TextDifferenceDetectorLCS()
        self.calculator = TimeRangeCalculatorLCS()
        self._transcription_result_cache = {}
        logger.info("NormalizedLCSTextProcessorGatewayを初期化しました")
    
    def normalize_for_comparison(self, text: str) -> str:
        """
        比較用にテキストを正規化
        
        音声認識特有の揺れを吸収：
        - 改行を除去
        - スペースを除去（日本語では不要）
        - 句読点の統一
        
        Args:
            text: 正規化するテキスト
            
        Returns:
            正規化されたテキスト
        """
        # 改行を除去
        normalized = text.replace('\n', '').replace('\r', '')
        
        # 全角スペースを半角に統一
        normalized = normalized.replace('　', ' ')
        
        # 日本語テキストの場合、単語間のスペースは音声認識の揺れなので除去
        # ただし、英数字の前後のスペースは保持する必要がある場合があるため、
        # 日本語文字間のスペースのみ除去
        normalized = re.sub(r'([ぁ-んァ-ヶー一-龯])\s+([ぁ-んァ-ヶー一-龯])', r'\1\2', normalized)
        
        # 先頭・末尾のスペースを除去
        normalized = normalized.strip()
        
        # 句読点の正規化（音声認識では句読点の有無が不安定）
        # 句読点の後のスペースを除去
        normalized = re.sub(r'([、。])\s*', r'\1', normalized)
        
        return normalized
    
    def find_differences(
        self,
        original_text: str,
        edited_text: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        文字起こし結果と編集済みテキストの差分を検出
        
        Args:
            original_text: 元のテキスト
            edited_text: 編集済みテキスト
            skip_normalization: 正規化をスキップするか
            
        Returns:
            差分情報
        """
        logger.info("正規化付きLCSベースの差分検出を開始します")
        
        # 正規化を適用
        if not skip_normalization:
            normalized_original = self.normalize_for_comparison(original_text)
            normalized_edited = self.normalize_for_comparison(edited_text)
            
            logger.info(f"正規化前: 元{len(original_text)}文字, 編集{len(edited_text)}文字")
            logger.info(f"正規化後: 元{len(normalized_original)}文字, 編集{len(normalized_edited)}文字")
        else:
            normalized_original = original_text
            normalized_edited = edited_text
        
        # LCSベースの差分検出（正規化されたテキストで比較）
        text_difference = self.detector.detect_differences(
            normalized_original, normalized_edited, None
        )
        
        # 元のテキストを保持（UIでの表示用）
        text_difference.original_text = original_text
        text_difference.edited_text = edited_text
        
        # デバッグ情報
        unchanged_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.UNCHANGED)
        deleted_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.DELETED)
        added_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.ADDED)
        
        logger.info(
            f"差分検出完了: {unchanged_count}個の一致, "
            f"{deleted_count}個の削除, {added_count}個の追加"
        )
        
        # 差分が多すぎる場合の警告
        if len(text_difference.differences) > 10:
            logger.warning(
                f"差分が細かすぎる可能性があります（{len(text_difference.differences)}個）。"
                f"音声認識の揺れが原因かもしれません。"
            )
        
        return text_difference
    
    def get_time_ranges(
        self, text_difference: TextDifference, transcription_result: TranscriptionResult
    ) -> List[TimeRange]:
        """
        差分情報から時間範囲を計算
        
        Args:
            text_difference: 差分情報
            transcription_result: 文字起こし結果
            
        Returns:
            時間範囲のリスト
        """
        logger.info("時間範囲の計算を開始します")
        
        # 元のテキストを正規化して比較
        normalized_original = self.normalize_for_comparison(transcription_result.text)
        
        # 差分ブロックを取得（再計算が必要）
        _, diff_blocks = self.detector.detect_differences_with_blocks(
            normalized_original,
            self.normalize_for_comparison(text_difference.edited_text),
            transcription_result
        )
        
        # 時間範囲を計算
        time_ranges = self.calculator.calculate_from_blocks(diff_blocks)
        
        # マージ（隣接する範囲を結合）
        merged_ranges = self.calculator.merge_adjacent_ranges(time_ranges, gap_threshold=0.5)
        
        # TimeRangeオブジェクトに変換
        result = [TimeRange(start=r.start, end=r.end) for r in merged_ranges]
        
        logger.info(f"時間範囲を計算しました: {len(result)}個の範囲")
        return result
    
    # 以下、他のメソッドは元のLCSTextProcessorGatewayと同じ
    def apply_boundary_adjustments(self, text: str, time_ranges: list[TimeRange]) -> tuple[str, list[TimeRange]]:
        """境界調整マーカーを適用"""
        return text, time_ranges
    
    def normalize_text(self, text: str) -> str:
        """テキストを正規化（このメソッドは比較用の正規化を行う）"""
        return self.normalize_for_comparison(text)
    
    def search_text(
        self, query: str, transcription_result: TranscriptionResult, case_sensitive: bool = False
    ) -> list[tuple[str, TimeRange]]:
        """文字起こし結果からテキストを検索"""
        # 正規化して検索
        normalized_text = self.normalize_for_comparison(transcription_result.text)
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
            
            # 簡易的に時間を推定
            if transcription_result.segments:
                total_duration = transcription_result.segments[-1].end
                char_duration = total_duration / len(normalized_text) if normalized_text else 0
                time_range = TimeRange(
                    start=pos * char_duration,
                    end=(pos + len(normalized_query)) * char_duration
                )
                # 元のテキストから該当部分を取得（正規化前）
                results.append((transcription_result.text[pos:pos + len(query)], time_range))
            
            start = pos + 1
        
        return results
    
    def _is_filler(self, text: str) -> bool:
        """フィラーかどうかを判定"""
        fillers = [
            "えー", "えーっと", "えっと", "あの", "あのー", "その", "そのー",
            "まあ", "ちょっと", "なんか", "こう", "ええ", "うーん", "んー",
            "あー", "うー", "おー"
        ]
        normalized = text.strip().replace("、", "").replace("。", "")
        return normalized in fillers
    
    def _cache_transcription_result(self, text: str, transcription_result: TranscriptionResult):
        """
        TranscriptionResultをキャッシュ
        
        get_highlight_dataやget_deletion_summaryで使用するため
        """
        self._transcription_result_cache[text] = transcription_result
    
    def get_highlight_data(
        self, transcription_result: TranscriptionResult, edited_text: str
    ) -> List[Dict[str, Any]]:
        """
        UI用のハイライトデータを生成
        
        Args:
            transcription_result: 文字起こし結果
            edited_text: 編集済みテキスト
            
        Returns:
            ハイライトデータのリスト
        """
        logger.info("ハイライトデータの生成を開始します")
        
        # TranscriptionResultをキャッシュ
        self._cache_transcription_result(transcription_result.text, transcription_result)
        
        # 正規化
        normalized_original = self.normalize_for_comparison(transcription_result.text)
        normalized_edited = self.normalize_for_comparison(edited_text)
        
        # 差分検出とブロック取得
        text_diff, diff_blocks = self.detector.detect_differences_with_blocks(
            normalized_original,
            normalized_edited,
            transcription_result
        )
        
        highlight_data = []
        
        for block in diff_blocks:
            # UIで使用するデータ形式に変換
            data = {
                "type": block.type.value,
                "text": block.text,
                "start_pos": block.original_start_pos,
                "end_pos": block.original_end_pos,
            }
            
            # 時間情報がある場合は追加
            if block.start_time is not None and block.end_time is not None:
                data["start_time"] = block.start_time
                data["end_time"] = block.end_time
                data["duration"] = block.duration
            
            # 削除ブロックの場合は追加情報
            if block.type == DifferenceType.DELETED:
                data["is_filler"] = self._is_filler(block.text)
                data["char_count"] = block.char_count
            
            highlight_data.append(data)
        
        logger.info(f"ハイライトデータを生成しました: {len(highlight_data)}個のブロック")
        return highlight_data