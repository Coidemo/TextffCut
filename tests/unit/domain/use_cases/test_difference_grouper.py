"""
DifferenceGrouperの単体テスト
"""

import pytest
from domain.use_cases.difference_grouper import DifferenceGrouper
from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.entities.text_difference import DifferenceType
from domain.value_objects.lcs_match import LCSMatch, DifferenceBlock


class TestDifferenceGrouper:
    """DifferenceGrouperのテスト"""

    @pytest.fixture
    def grouper(self):
        return DifferenceGrouper()

    @pytest.fixture
    def sample_matches(self):
        """連続したマッチとギャップを含むサンプル"""
        chars = [
            CharacterWithTimestamp("こ", 0.0, 0.2, "seg1", 0, 0),
            CharacterWithTimestamp("ん", 0.2, 0.4, "seg1", 1, 1),
            CharacterWithTimestamp("に", 0.4, 0.6, "seg1", 2, 2),
            CharacterWithTimestamp("ち", 0.6, 0.8, "seg1", 3, 3),
            CharacterWithTimestamp("は", 0.8, 1.0, "seg1", 4, 4),
        ]

        # "こんに"と"は"がマッチ（"ち"は削除）
        matches = [
            LCSMatch(0, 0, "こ", chars[0]),
            LCSMatch(1, 1, "ん", chars[1]),
            LCSMatch(2, 2, "に", chars[2]),
            LCSMatch(4, 3, "は", chars[4]),  # ギャップあり
        ]

        return matches, chars

    def test_group_continuous_matches(self, grouper, sample_matches):
        """連続したマッチのグループ化"""
        matches, _ = sample_matches

        groups = grouper.group_lcs_matches(matches)

        # 2つのグループに分かれるはず
        assert len(groups) == 2

        # 最初のグループ："こんに"
        assert len(groups[0]) == 3
        assert [m.char for m in groups[0]] == ["こ", "ん", "に"]

        # 2番目のグループ："は"
        assert len(groups[1]) == 1
        assert groups[1][0].char == "は"

    def test_group_empty_matches(self, grouper):
        """空のマッチリスト"""
        groups = grouper.group_lcs_matches([])
        assert groups == []

    def test_group_single_match(self, grouper):
        """単一のマッチ"""
        char = CharacterWithTimestamp("あ", 0.0, 0.2, "seg1", 0, 0)
        match = LCSMatch(0, 0, "あ", char)

        groups = grouper.group_lcs_matches([match])

        assert len(groups) == 1
        assert len(groups[0]) == 1
        assert groups[0][0] == match

    def test_create_difference_blocks_basic(self, grouper, sample_matches):
        """基本的な差分ブロック作成"""
        matches, chars = sample_matches
        groups = grouper.group_lcs_matches(matches)

        blocks = grouper.create_difference_blocks(groups, chars, "こんにちは", "こんには")

        # UNCHANGEDとDELETEDブロックが作成される
        unchanged_blocks = [b for b in blocks if b.type == DifferenceType.UNCHANGED]
        deleted_blocks = [b for b in blocks if b.type == DifferenceType.DELETED]

        assert len(unchanged_blocks) == 2  # "こんに"と"は"
        assert len(deleted_blocks) == 1  # "ち"

        # UNCHANGEDブロックの検証
        assert unchanged_blocks[0].text == "こんに"
        assert unchanged_blocks[0].start_time == 0.0
        assert unchanged_blocks[0].end_time == 0.6

        assert unchanged_blocks[1].text == "は"
        assert unchanged_blocks[1].start_time == 0.8
        assert unchanged_blocks[1].end_time == 1.0

        # DELETEDブロックの検証
        assert deleted_blocks[0].text == "ち"
        assert deleted_blocks[0].start_time == 0.6
        assert deleted_blocks[0].end_time == 0.8

    def test_create_difference_blocks_with_additions(self, grouper):
        """追加を含む差分ブロック作成"""
        chars = [
            CharacterWithTimestamp("あ", 0.0, 0.2, "seg1", 0, 0),
            CharacterWithTimestamp("い", 0.2, 0.4, "seg1", 1, 1),
        ]

        # "あ"だけマッチ
        matches = [LCSMatch(0, 0, "あ", chars[0])]
        groups = grouper.group_lcs_matches(matches)

        blocks = grouper.create_difference_blocks(groups, chars, "あい", "あうえ")

        # UNCHANGED、DELETED、ADDEDブロックが作成される
        unchanged_blocks = [b for b in blocks if b.type == DifferenceType.UNCHANGED]
        deleted_blocks = [b for b in blocks if b.type == DifferenceType.DELETED]
        added_blocks = [b for b in blocks if b.type == DifferenceType.ADDED]

        assert len(unchanged_blocks) == 1  # "あ"
        assert len(deleted_blocks) == 1  # "い"
        assert len(added_blocks) == 1  # "うえ"

        assert unchanged_blocks[0].text == "あ"
        assert deleted_blocks[0].text == "い"
        assert added_blocks[0].text == "うえ"
        assert added_blocks[0].start_time is None  # 追加部分には時間なし

    def test_identify_deletions_multiple_blocks(self, grouper):
        """複数の削除ブロックの識別"""
        chars = [
            CharacterWithTimestamp("あ", 0.0, 0.2, "seg1", 0, 0),
            CharacterWithTimestamp("い", 0.2, 0.4, "seg1", 1, 1),
            CharacterWithTimestamp("う", 0.4, 0.6, "seg1", 2, 2),
            CharacterWithTimestamp("え", 0.6, 0.8, "seg1", 3, 3),
            CharacterWithTimestamp("お", 0.8, 1.0, "seg1", 4, 4),
        ]

        # "あ"と"え"だけマッチ
        matches = [
            LCSMatch(0, 0, "あ", chars[0]),
            LCSMatch(3, 1, "え", chars[3]),
        ]
        groups = grouper.group_lcs_matches(matches)

        deletion_blocks = grouper._identify_deletions(groups, chars, "あいうえお")

        # 2つの削除ブロック："いう"と"お"
        assert len(deletion_blocks) == 2

        assert deletion_blocks[0].text == "いう"
        assert deletion_blocks[0].start_time == 0.2
        assert deletion_blocks[0].end_time == 0.6

        assert deletion_blocks[1].text == "お"
        assert deletion_blocks[1].start_time == 0.8
        assert deletion_blocks[1].end_time == 1.0

    def test_identify_additions_at_boundaries(self, grouper):
        """境界での追加の識別"""
        chars = []
        matches = []
        groups = []

        # 元テキストなし、編集テキストあり
        addition_blocks = grouper._identify_additions(groups, "新しいテキスト")

        assert len(addition_blocks) == 1
        assert addition_blocks[0].text == "新しいテキスト"
        assert addition_blocks[0].type == DifferenceType.ADDED

    def test_block_sorting(self, grouper):
        """ブロックの位置ソート"""
        chars = [
            CharacterWithTimestamp("B", 1.0, 1.2, "seg1", 1, 1),
            CharacterWithTimestamp("A", 0.0, 0.2, "seg1", 0, 0),
            CharacterWithTimestamp("C", 2.0, 2.2, "seg1", 2, 2),
        ]

        # 順序がバラバラなマッチ
        matches = [
            LCSMatch(1, 0, "B", chars[0]),
            LCSMatch(0, 1, "A", chars[1]),
            LCSMatch(2, 2, "C", chars[2]),
        ]

        groups = [[matches[1]], [matches[0]], [matches[2]]]  # A, B, C

        blocks = grouper.create_difference_blocks(groups, chars, "ABC", "BAC")

        # original_start_posでソートされているか確認
        unchanged_blocks = [b for b in blocks if b.type == DifferenceType.UNCHANGED]
        positions = [b.original_start_pos for b in unchanged_blocks]

        assert positions == sorted(positions)

    def test_empty_groups(self, grouper):
        """空のグループ処理"""
        blocks = grouper.create_difference_blocks([], [], "", "")
        assert blocks == []

    def test_char_positions_validation(self, grouper):
        """文字位置情報の検証"""
        chars = [
            CharacterWithTimestamp("テ", 0.0, 0.3, "seg1", 0, 0),
            CharacterWithTimestamp("ス", 0.3, 0.6, "seg1", 1, 1),
            CharacterWithTimestamp("ト", 0.6, 0.9, "seg1", 2, 2),
        ]

        matches = [
            LCSMatch(0, 0, "テ", chars[0]),
            LCSMatch(1, 1, "ス", chars[1]),
            LCSMatch(2, 2, "ト", chars[2]),
        ]

        groups = grouper.group_lcs_matches(matches)
        blocks = grouper.create_difference_blocks(groups, chars, "テスト", "テスト")

        # UNCHANGEDブロックの文字位置情報を検証
        unchanged_block = blocks[0]
        assert len(unchanged_block.char_positions) == 3
        assert all(isinstance(cp, CharacterWithTimestamp) for cp in unchanged_block.char_positions)
