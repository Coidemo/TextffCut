"""
文字起こしデータ型変換ユーティリティ

レガシーの文字起こしデータ型とドメインエンティティ間の変換を行います。
"""

from typing import Any, Dict, List, Optional, Union
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
        legacy_result: LegacyResult,
        processing_time: Optional[float] = None
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
                segment = TranscriptionConverter._convert_segment(
                    legacy_seg, 
                    segment_id=f"seg_{i}"
                )
                segments.append(segment)
            
            # TranscriptionResultの作成
            return domain.TranscriptionResult(
                id=str(uuid4()),
                language=legacy_result.language,
                segments=segments,
                original_audio_path=str(legacy_result.original_audio_path),
                model_size=legacy_result.model_size,
                processing_time=processing_time or getattr(legacy_result, 'processing_time', 0.0),
                metadata={
                    "legacy_format": True,
                    "converter_version": "1.0"
                }
            )
        except Exception as e:
            logger.error(f"Failed to convert legacy result to domain: {e}")
            raise ValueError(f"Conversion failed: {e}")
    
    @staticmethod
    def _convert_segment(
        legacy_segment: LegacySegment,
        segment_id: str
    ) -> domain.TranscriptionSegment:
        """セグメントの変換"""
        # Word情報の変換
        words = []
        if legacy_segment.words:
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
            chars=chars
        )
    
    @staticmethod
    def _convert_word(word_data: Union[Dict[str, Any], Any]) -> domain.Word:
        """Word情報の変換"""
        if isinstance(word_data, dict):
            return domain.Word(
                word=word_data.get("word", ""),
                start=float(word_data.get("start", 0)),
                end=float(word_data.get("end", 0)),
                confidence=word_data.get("confidence") or word_data.get("score")
            )
        elif hasattr(word_data, "word"):
            # オブジェクトの場合
            return domain.Word(
                word=word_data.word,
                start=float(word_data.start),
                end=float(word_data.end),
                confidence=getattr(word_data, "confidence", None) or getattr(word_data, "score", None)
            )
        else:
            raise ValueError(f"Unknown word format: {type(word_data)}")
    
    @staticmethod
    def _convert_char(char_data: Union[Dict[str, Any], Any]) -> domain.Char:
        """Char情報の変換"""
        if isinstance(char_data, dict):
            return domain.Char(
                char=char_data.get("char", ""),
                start=float(char_data.get("start", 0)),
                end=float(char_data.get("end", 0)),
                confidence=char_data.get("confidence") or char_data.get("score")
            )
        elif hasattr(char_data, "char"):
            # オブジェクトの場合
            return domain.Char(
                char=char_data.char,
                start=float(char_data.start),
                end=float(char_data.end),
                confidence=getattr(char_data, "confidence", None) or getattr(char_data, "score", None)
            )
        else:
            raise ValueError(f"Unknown char format: {type(char_data)}")
    
    @staticmethod
    def domain_to_legacy_dict(
        domain_result: domain.TranscriptionResult
    ) -> Dict[str, Any]:
        """
        ドメインエンティティからレガシー辞書形式へ変換
        
        キャッシュ保存時などに使用
        
        Args:
            domain_result: ドメインの文字起こし結果
            
        Returns:
            レガシー互換の辞書
        """
        try:
            segments = []
            for segment in domain_result.segments:
                seg_dict = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                }
                
                # Words
                if segment.words:
                    seg_dict["words"] = [
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence
                        }
                        for w in segment.words
                    ]
                
                # Chars
                if segment.chars:
                    seg_dict["chars"] = [
                        {
                            "char": c.char,
                            "start": c.start,
                            "end": c.end,
                            "confidence": c.confidence
                        }
                        for c in segment.chars
                    ]
                
                segments.append(seg_dict)
            
            return {
                "language": domain_result.language,
                "segments": segments,
                "original_audio_path": domain_result.original_audio_path,
                "model_size": domain_result.model_size,
                "processing_time": domain_result.processing_time
            }
        except Exception as e:
            logger.error(f"Failed to convert domain result to legacy dict: {e}")
            raise ValueError(f"Conversion failed: {e}")
    
    @staticmethod
    def validate_conversion(
        original: LegacyResult,
        converted: domain.TranscriptionResult
    ) -> bool:
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
            for orig_seg, conv_seg in zip(original.segments, converted.segments):
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