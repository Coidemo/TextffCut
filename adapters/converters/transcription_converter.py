"""
文字起こしデータ型変換ユーティリティ

レガシーの文字起こしデータ型とドメインエンティティ間の変換を行います。
"""

from typing import Any
from uuid import uuid4

import domain.entities as domain
from core.transcription import TranscriptionResult as LegacyResult
from core.transcription import TranscriptionSegment as LegacySegment
from utils.logging import get_logger

logger = get_logger(__name__)


class TranscriptionConverter:
    """文字起こしデータの変換ユーティリティ"""

    @staticmethod
    def legacy_to_domain(
        legacy_result: LegacyResult, processing_time: float | None = None
    ) -> domain.TranscriptionResult:
        """
        レガシー形式からドメインエンティティへ変換

        Args:
            legacy_result: レガシーの文字起こし結果
            processing_time: 処理時間（秒）

        Returns:
            ドメインの文字起こし結果
        """
        try:
            # セグメントの変換
            segments = []
            for i, legacy_seg in enumerate(legacy_result.segments):
                segment = TranscriptionConverter._convert_segment(legacy_seg, segment_id=f"seg_{i}")
                segments.append(segment)

            # TranscriptionResultの作成
            return domain.TranscriptionResult(
                id=str(uuid4()),
                language=legacy_result.language,
                segments=segments,
                original_audio_path=str(legacy_result.original_audio_path),
                model_size=legacy_result.model_size,
                processing_time=processing_time or getattr(legacy_result, "processing_time", 0.0),
                metadata={"legacy_format": True, "converter_version": "1.0"},
            )
        except Exception as e:
            logger.error(f"Failed to convert legacy result to domain: {e}")
            raise ValueError(f"Conversion failed: {e}")

    @staticmethod
    def _convert_segment(legacy_segment: LegacySegment, segment_id: str) -> domain.TranscriptionSegment:
        """セグメントの変換"""
        # Word情報の変換
        words = []
        logger.debug(
            f"Legacy segment has words: {hasattr(legacy_segment, 'words')}, "
            f"words value: {legacy_segment.words if hasattr(legacy_segment, 'words') else 'N/A'}"
        )
        if hasattr(legacy_segment, "words") and legacy_segment.words:
            logger.debug(f"Converting {len(legacy_segment.words)} words")
            for word_data in legacy_segment.words:
                word = TranscriptionConverter._convert_word(word_data)
                words.append(word)

        # Char情報の変換
        chars = []
        if legacy_segment.chars:
            for char_data in legacy_segment.chars:
                char = TranscriptionConverter._convert_char(char_data)
                chars.append(char)

        return domain.TranscriptionSegment(
            id=segment_id,
            text=legacy_segment.text,
            start=legacy_segment.start,
            end=legacy_segment.end,
            words=words,
            chars=chars,
        )

    @staticmethod
    def _convert_word(word_data: dict[str, Any] | Any) -> domain.Word:
        """Word情報の変換"""
        if isinstance(word_data, dict):
            start = float(word_data.get("start") or 0)
            end = float(word_data.get("end") or 0)
            # start と end が同じ場合、微小な差を追加
            if end <= start:
                end = start + 0.001
            return domain.Word(
                word=word_data.get("word", ""),
                start=start,
                end=end,
                confidence=word_data.get("confidence") or word_data.get("score"),
            )
        elif hasattr(word_data, "word"):
            # オブジェクトの場合
            start = float(word_data.start if word_data.start is not None else 0)
            end = float(word_data.end if word_data.end is not None else 0)
            # start と end が同じ場合、微小な差を追加
            if end <= start:
                end = start + 0.001
            return domain.Word(
                word=word_data.word,
                start=start,
                end=end,
                confidence=getattr(word_data, "confidence", None) or getattr(word_data, "score", None),
            )
        else:
            raise ValueError(f"Unknown word format: {type(word_data)}")

    @staticmethod
    def _convert_char(char_data: dict[str, Any] | Any) -> domain.Char:
        """Char情報の変換"""
        if isinstance(char_data, dict):
            start = float(char_data.get("start") or 0)
            end = float(char_data.get("end") or 0)
            # start と end が同じ場合、微小な差を追加
            if end <= start:
                end = start + 0.001
            return domain.Char(
                char=char_data.get("char", ""),
                start=start,
                end=end,
                confidence=char_data.get("confidence") or char_data.get("score"),
            )
        elif hasattr(char_data, "char"):
            # オブジェクトの場合
            start = float(char_data.start if char_data.start is not None else 0)
            end = float(char_data.end if char_data.end is not None else 0)
            # start と end が同じ場合、微小な差を追加
            if end <= start:
                end = start + 0.001
            return domain.Char(
                char=char_data.char,
                start=start,
                end=end,
                confidence=getattr(char_data, "confidence", None) or getattr(char_data, "score", None),
            )
        else:
            raise ValueError(f"Unknown char format: {type(char_data)}")

    @staticmethod
    def domain_to_legacy_dict(domain_result: domain.TranscriptionResult) -> dict[str, Any]:
        """
        ドメインエンティティからレガシー辞書形式へ変換

        キャッシュ保存時などに使用

        Args:
            domain_result: ドメインの文字起こし結果

        Returns:
            レガシー互換の辞書
        """
        try:
            logger.debug(f"domain_to_legacy_dict called with type: {type(domain_result)}")
            logger.debug(f"domain_result.segments type: {type(domain_result.segments)}")
            if domain_result.segments:
                logger.debug(f"First segment type: {type(domain_result.segments[0])}")
                first_seg = domain_result.segments[0]
                if isinstance(first_seg, dict):
                    logger.debug(f"First segment is dict with keys: {list(first_seg.keys())}")
                else:
                    logger.debug(f"First segment is object: {first_seg.__class__.__name__}")
                    
            segments = []
            for i, segment in enumerate(domain_result.segments):
                # segmentが辞書の場合とTranscriptionSegmentオブジェクトの場合の両方に対応
                if isinstance(segment, dict):
                    seg_dict = {
                        "start": segment.get("start", 0),
                        "end": segment.get("end", 0),
                        "text": segment.get("text", "")
                    }
                    # words と chars も辞書から取得
                    if "words" in segment:
                        seg_dict["words"] = segment["words"]
                    if "chars" in segment:
                        seg_dict["chars"] = segment["chars"]
                else:
                    # TranscriptionSegmentオブジェクトの場合
                    seg_dict = {"start": segment.start, "end": segment.end, "text": segment.text}

                    # Words
                    if hasattr(segment, "words") and segment.words:
                        seg_dict["words"] = [
                            {"word": w.word, "start": w.start, "end": w.end, "confidence": w.confidence}
                            for w in segment.words
                        ]

                    # Chars
                    if hasattr(segment, "chars") and segment.chars:
                        seg_dict["chars"] = [
                            {"char": c.char, "start": c.start, "end": c.end, "confidence": c.confidence}
                            for c in segment.chars
                        ]

                segments.append(seg_dict)

            return {
                "language": domain_result.language,
                "segments": segments,
                "original_audio_path": domain_result.original_audio_path,
                "model_size": domain_result.model_size,
                "processing_time": domain_result.processing_time,
            }
        except Exception as e:
            logger.error(f"Failed to convert domain result to legacy dict: {e}")
            raise ValueError(f"Conversion failed: {e}")

    @staticmethod
    def validate_conversion(original: LegacyResult, converted: domain.TranscriptionResult) -> bool:
        """
        変換の妥当性を検証

        Args:
            original: 元のレガシー結果
            converted: 変換後のドメイン結果

        Returns:
            検証が成功したかどうか
        """
        try:
            # 基本属性の検証
            if original.language != converted.language:
                logger.error(f"Language mismatch: {original.language} != {converted.language}")
                return False

            if len(original.segments) != len(converted.segments):
                logger.error(f"Segment count mismatch: {len(original.segments)} != {len(converted.segments)}")
                return False

            # セグメントの検証
            for orig_seg, conv_seg in zip(original.segments, converted.segments, strict=False):
                if orig_seg.text != conv_seg.text:
                    logger.error(f"Text mismatch: {orig_seg.text} != {conv_seg.text}")
                    return False

                if abs(orig_seg.start - conv_seg.start) > 0.001:
                    logger.error(f"Start time mismatch: {orig_seg.start} != {conv_seg.start}")
                    return False

                if abs(orig_seg.end - conv_seg.end) > 0.001:
                    logger.error(f"End time mismatch: {orig_seg.end} != {conv_seg.end}")
                    return False

            return True
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
