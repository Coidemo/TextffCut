"""
境界調整ユースケース
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import re

from domain.value_objects import TimeRange
from use_cases.base import UseCase
from use_cases.exceptions import TextProcessingError, InvalidTextFormatError
from use_cases.interfaces import ITextProcessorGateway


@dataclass
class AdjustBoundariesRequest:
    """境界調整リクエスト"""
    text_with_markers: str
    time_ranges: List[TimeRange]


@dataclass
class BoundaryAdjustment:
    """境界調整情報"""
    index: int  # 調整対象の時間範囲のインデックス
    adjustment_type: str  # "extend_prev", "shrink_prev", "advance_next", "delay_next"
    amount: float  # 調整量（秒）
    marker: str  # 元のマーカー文字列


@dataclass
class AdjustBoundariesResponse:
    """境界調整レスポンス"""
    cleaned_text: str
    adjusted_time_ranges: List[TimeRange]
    adjustments: List[BoundaryAdjustment]
    
    @property
    def adjustment_count(self) -> int:
        """調整の数"""
        return len(self.adjustments)
    
    @property
    def total_adjustment(self) -> float:
        """調整量の合計（秒）"""
        return sum(adj.amount for adj in self.adjustments)


class AdjustBoundariesUseCase(UseCase[AdjustBoundariesRequest, AdjustBoundariesResponse]):
    """
    境界調整マーカーを解析して時間範囲を調整するユースケース
    
    マーカー記法：
    - [数値>] : 前のクリップを指定秒数延ばす
    - [数値<] : 前のクリップを指定秒数縮める
    - [<数値] : 後のクリップを指定秒数早める
    - [>数値] : 後のクリップを指定秒数遅らせる
    """
    
    # マーカーのパターン
    MARKER_PATTERNS = {
        'extend_prev': re.compile(r'\[(\d+(?:\.\d+)?)>\]'),    # [2>]
        'shrink_prev': re.compile(r'\[(\d+(?:\.\d+)?)<\]'),    # [2<]
        'advance_next': re.compile(r'\[<(\d+(?:\.\d+)?)\]'),   # [<2]
        'delay_next': re.compile(r'\[>(\d+(?:\.\d+)?)\]'),     # [>2]
    }
    
    def __init__(self, text_processor_gateway: ITextProcessorGateway):
        super().__init__()
        self.gateway = text_processor_gateway
    
    def validate_request(self, request: AdjustBoundariesRequest) -> None:
        """リクエストのバリデーション"""
        if not request.text_with_markers:
            raise InvalidTextFormatError("Text is empty")
        
        if not request.time_ranges:
            raise TextProcessingError("No time ranges provided")
    
    def execute(self, request: AdjustBoundariesRequest) -> AdjustBoundariesResponse:
        """境界調整の実行"""
        self.logger.info("Starting boundary adjustment")
        
        try:
            # ゲートウェイを使用して調整を実行
            cleaned_text, adjusted_ranges = self.gateway.apply_boundary_adjustments(
                text=request.text_with_markers,
                time_ranges=request.time_ranges
            )
            
            # 調整情報を抽出（独自実装）
            adjustments = self._extract_adjustments(
                request.text_with_markers,
                request.time_ranges
            )
            
            self.logger.info(
                f"Boundary adjustment completed. "
                f"Adjustments: {len(adjustments)}"
            )
            
            return AdjustBoundariesResponse(
                cleaned_text=cleaned_text,
                adjusted_time_ranges=adjusted_ranges,
                adjustments=adjustments
            )
            
        except TextProcessingError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to adjust boundaries: {str(e)}")
            raise TextProcessingError(
                f"Failed to adjust boundaries: {str(e)}",
                cause=e
            )
    
    def _extract_adjustments(
        self,
        text_with_markers: str,
        original_ranges: List[TimeRange]
    ) -> List[BoundaryAdjustment]:
        """マーカーから調整情報を抽出"""
        adjustments = []
        
        # 各マーカータイプを検索
        for adjustment_type, pattern in self.MARKER_PATTERNS.items():
            for match in pattern.finditer(text_with_markers):
                amount = float(match.group(1))
                marker = match.group(0)
                
                # マーカーの位置から対象インデックスを推定
                position = match.start()
                index = self._estimate_range_index(
                    text_with_markers[:position],
                    len(original_ranges)
                )
                
                # インデックスの調整
                if adjustment_type in ['extend_prev', 'shrink_prev']:
                    # 前のクリップを調整
                    target_index = max(0, index - 1)
                else:
                    # 次のクリップを調整
                    target_index = min(len(original_ranges) - 1, index)
                
                adjustments.append(BoundaryAdjustment(
                    index=target_index,
                    adjustment_type=adjustment_type,
                    amount=amount,
                    marker=marker
                ))
        
        # 位置順にソート
        adjustments.sort(key=lambda a: a.index)
        
        return adjustments
    
    def _estimate_range_index(self, text_before: str, total_ranges: int) -> int:
        """テキスト位置から時間範囲のインデックスを推定"""
        # 簡易的な実装：改行数や文の数から推定
        # より正確にはゲートウェイ側で実装すべき
        lines = text_before.count('\n')
        sentences = text_before.count('。') + text_before.count('.')
        
        # 文または改行の多い方を基準に推定
        estimated = max(lines, sentences)
        
        return min(estimated, total_ranges - 1)