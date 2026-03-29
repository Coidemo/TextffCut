"""
文字配列構築ユースケース

WhisperXの文字起こし結果から、タイムスタンプ付き文字配列を構築する。
"""

from typing import List, Tuple, Dict, Any
import logging

from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from utils.logging import get_logger

logger = get_logger(__name__)


class CharacterArrayBuilder:
    """
    文字配列構築ユースケース

    WhisperXのセグメントとwords配列から、タイムスタンプ付き文字配列を構築する。
    """

    def build_from_transcription(
        self, transcription_result: TranscriptionResult
    ) -> Tuple[List[CharacterWithTimestamp], str]:
        """
        TranscriptionResultから文字配列を構築

        Args:
            transcription_result: 文字起こし結果

        Returns:
            (文字配列, 結合された全文テキスト)
        """
        all_chars = []
        position = 0

        for segment in transcription_result.segments:
            chars_from_segment = self._build_from_segment(segment, position)
            all_chars.extend(chars_from_segment)
            position += len(chars_from_segment)

        # 全文を再構築
        full_text = "".join([c.char for c in all_chars])

        # 検証
        if not self.validate_reconstruction(full_text, transcription_result.text):
            logger.warning(
                f"再構築されたテキストが元のテキストと一致しません: "
                f"再構築={len(full_text)}文字, 元={len(transcription_result.text)}文字"
            )

        logger.info(f"文字配列を構築しました: {len(all_chars)}文字")
        return all_chars, full_text

    def build_from_segments(self, segments: List[Dict[str, Any]]) -> Tuple[List[CharacterWithTimestamp], str]:
        """
        セグメントの辞書リストから文字配列を構築（レガシー互換）

        Args:
            segments: セグメントの辞書リスト

        Returns:
            (文字配列, 結合された全文テキスト)
        """
        all_chars = []
        position = 0

        for segment in segments:
            segment_id = str(segment.get("id", segment.get("start", 0)))

            # wordsフィールドが存在する場合
            if "words" in segment and segment["words"]:
                for word_idx, word in enumerate(segment["words"]):
                    # 日本語では通常1文字ずつ
                    char_info = CharacterWithTimestamp(
                        char=word["word"],
                        start=float(word["start"]),
                        end=float(word["end"]),
                        segment_id=segment_id,
                        word_index=word_idx,
                        original_position=position,
                        confidence=float(word.get("confidence", 1.0)),
                    )
                    all_chars.append(char_info)
                    position += 1
            else:
                # wordsがない場合はセグメントテキストを使用（フォールバック）
                segment_text = segment.get("text", "")
                segment_start = float(segment.get("start", 0))
                segment_end = float(segment.get("end", 0))

                if segment_text and segment_end > segment_start:
                    # 文字を均等に配分
                    char_duration = (segment_end - segment_start) / len(segment_text)
                    for char_idx, char in enumerate(segment_text):
                        char_start = segment_start + char_idx * char_duration
                        char_end = char_start + char_duration

                        char_info = CharacterWithTimestamp(
                            char=char,
                            start=char_start,
                            end=char_end,
                            segment_id=segment_id,
                            word_index=char_idx,
                            original_position=position,
                            confidence=0.5,  # wordsがない場合は信頼度を下げる
                        )
                        all_chars.append(char_info)
                        position += 1

        # 全文を再構築
        full_text = "".join([c.char for c in all_chars])

        logger.info(f"セグメントから文字配列を構築: {len(all_chars)}文字")
        return all_chars, full_text

    def _build_from_segment(self, segment: TranscriptionSegment, start_position: int) -> List[CharacterWithTimestamp]:
        """
        単一セグメントから文字配列を構築

        Args:
            segment: 文字起こしセグメント
            start_position: このセグメントの開始文字位置

        Returns:
            文字配列
        """
        chars = []
        position = start_position

        # wordsが1文字ずつの場合（WhisperX日本語の通常ケース）
        # wordsが1文字超の場合はcharsを使う（MLXアライメントの場合）
        use_words = hasattr(segment, "words") and segment.words
        use_chars_instead = False
        if use_words:
            # wordsの最初の要素が1文字超ならcharsパスを使う
            first_word = segment.words[0]
            word_text = first_word.word if hasattr(first_word, "word") else first_word.get("word", "")
            if len(word_text) > 1:
                use_chars_instead = True

        if use_chars_instead and hasattr(segment, "chars") and segment.chars:
            # charsベースの構築（MLXアライメント: wordsが単語単位の場合）
            for char_idx, char_obj in enumerate(segment.chars):
                if hasattr(char_obj, "char"):
                    char_str = char_obj.char
                    char_start = char_obj.start
                    char_end = char_obj.end
                    char_conf = char_obj.confidence if hasattr(char_obj, "confidence") and char_obj.confidence is not None else 1.0
                else:
                    char_str = char_obj.get("char", "")
                    char_start = char_obj.get("start", 0)
                    char_end = char_obj.get("end", 0)
                    char_conf = char_obj.get("confidence") or char_obj.get("score") or 1.0
                    if isinstance(char_conf, (int, float)) and char_conf < 0:
                        char_conf = 1.0

                char_info = CharacterWithTimestamp(
                    char=char_str,
                    start=char_start,
                    end=char_end,
                    segment_id=segment.id,
                    word_index=char_idx,
                    original_position=position,
                    confidence=char_conf,
                )
                chars.append(char_info)
                position += 1
        elif use_words:
            for word_idx, word in enumerate(segment.words):
                char_info = CharacterWithTimestamp(
                    char=word.word,
                    start=word.start,
                    end=word.end,
                    segment_id=segment.id,
                    word_index=word_idx,
                    original_position=position,
                    confidence=word.confidence if hasattr(word, "confidence") and word.confidence is not None else 1.0,
                )
                chars.append(char_info)
                position += 1
        else:
            # wordsがない場合のフォールバック
            if segment.text and segment.end > segment.start:
                char_duration = (segment.end - segment.start) / len(segment.text)
                for char_idx, char in enumerate(segment.text):
                    char_start = segment.start + char_idx * char_duration
                    char_end = char_start + char_duration

                    char_info = CharacterWithTimestamp(
                        char=char,
                        start=char_start,
                        end=char_end,
                        segment_id=segment.id,
                        word_index=char_idx,
                        original_position=position,
                        confidence=0.5,
                    )
                    chars.append(char_info)
                    position += 1

        return chars

    def validate_reconstruction(self, full_text: str, original_text: str) -> bool:
        """
        再構築されたテキストの妥当性を検証

        Args:
            full_text: 再構築されたテキスト
            original_text: 元のテキスト

        Returns:
            一致する場合True
        """
        # 空白の正規化を考慮した比較
        normalized_full = full_text.strip().replace(" ", "").replace("　", "")
        normalized_original = original_text.strip().replace(" ", "").replace("　", "")

        if normalized_full == normalized_original:
            return True

        # 部分一致も許容（wordsが部分的な場合）
        if normalized_full in normalized_original or normalized_original in normalized_full:
            logger.info("部分一致として検証成功")
            return True

        return False
