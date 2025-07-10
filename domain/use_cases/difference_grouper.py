"""
差分グループ化ユースケース

LCSマッチを連続したグループに分類し、差分ブロックを生成する。
"""

from typing import List, Set
from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.entities.text_difference import DifferenceType
from domain.value_objects.lcs_match import LCSMatch, DifferenceBlock
from utils.logging import get_logger

logger = get_logger(__name__)


class DifferenceGrouper:
    """
    差分グループ化ユースケース

    連続したマッチをグループ化し、差分ブロックを生成する。
    """

    def group_lcs_matches(self, matches: List[LCSMatch]) -> List[List[LCSMatch]]:
        """
        連続したマッチをグループ化

        Args:
            matches: LCSマッチのリスト（順序付き）

        Returns:
            グループ化されたマッチのリスト
        """
        if not matches:
            return []

        groups = []
        current_group = [matches[0]]

        for i in range(1, len(matches)):
            prev_match = matches[i - 1]
            curr_match = matches[i]

            # 両方のテキストで連続している場合は同じグループ
            if (
                curr_match.original_index == prev_match.original_index + 1
                and curr_match.edited_index == prev_match.edited_index + 1
            ):
                current_group.append(curr_match)
            else:
                # 新しいグループを開始
                groups.append(current_group)
                current_group = [curr_match]

        # 最後のグループを追加
        if current_group:
            groups.append(current_group)

        logger.info(f"LCSマッチを{len(groups)}個のグループに分類しました")
        return groups

    def create_difference_blocks(
        self,
        groups: List[List[LCSMatch]],
        original_chars: List[CharacterWithTimestamp],
        original_text: str,
        edited_text: str,
    ) -> List[DifferenceBlock]:
        """
        グループから差分ブロックを作成

        Args:
            groups: グループ化されたマッチ
            original_chars: 元テキストの文字配列
            original_text: 元テキスト全体
            edited_text: 編集後テキスト全体

        Returns:
            差分ブロックのリスト
        """
        blocks = []

        # UNCHANGEDブロックの作成
        for group in groups:
            if not group:
                continue

            # グループの範囲を特定
            start_match = group[0]
            end_match = group[-1]

            # 対応する文字情報を収集
            char_positions = []
            for match in group:
                if match.original_index < len(original_chars):
                    char_positions.append(original_chars[match.original_index])

            # テキストを抽出
            text = "".join(match.char for match in group)

            # 時間情報
            start_time = char_positions[0].start if char_positions else None
            end_time = char_positions[-1].end if char_positions else None

            block = DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text=text,
                start_time=start_time,
                end_time=end_time,
                char_positions=char_positions,
                original_start_pos=start_match.original_index,
                original_end_pos=end_match.original_index,
            )
            blocks.append(block)

        # 削除ブロックの作成
        deletion_blocks = self._identify_deletions(groups, original_chars, original_text)
        blocks.extend(deletion_blocks)

        # 追加ブロックの作成
        addition_blocks = self._identify_additions(groups, edited_text)
        blocks.extend(addition_blocks)

        # 位置でソート（表示順序を保つため）
        blocks.sort(key=lambda b: (b.original_start_pos or 0, b.original_end_pos or 0))

        logger.info(
            f"差分ブロックを作成: {len(blocks)}個 "
            f"(UNCHANGED: {sum(1 for b in blocks if b.type == DifferenceType.UNCHANGED)}, "
            f"DELETED: {sum(1 for b in blocks if b.type == DifferenceType.DELETED)}, "
            f"ADDED: {sum(1 for b in blocks if b.type == DifferenceType.ADDED)})"
        )

        return blocks

    def _identify_deletions(
        self, groups: List[List[LCSMatch]], original_chars: List[CharacterWithTimestamp], original_text: str
    ) -> List[DifferenceBlock]:
        """削除された部分を特定"""
        deletion_blocks = []

        # マッチした位置のセット
        matched_indices = set()
        for group in groups:
            for match in group:
                matched_indices.add(match.original_index)

        # 削除された文字を連続したブロックとして収集
        current_deletion_start = None
        current_deletion_chars = []

        for i in range(len(original_chars)):
            if i not in matched_indices:
                # 削除される文字
                if current_deletion_start is None:
                    current_deletion_start = i
                current_deletion_chars.append(original_chars[i])
            else:
                # マッチした文字（削除ブロックの終了）
                if current_deletion_chars:
                    deletion_text = "".join(c.char for c in current_deletion_chars)
                    block = DifferenceBlock(
                        type=DifferenceType.DELETED,
                        text=deletion_text,
                        start_time=current_deletion_chars[0].start,
                        end_time=current_deletion_chars[-1].end,
                        char_positions=current_deletion_chars.copy(),
                        original_start_pos=current_deletion_start,
                        original_end_pos=current_deletion_start + len(current_deletion_chars) - 1,
                    )
                    deletion_blocks.append(block)
                    current_deletion_start = None
                    current_deletion_chars = []

        # 最後の削除ブロック
        if current_deletion_chars:
            deletion_text = "".join(c.char for c in current_deletion_chars)
            block = DifferenceBlock(
                type=DifferenceType.DELETED,
                text=deletion_text,
                start_time=current_deletion_chars[0].start,
                end_time=current_deletion_chars[-1].end,
                char_positions=current_deletion_chars.copy(),
                original_start_pos=current_deletion_start,
                original_end_pos=current_deletion_start + len(current_deletion_chars) - 1,
            )
            deletion_blocks.append(block)

        return deletion_blocks

    def _identify_additions(self, groups: List[List[LCSMatch]], edited_text: str) -> List[DifferenceBlock]:
        """追加された部分を特定"""
        addition_blocks = []

        # マッチした編集テキストの位置のセット
        matched_edited_indices = set()
        for group in groups:
            for match in group:
                matched_edited_indices.add(match.edited_index)

        # 追加された文字を連続したブロックとして収集
        current_addition_start = None
        current_addition_chars = []

        for i in range(len(edited_text)):
            if i not in matched_edited_indices:
                # 追加される文字
                if current_addition_start is None:
                    current_addition_start = i
                current_addition_chars.append(edited_text[i])
            else:
                # マッチした文字（追加ブロックの終了）
                if current_addition_chars:
                    addition_text = "".join(current_addition_chars)
                    block = DifferenceBlock(
                        type=DifferenceType.ADDED,
                        text=addition_text,
                        start_time=None,  # 追加部分には時間情報なし
                        end_time=None,
                        char_positions=[],
                        original_start_pos=None,  # 元テキストには存在しない
                        original_end_pos=None,
                    )
                    addition_blocks.append(block)
                    current_addition_start = None
                    current_addition_chars = []

        # 最後の追加ブロック
        if current_addition_chars:
            addition_text = "".join(current_addition_chars)
            block = DifferenceBlock(
                type=DifferenceType.ADDED,
                text=addition_text,
                start_time=None,
                end_time=None,
                char_positions=[],
                original_start_pos=None,
                original_end_pos=None,
            )
            addition_blocks.append(block)

        return addition_blocks
