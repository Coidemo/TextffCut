"""
LCSベースのテキスト処理ゲートウェイ

LCSアルゴリズムを使用した高精度なテキスト差分検出を提供する。
"""

from typing import List, Optional, Dict, Any, Tuple
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult
from domain.value_objects import TimeRange
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from domain.use_cases.time_range_calculator_lcs import TimeRangeCalculatorLCS
from use_cases.interfaces.text_processor_gateway import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class LCSTextProcessorGateway(ITextProcessorGateway):
    """
    LCSベースのテキスト処理ゲートウェイ
    
    フィラーを含む文字起こしに対して、より正確な差分検出を実現。
    """
    
    def __init__(self):
        self.detector = TextDifferenceDetectorLCS()
        self.calculator = TimeRangeCalculatorLCS()
        self._transcription_result_cache = {}
        logger.info("LCSTextProcessorGatewayを初期化しました")
    
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
            skip_normalization: 正規化をスキップするか（LCSでは未使用）
            
        Returns:
            差分情報
        """
        logger.info("LCSベースの差分検出を開始します")
        
        # LCSベースの差分検出（TranscriptionResultは後で渡す）
        text_difference = self.detector.detect_differences(
            original_text, edited_text, None
        )
        
        # デバッグ情報
        unchanged_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.UNCHANGED)
        deleted_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.DELETED)
        added_count = sum(1 for d in text_difference.differences if d[0] == DifferenceType.ADDED)
        
        logger.info(
            f"差分検出完了: {unchanged_count}個の一致, "
            f"{deleted_count}個の削除, {added_count}個の追加"
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
        
        # 差分ブロックを取得（再計算が必要）
        _, diff_blocks = self.detector.detect_differences_with_blocks(
            text_difference.original_text,
            text_difference.edited_text,
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
        
        # 差分検出とブロック取得
        text_diff, diff_blocks = self.detector.detect_differences_with_blocks(
            transcription_result.text,
            edited_text,
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
    
    def get_deletion_summary(
        self, transcription_result: TranscriptionResult, edited_text: str
    ) -> Dict[str, Any]:
        """
        削除部分のサマリーを生成（UIの確認ダイアログ用）
        
        Args:
            transcription_result: 文字起こし結果
            edited_text: 編集済みテキスト
            
        Returns:
            削除サマリー
        """
        logger.info("削除サマリーの生成を開始します")
        
        # TranscriptionResultをキャッシュ
        self._cache_transcription_result(transcription_result.text, transcription_result)
        
        # 差分検出とブロック取得
        _, diff_blocks = self.detector.detect_differences_with_blocks(
            transcription_result.text,
            edited_text,
            transcription_result
        )
        
        # 削除ブロックのみを抽出
        deletion_blocks = [b for b in diff_blocks if b.type == DifferenceType.DELETED]
        
        # フィラーと内容のある削除を分類
        filler_deletions = []
        content_deletions = []
        
        for block in deletion_blocks:
            if self._is_filler(block.text):
                filler_deletions.append(block)
            else:
                content_deletions.append(block)
        
        # 合計時間を計算
        total_deletion_time = sum(
            b.duration for b in deletion_blocks
            if b.start_time is not None and b.end_time is not None
        )
        
        summary = {
            "total_deletions": len(deletion_blocks),
            "filler_deletions": len(filler_deletions),
            "content_deletions": len(content_deletions),
            "total_deletion_time": total_deletion_time,
            "filler_examples": [b.text for b in filler_deletions[:3]],  # 最初の3つ
            "content_examples": [b.text for b in content_deletions[:3]],  # 最初の3つ
            "deletion_blocks": [
                {
                    "text": b.text,
                    "start_time": b.start_time,
                    "end_time": b.end_time,
                    "is_filler": self._is_filler(b.text)
                }
                for b in deletion_blocks
            ]
        }
        
        logger.info(
            f"削除サマリー: 合計{summary['total_deletions']}個 "
            f"(フィラー{summary['filler_deletions']}個, "
            f"内容{summary['content_deletions']}個)"
        )
        
        return summary
    
    def _is_filler(self, text: str) -> bool:
        """フィラーかどうかを判定"""
        # 一般的な日本語フィラー
        fillers = [
            "えー", "えーっと", "えっと", "あの", "あのー", "その", "そのー",
            "まあ", "ちょっと", "なんか", "こう", "ええ", "うーん", "んー",
            "あー", "うー", "おー"
        ]
        
        # 正規化（句読点を除去）
        normalized = text.strip().replace("、", "").replace("。", "")
        
        return normalized in fillers
    
    def apply_boundary_adjustments(self, text: str, time_ranges: list[TimeRange]) -> tuple[str, list[TimeRange]]:
        """
        境界調整マーカーを適用
        
        Args:
            text: マーカーを含むテキスト
            time_ranges: 元の時間範囲
            
        Returns:
            マーカーを除去したテキストと調整後の時間範囲
        """
        # LCSベースの実装では境界調整は未実装
        # 元のテキストと時間範囲をそのまま返す
        return text, time_ranges
    
    def normalize_text(self, text: str) -> str:
        """
        テキストを正規化
        
        Args:
            text: 正規化するテキスト
            
        Returns:
            正規化されたテキスト
        """
        # LCSベースの実装では正規化は行わない（文字レベルで正確にマッチングするため）
        return text
    
    def search_text(
        self, query: str, transcription_result: TranscriptionResult, case_sensitive: bool = False
    ) -> list[tuple[str, TimeRange]]:
        """
        文字起こし結果からテキストを検索
        
        Args:
            query: 検索クエリ
            transcription_result: 文字起こし結果
            case_sensitive: 大文字小文字を区別するか
            
        Returns:
            マッチしたテキストと時間範囲のリスト
        """
        # シンプルな実装：全文を検索
        text = transcription_result.text
        if not case_sensitive:
            text = text.lower()
            query = query.lower()
        
        results = []
        start = 0
        while True:
            pos = text.find(query, start)
            if pos == -1:
                break
            
            # 簡易的に時間を推定（文字位置から）
            if transcription_result.segments:
                total_duration = transcription_result.segments[-1].end
                char_duration = total_duration / len(text) if text else 0
                time_range = TimeRange(
                    start=pos * char_duration,
                    end=(pos + len(query)) * char_duration
                )
                results.append((transcription_result.text[pos:pos + len(query)], time_range))
            
            start = pos + 1
        
        return results