"""
テキスト処理データ型変換ユーティリティ

レガシーのテキスト処理データ型とドメインエンティティ間の変換を行います。
"""

from uuid import uuid4

import domain.entities as domain
import domain.value_objects as vo
from core.text_processor import TextDifference as LegacyTextDifference
from domain.entities.text_difference import DifferenceType
from utils.logging import get_logger

logger = get_logger(__name__)


class TextConverter:
    """テキスト処理データの変換ユーティリティ"""

    @staticmethod
    def legacy_difference_to_domain(legacy_diff: LegacyTextDifference) -> domain.TextDifference:
        """
        レガシーのTextDifferenceからドメインエンティティへ変換

        Args:
            legacy_diff: レガシーの差分情報

        Returns:
            ドメインの差分情報
        """
        try:
            differences = []

            # 共通部分（変更なし）を変換
            for pos in legacy_diff.common_positions:
                differences.append((DifferenceType.UNCHANGED, pos.text, None))  # 時間範囲は後で計算される

            # 追加部分を変換
            if legacy_diff.added_positions:
                for pos in legacy_diff.added_positions:
                    differences.append((DifferenceType.ADDED, pos.text, None))
            elif legacy_diff.added_chars:
                # added_positionsがない場合は、added_charsから単一の追加として扱う
                added_text = "".join(legacy_diff.added_chars)
                if added_text:
                    differences.append((DifferenceType.ADDED, added_text, None))

            # 削除部分の検出（元のテキストにあって編集後にない部分）
            # 簡易実装：この変換では削除は検出しない（レガシー実装に依存）

            return domain.TextDifference(
                id=str(uuid4()),
                original_text=legacy_diff.original_text,
                edited_text=legacy_diff.edited_text,
                differences=differences,
            )
        except Exception as e:
            logger.error(f"Failed to convert legacy TextDifference: {e}")
            raise ValueError(f"Conversion failed: {e}")

    @staticmethod
    def time_ranges_to_domain(time_ranges: list[tuple[float, float]]) -> list[vo.TimeRange]:
        """
        時間範囲のタプルリストをドメインのTimeRangeリストに変換

        Args:
            time_ranges: [(start, end), ...] 形式の時間範囲

        Returns:
            TimeRangeオブジェクトのリスト
        """
        domain_ranges = []
        for start, end in time_ranges:
            try:
                domain_ranges.append(vo.TimeRange(start=start, end=end))
            except ValueError as e:
                logger.warning(f"Invalid time range ({start}, {end}): {e}")
                # 無効な範囲はスキップ
                continue

        return domain_ranges

    @staticmethod
    def domain_to_time_ranges(domain_ranges: list[vo.TimeRange]) -> list[tuple[float, float]]:
        """
        ドメインのTimeRangeリストをタプルリストに変換

        Args:
            domain_ranges: TimeRangeオブジェクトのリスト

        Returns:
            [(start, end), ...] 形式の時間範囲
        """
        return [(tr.start, tr.end) for tr in domain_ranges]

    @staticmethod
    def adjusted_segments_to_domain(segments: list[dict], markers: list[str]) -> list[domain.TranscriptionSegment]:
        """
        調整済みセグメントをドメインエンティティに変換

        Args:
            segments: 調整済みセグメントの辞書リスト
            markers: 使用されたマーカー文字列

        Returns:
            TranscriptionSegmentのリスト
        """
        domain_segments = []

        for i, seg in enumerate(segments):
            try:
                # 必要なフィールドの存在確認
                if not all(key in seg for key in ["start", "end", "text"]):
                    logger.warning(f"Segment {i} missing required fields, skipping")
                    continue

                # Wordsの変換
                words = None
                if "words" in seg and seg["words"]:
                    words = []
                    for w in seg["words"]:
                        word = domain.Word(
                            word=w.get("word", ""),
                            start=float(w.get("start", 0)),
                            end=float(w.get("end", 0)),
                            confidence=w.get("confidence") or w.get("score"),
                        )
                        words.append(word)

                # Charsの変換
                chars = None
                if "chars" in seg and seg["chars"]:
                    chars = []
                    for c in seg["chars"]:
                        char = domain.Char(
                            char=c.get("char", ""),
                            start=float(c.get("start", 0)),
                            end=float(c.get("end", 0)),
                            confidence=c.get("confidence") or c.get("score"),
                        )
                        chars.append(char)

                segment = domain.TranscriptionSegment(
                    id=seg.get("id", f"adjusted_seg_{i}"),
                    text=seg["text"],
                    start=float(seg["start"]),
                    end=float(seg["end"]),
                    words=words,
                    chars=chars,
                )

                domain_segments.append(segment)

            except Exception as e:
                logger.error(f"Failed to convert segment {i}: {e}")
                continue

        return domain_segments
