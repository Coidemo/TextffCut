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
        
        # 文字単位で差分を検出（difffのようなアルゴリズム）
        differences = self._detect_character_differences(original_text, edited_text)
        
        # 時間情報を付与（必要な場合）
        if transcription_result:
            differences = self._add_time_information(differences, transcription_result, 0)
        
        return TextDifference(
            id=self._generate_id(),
            original_text=original_text,
            edited_text=edited_text,
            differences=differences
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
        
        # 文字単位で比較（LCSアルゴリズムの簡易版）
        # 編集テキストの各部分が元のテキストのどこかに存在するか確認
        current_pos = 0
        current_unchanged = ""
        current_added = ""
        
        for char in edited_text:
            # この文字が元のテキストに存在するか
            if char in original_text:
                # 存在する場合
                if current_added:
                    # それまでの追加文字をADDEDとして記録
                    differences.append((DifferenceType.ADDED, current_added, None))
                    current_added = ""
                current_unchanged += char
            else:
                # 存在しない場合
                if current_unchanged:
                    # それまでの一致文字をUNCHANGEDとして記録
                    differences.append((DifferenceType.UNCHANGED, current_unchanged, None))
                    current_unchanged = ""
                current_added += char
        
        # 最後の部分を記録
        if current_unchanged:
            differences.append((DifferenceType.UNCHANGED, current_unchanged, None))
        if current_added:
            differences.append((DifferenceType.ADDED, current_added, None))
        
        # より精密な差分検出（連続する文字列として存在するか確認）
        return self._refine_differences(original_text, edited_text, differences)
    
    def _refine_differences(
        self, original_text: str, edited_text: str,
        initial_differences: list[tuple[DifferenceType, str, tuple[float, float] | None]]
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """
        初期の差分検出結果を改善
        連続する文字列として元のテキストに存在するか確認
        """
        refined_differences = []
        
        # UNCHANGEDとされた部分が本当に連続して存在するか確認
        for diff_type, text, time_range in initial_differences:
            if diff_type == DifferenceType.UNCHANGED:
                # この文字列が元のテキストに連続して存在するか
                if text in original_text:
                    refined_differences.append((diff_type, text, time_range))
                else:
                    # 連続して存在しない場合は、文字単位で再検査
                    for char in text:
                        if char in original_text:
                            refined_differences.append((DifferenceType.UNCHANGED, char, None))
                        else:
                            refined_differences.append((DifferenceType.ADDED, char, None))
            else:
                refined_differences.append((diff_type, text, time_range))
        
        # 連続する同じ種類の差分をマージ
        return self._merge_consecutive_differences(refined_differences)
    
    def _merge_consecutive_differences(
        self, differences: list[tuple[DifferenceType, str, tuple[float, float] | None]]
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """連続する同じ種類の差分をマージ"""
        if not differences:
            return differences
        
        merged = []
        current_type = differences[0][0]
        current_text = differences[0][1]
        current_time = differences[0][2]
        
        for diff_type, text, time_range in differences[1:]:
            if diff_type == current_type:
                # 同じ種類なのでマージ
                current_text += text
            else:
                # 種類が変わったので、これまでの分を記録
                merged.append((current_type, current_text, current_time))
                current_type = diff_type
                current_text = text
                current_time = time_range
        
        # 最後の部分を記録
        merged.append((current_type, current_text, current_time))
        
        return merged


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
