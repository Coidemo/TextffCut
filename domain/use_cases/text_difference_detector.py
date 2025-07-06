"""
テキスト差分検出のユースケース

テキストの差分を検出するビジネスロジックを実装。
ドメインエンティティのみを使用し、レガシー形式は扱わない。
"""

from dataclasses import dataclass
from typing import Any

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
        self,
        original_text: str,
        edited_text: str,
        transcription_result: TranscriptionResult | None = None
    ) -> TextDifference:
        """
        テキストの差分を検出
        
        Args:
            original_text: 元のテキスト
            edited_text: 編集後のテキスト
            transcription_result: 文字起こし結果（時間情報用）
            
        Returns:
            差分情報
        """
        # 編集テキストが元のテキストの抜粋である場合を検出
        if len(edited_text) < len(original_text) * 0.8:
            return self._detect_excerpt_differences(
                original_text, edited_text, transcription_result
            )
        
        # 通常の差分検出
        return self._detect_full_differences(
            original_text, edited_text, transcription_result
        )
    
    def _detect_excerpt_differences(
        self,
        original_text: str,
        edited_text: str,
        transcription_result: TranscriptionResult | None
    ) -> TextDifference:
        """抜粋テキストの差分を検出"""
        logger.info(f"抜粋として処理: 編集{len(edited_text)}文字 vs 元{len(original_text)}文字")
        
        # 句読点を除去して位置を特定
        edited_no_punct = self._remove_punctuation(edited_text)
        position = original_text.find(edited_no_punct)
        
        if position == -1:
            # スペースの違いを考慮して再検索
            original_no_space = original_text.replace(" ", "")
            edited_no_space = edited_no_punct.replace(" ", "")
            position_no_space = original_no_space.find(edited_no_space)
            
            if position_no_space != -1:
                # スペースなしで見つかった場合、元のテキストでの位置を推定
                position = self._map_position_with_spaces(
                    original_text, original_no_space, position_no_space
                )
                logger.info(f"スペースを除去して抜粋を発見: 位置={position}")
        
        if position == -1:
            logger.warning("抜粋が元のテキスト内に見つかりません")
            # 全体を追加として扱う
            return self._create_all_added_difference(original_text, edited_text)
        
        # 抜粋範囲内での差分を検出
        excerpt_end = position + len(edited_no_punct)
        original_excerpt = original_text[position:excerpt_end]
        
        # 差分を検出
        differences = self._compare_texts(original_excerpt, edited_text, position)
        
        # 時間情報を付与
        if transcription_result:
            differences = self._add_time_information(
                differences, transcription_result, position
            )
        
        return TextDifference(
            id=self._generate_id(),
            original_text=original_text,
            edited_text=edited_text,
            differences=differences
        )
    
    def _detect_full_differences(
        self,
        original_text: str,
        edited_text: str,
        transcription_result: TranscriptionResult | None
    ) -> TextDifference:
        """全体テキストの差分を検出"""
        differences = self._compare_texts(original_text, edited_text, 0)
        
        # 時間情報を付与
        if transcription_result:
            differences = self._add_time_information(differences, transcription_result, 0)
        
        return TextDifference(
            id=self._generate_id(),
            original_text=original_text,
            edited_text=edited_text,
            differences=differences
        )
    
    def _compare_texts(
        self,
        original: str,
        edited: str,
        offset: int
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """
        2つのテキストを比較して差分を検出
        
        シンプルな実装：句読点の追加のみを検出
        """
        differences = []
        
        # 句読点を除去
        original_no_punct = self._remove_punctuation(original)
        edited_no_punct = self._remove_punctuation(edited)
        
        if original_no_punct == edited_no_punct:
            # 句読点以外は同じ
            # 共通部分と追加された句読点を検出
            i = 0  # original index
            j = 0  # edited index
            current_text = ""
            
            while j < len(edited):
                if i < len(original) and original[i] == edited[j]:
                    # 同じ文字
                    current_text += edited[j]
                    i += 1
                    j += 1
                elif edited[j] in "。、":
                    # 句読点が追加された
                    if current_text:
                        differences.append((
                            DifferenceType.UNCHANGED,
                            current_text,
                            None
                        ))
                        current_text = ""
                    differences.append((
                        DifferenceType.ADDED,
                        edited[j],
                        None
                    ))
                    j += 1
                else:
                    # 予期しない差分
                    current_text += edited[j]
                    j += 1
            
            # 残りのテキスト
            if current_text:
                differences.append((
                    DifferenceType.UNCHANGED,
                    current_text,
                    None
                ))
        else:
            # より複雑な差分がある場合
            # 簡易実装：全体を追加として扱う
            differences.append((
                DifferenceType.ADDED,
                edited,
                None
            ))
        
        return differences
    
    def _add_time_information(
        self,
        differences: list[tuple[DifferenceType, str, tuple[float, float] | None]],
        transcription_result: TranscriptionResult,
        offset: int
    ) -> list[tuple[DifferenceType, str, tuple[float, float] | None]]:
        """差分に時間情報を付与"""
        # TODO: 実装が必要
        # 現在は時間情報なしで返す
        return differences
    
    def _remove_punctuation(self, text: str) -> str:
        """句読点を除去"""
        return text.replace("。", "").replace("、", "")
    
    def _map_position_with_spaces(
        self,
        text_with_spaces: str,
        text_no_spaces: str,
        position_no_spaces: int
    ) -> int:
        """スペースなしの位置をスペースありの位置にマッピング"""
        char_count = 0
        for i, char in enumerate(text_with_spaces):
            if char != " ":
                if char_count == position_no_spaces:
                    return i
                char_count += 1
        return -1
    
    def _create_all_added_difference(
        self,
        original_text: str,
        edited_text: str
    ) -> TextDifference:
        """全体を追加として扱う差分を作成"""
        return TextDifference(
            id=self._generate_id(),
            original_text=original_text,
            edited_text=edited_text,
            differences=[(DifferenceType.ADDED, edited_text, None)]
        )
    
    def _generate_id(self) -> str:
        """ID生成"""
        from uuid import uuid4
        return str(uuid4())