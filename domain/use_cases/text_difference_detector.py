"""
テキスト差分検出のユースケース

テキストの差分を検出するビジネスロジックを実装。
ドメインエンティティのみを使用し、レガシー形式は扱わない。
"""

from dataclasses import dataclass

from domain.entities.text_difference import DifferenceType, TextDifference
from domain.entities.transcription import TranscriptionResult
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TextRange:
    """テキスト内の範囲"""

    start: int
    end: int
    text: str


class TextDifferenceDetector:
    """
    テキスト差分検出ユースケース

    編集前後のテキストを比較し、差分を検出する。
    """

    def detect_differences(
        self, original_text: str, edited_text: str, transcription_result: TranscriptionResult | None = None
    ) -> TextDifference:
        """
        テキストの差分を検出

        Args:
            original_text: 元のテキスト（文字起こし結果）
            edited_text: 編集後のテキスト（切り抜き指定）
            transcription_result: 文字起こし結果（時間情報用）

        Returns:
            差分情報
        """
        logger.info(f"差分検出開始: 元{len(original_text)}文字 vs 編集{len(edited_text)}文字")

        # デバッグ：編集テキストが元のテキストに含まれているか確認
        if edited_text in original_text:
            logger.info("✅ 編集テキストは元のテキストに完全に含まれています")
        else:
            logger.warning("⚠️ 編集テキストが元のテキストに完全には含まれていません")
            # 最初の50文字を確認
            logger.debug(f"元のテキスト冒頭: {repr(original_text[:100])}")
            logger.debug(f"編集テキスト冒頭: {repr(edited_text[:100])}")

        # 文字単位で差分を検出（difffのようなアルゴリズム）
        differences = self._detect_character_differences(original_text, edited_text)

        # 時間情報を付与（必要な場合）
        if transcription_result:
            differences = self._add_time_information(differences, transcription_result, 0)

        return TextDifference(
            id=self._generate_id(), original_text=original_text, edited_text=edited_text, differences=differences
        )

    def _detect_character_differences(
        self, original_text: str, edited_text: str
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """
        文字単位で差分を検出（difffのようなアルゴリズム）

        Args:
            original_text: 元のテキスト（文字起こし結果）
            edited_text: 編集テキスト（切り抜き指定）

        Returns:
            差分リスト（種別, テキスト, 時間範囲）
        """
        differences = []

        if not edited_text:
            # 編集テキストが空の場合
            return differences

        # 編集テキストが元のテキストにそのまま含まれている場合（最も一般的）
        if edited_text in original_text:
            logger.info("編集テキストが元のテキストに完全に含まれています")
            differences.append((DifferenceType.UNCHANGED, edited_text, None))
            return differences

        # 最長共通部分文字列アプローチで差分を検出
        # 編集テキストの各部分が元のテキストに連続して存在するか確認
        current_pos = 0  # edited_text内の現在位置

        while current_pos < len(edited_text):
            # 現在位置から始まる最長の一致部分を探す
            best_match_len = 0
            best_match_text = ""

            # 様々な長さの部分文字列を試す
            for length in range(len(edited_text) - current_pos, 0, -1):
                substr = edited_text[current_pos : current_pos + length]
                if substr in original_text:
                    best_match_len = length
                    best_match_text = substr
                    break

            if best_match_len > 0:
                # 一致する部分が見つかった
                differences.append((DifferenceType.UNCHANGED, best_match_text, None))
                current_pos += best_match_len
            else:
                # 一致しない文字（追加文字）
                # 次に一致する部分まで、または最後まで追加文字として扱う
                added_text = ""
                while current_pos < len(edited_text):
                    # 次の文字から始まる部分が元のテキストに存在するか確認
                    found_match = False
                    for length in range(len(edited_text) - current_pos, 0, -1):
                        if current_pos + 1 < len(edited_text):
                            substr = edited_text[current_pos + 1 : current_pos + 1 + length]
                            if substr in original_text and len(substr) > 3:  # 3文字以上の一致を探す
                                found_match = True
                                break

                    if found_match:
                        # 次の位置から一致が見つかったので、現在の文字は追加文字
                        added_text += edited_text[current_pos]
                        differences.append((DifferenceType.ADDED, added_text, None))
                        current_pos += 1
                        break
                    else:
                        # 追加文字を継続
                        added_text += edited_text[current_pos]
                        current_pos += 1

                # 最後まで一致しなかった場合
                if added_text and not any(d[1] == added_text for d in differences if d[0] == DifferenceType.ADDED):
                    differences.append((DifferenceType.ADDED, added_text, None))

        logger.info(f"差分検出結果: {len(differences)}個の差分")
        for diff_type, text, _ in differences:
            logger.debug(f"  {diff_type.value}: {repr(text[:50])}...")

        return differences

    def _add_time_information(
        self,
        differences: list[tuple[DifferenceType, str, tuple[float, float] | None]],
        transcription_result: TranscriptionResult,
        offset: int,
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """差分に時間情報を付与"""
        # TODO: 実装が必要
        # 現在は時間情報なしで返す
        return differences

    def _generate_id(self) -> str:
        """ID生成"""
        from uuid import uuid4

        return str(uuid4())
