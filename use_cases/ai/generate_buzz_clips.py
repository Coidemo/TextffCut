"""
バズる切り抜き候補を生成するユースケース
"""

import logging
from dataclasses import dataclass
from typing import Any

from domain.entities.buzz_clip import (
    BuzzClipCandidate,
    BuzzClipGenerationRequest,
    BuzzClipGenerationResult,
)
from domain.gateways.ai_gateway import AIGatewayInterface
from use_cases.base import UseCase
from use_cases.exceptions import UseCaseError

logger = logging.getLogger(__name__)


@dataclass
class GenerateBuzzClipsRequest:
    """バズクリップ生成リクエスト"""

    transcription_text: str
    transcription_segments: list[dict[str, Any]]
    num_candidates: int = 10
    min_duration: int = 30
    max_duration: int = 40
    categories: list[str] | None = None
    existing_candidates: list[BuzzClipCandidate] | None = None


@dataclass
class GenerateBuzzClipsResponse:
    """バズクリップ生成レスポンス"""

    success: bool
    candidates: list[BuzzClipCandidate]
    processing_time: float
    model_used: str
    usage: dict[str, int]
    error_message: str | None = None


class GenerateBuzzClipsUseCase(UseCase[GenerateBuzzClipsRequest, GenerateBuzzClipsResponse]):
    """バズる切り抜き候補を生成するユースケース"""

    def __init__(self, ai_gateway: AIGatewayInterface):
        """
        初期化

        Args:
            ai_gateway: AI処理ゲートウェイ
        """
        self.ai_gateway = ai_gateway

    def execute(self, request: GenerateBuzzClipsRequest) -> GenerateBuzzClipsResponse:
        """
        バズる切り抜き候補を生成

        Args:
            request: 生成リクエスト

        Returns:
            生成レスポンス
        """
        logger.info(f"Generating buzz clips: num_candidates={request.num_candidates}")

        try:
            # 入力検証
            self._validate_request(request)

            # ドメインエンティティを作成
            domain_request = BuzzClipGenerationRequest(
                transcription_text=request.transcription_text,
                transcription_segments=request.transcription_segments,
                num_candidates=request.num_candidates,
                min_duration=request.min_duration,
                max_duration=request.max_duration,
                categories=request.categories,
                existing_candidates=request.existing_candidates,
            )

            # AI Gatewayを使用して生成
            result = self.ai_gateway.generate_buzz_clips(domain_request)

            # 結果を検証
            self._validate_result(result, request)

            logger.info(
                f"Generated {len(result.candidates)} buzz clip candidates in "
                f"{result.total_processing_time:.2f}s using {result.model_used}"
            )

            return GenerateBuzzClipsResponse(
                success=True,
                candidates=result.candidates,
                processing_time=result.total_processing_time,
                model_used=result.model_used,
                usage=result.usage,
            )

        except UseCaseError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate buzz clips: {e}")
            return GenerateBuzzClipsResponse(
                success=False, candidates=[], processing_time=0.0, model_used="", usage={}, error_message=str(e)
            )

    def _validate_request(self, request: GenerateBuzzClipsRequest) -> None:
        """リクエストを検証"""
        if not request.transcription_text:
            raise UseCaseError("文字起こしテキストが空です")

        if not request.transcription_segments:
            raise UseCaseError("文字起こしセグメントが空です")

        if request.num_candidates < 1:
            raise UseCaseError("候補数は1以上である必要があります")

        if request.min_duration < 10:
            raise UseCaseError("最小時間は10秒以上である必要があります")

        if request.max_duration > 60:
            raise UseCaseError("最大時間は60秒以下である必要があります")

        if request.min_duration >= request.max_duration:
            raise UseCaseError("最小時間は最大時間より小さい必要があります")

    def _validate_result(self, result: BuzzClipGenerationResult, request: GenerateBuzzClipsRequest) -> None:
        """結果を検証"""
        if not result.candidates:
            logger.warning("No buzz clip candidates generated")
            return

        # 各候補を検証
        for i, candidate in enumerate(result.candidates):
            # 時間範囲の検証
            duration = candidate.duration
            if duration < request.min_duration or duration > request.max_duration:
                logger.warning(
                    f"Candidate {i} duration {duration}s is outside requested range "
                    f"[{request.min_duration}, {request.max_duration}]"
                )

            # スコアの検証
            if candidate.score < 0 or candidate.score > 20:
                logger.warning(f"Candidate {i} score {candidate.score} is outside valid range [0, 20]")

            # 時間の妥当性チェック
            if candidate.start_time < 0:
                logger.warning(f"Candidate {i} has negative start time")

            if candidate.end_time <= candidate.start_time:
                logger.warning(f"Candidate {i} has invalid time range")
