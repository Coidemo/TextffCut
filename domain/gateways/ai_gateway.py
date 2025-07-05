"""
AI処理ゲートウェイのインターフェース
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from domain.entities.buzz_clip import (
    BuzzClipGenerationRequest,
    BuzzClipGenerationResult,
)


class AIGatewayInterface(ABC):
    """AI処理ゲートウェイのインターフェース"""

    @abstractmethod
    def generate_buzz_clips(
        self, request: BuzzClipGenerationRequest
    ) -> BuzzClipGenerationResult:
        """
        バズる切り抜き候補を生成

        Args:
            request: 生成リクエスト

        Returns:
            生成結果
        """
        pass

    @abstractmethod
    def analyze_text_for_highlights(
        self, text: str, num_highlights: int = 5
    ) -> List[Dict[str, Any]]:
        """
        テキストからハイライトを抽出

        Args:
            text: 分析対象のテキスト
            num_highlights: 抽出するハイライト数

        Returns:
            ハイライトのリスト
        """
        pass

    @abstractmethod
    def check_connection(self) -> bool:
        """
        接続確認

        Returns:
            接続可能かどうか
        """
        pass