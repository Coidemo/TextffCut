"""
UIDataGeneratorの単体テスト
"""

import pytest
from domain.use_cases.ui_data_generator import UIDataGenerator
from domain.entities.text_difference import DifferenceType
from domain.value_objects.lcs_match import DifferenceBlock
from domain.entities.character_timestamp import CharacterWithTimestamp


class TestUIDataGenerator:
    """UIDataGeneratorのテスト"""

    @pytest.fixture
    def generator(self):
        return UIDataGenerator()

    @pytest.fixture
    def sample_blocks(self):
        """サンプルの差分ブロック"""
        chars1 = [
            CharacterWithTimestamp("こ", 0.0, 0.1, "seg1", 0, 0),
            CharacterWithTimestamp("ん", 0.1, 0.2, "seg1", 1, 1),
            CharacterWithTimestamp("に", 0.2, 0.3, "seg1", 2, 2),
            CharacterWithTimestamp("ち", 0.3, 0.4, "seg1", 3, 3),
            CharacterWithTimestamp("は", 0.4, 0.5, "seg1", 4, 4),
        ]
        
        chars2 = [
            CharacterWithTimestamp("え", 0.5, 0.6, "seg1", 5, 5),
            CharacterWithTimestamp("ー", 0.6, 0.7, "seg1", 6, 6),
        ]
        
        blocks = [
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="こんにちは",
                start_time=0.0,
                end_time=0.5,
                char_positions=chars1,
                original_start_pos=0,
                original_end_pos=4
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="えー",
                start_time=0.5,
                end_time=0.7,
                char_positions=chars2,
                original_start_pos=5,
                original_end_pos=6
            ),
            DifferenceBlock(
                type=DifferenceType.ADDED,
                text="今日は",
                start_time=None,
                end_time=None,
                char_positions=[],
                original_start_pos=None,
                original_end_pos=None
            ),
        ]
        
        return blocks

    def test_generate_highlights_basic(self, generator, sample_blocks):
        """基本的なハイライト生成"""
        original_text = "こんにちはえー"
        
        highlights = generator.generate_highlights(original_text, sample_blocks)
        
        assert len(highlights) == 3
        
        # UNCHANGEDブロック
        assert highlights[0]["type"] == "unchanged"
        assert highlights[0]["text"] == "こんにちは"
        assert highlights[0]["char_count"] == 5
        assert highlights[0]["start_pos"] == 0
        assert highlights[0]["end_pos"] == 4
        assert highlights[0]["start_time"] == 0.0
        assert highlights[0]["end_time"] == 0.5
        assert highlights[0]["duration"] == 0.5
        assert highlights[0]["time_display"] == "0:00.00 - 0:00.50"
        assert highlights[0]["css_class"] == "diff-unchanged"
        assert "保持" in highlights[0]["tooltip"]
        
        # DELETEDブロック
        assert highlights[1]["type"] == "deleted"
        assert highlights[1]["text"] == "えー"
        assert highlights[1]["char_count"] == 2
        assert highlights[1]["css_class"] == "diff-deleted"
        assert "削除" in highlights[1]["tooltip"]
        
        # ADDEDブロック
        assert highlights[2]["type"] == "added"
        assert highlights[2]["text"] == "今日は"
        assert highlights[2]["char_count"] == 3
        assert highlights[2]["css_class"] == "diff-added"
        assert "追加" in highlights[2]["tooltip"]
        assert "start_time" not in highlights[2]  # 時間情報なし

    def test_generate_deletion_summary_with_fillers(self, generator):
        """フィラーを含む削除サマリー生成"""
        deletion_blocks = [
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="えー",
                start_time=0.0,
                end_time=0.2,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="あのー",
                start_time=1.0,
                end_time=1.3,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="重要な",
                start_time=2.0,
                end_time=2.5,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="内容",
                start_time=3.0,
                end_time=3.3,
                char_positions=[]
            ),
        ]
        
        summary = generator.generate_deletion_summary(deletion_blocks)
        
        assert summary["has_deletions"] is True
        assert summary["total_count"] == 4
        assert summary["total_duration"] == 1.3  # 0.2 + 0.3 + 0.5 + 0.3
        assert summary["total_chars"] == 10  # 2 + 3 + 3 + 2
        
        # グループ検証
        assert len(summary["groups"]) == 2
        
        # フィラーグループ
        filler_group = summary["groups"][0]
        assert filler_group["type"] == "fillers"
        assert filler_group["count"] == 2
        assert filler_group["duration"] == 0.5  # 0.2 + 0.3
        assert len(filler_group["items"]) == 2
        assert filler_group["has_more"] is False
        
        # 通常の削除グループ
        normal_group = summary["groups"][1]
        assert normal_group["type"] == "normal"
        assert normal_group["count"] == 2
        assert normal_group["duration"] == 0.8  # 0.5 + 0.3
        assert len(normal_group["items"]) == 2

    def test_generate_deletion_summary_with_short_deletions(self, generator):
        """短い削除を含むサマリー生成"""
        deletion_blocks = [
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="あ",
                start_time=0.0,
                end_time=0.1,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="い",
                start_time=1.0,
                end_time=1.2,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="長い削除内容",
                start_time=2.0,
                end_time=3.0,
                char_positions=[]
            ),
        ]
        
        summary = generator.generate_deletion_summary(deletion_blocks)
        
        assert len(summary["groups"]) == 2
        
        # 短い削除グループ
        short_group = [g for g in summary["groups"] if g["type"] == "short"][0]
        assert short_group["count"] == 2
        assert short_group["duration"] == 0.3  # 0.1 + 0.2
        
        # 通常の削除グループ
        normal_group = [g for g in summary["groups"] if g["type"] == "normal"][0]
        assert normal_group["count"] == 1
        assert normal_group["duration"] == 1.0

    def test_generate_deletion_summary_empty(self, generator):
        """空の削除リストのサマリー"""
        summary = generator.generate_deletion_summary([])
        
        assert summary["has_deletions"] is False
        assert summary["total_count"] == 0
        assert summary["total_duration"] == 0.0
        assert summary["groups"] == []

    def test_generate_progress_indicator(self, generator, sample_blocks):
        """進捗インジケーターの生成"""
        original_text = "こんにちはえー"
        edited_text = "こんにちは今日は"
        
        progress = generator.generate_progress_indicator(
            original_text, edited_text, sample_blocks
        )
        
        # 文字数情報
        assert progress["original_length"] == 7  # "こんにちはえー"
        assert progress["edited_length"] == 8   # "こんにちは今日は"
        assert progress["unchanged_chars"] == 5  # "こんにちは"
        assert progress["deleted_chars"] == 2   # "えー"
        assert progress["added_chars"] == 3     # "今日は"
        
        # 圧縮率（文字ベース）
        # (1 - 8/7) * 100 = -14.3% (増加)
        assert progress["compression_rate"] == pytest.approx(-14.3, abs=0.1)
        
        # 時間情報
        assert progress["total_original_duration"] == 0.7  # 0.0〜0.7
        assert progress["total_edited_duration"] == 0.5    # UNCHANGEDの合計
        assert progress["time_compression_rate"] == pytest.approx(28.6, abs=0.1)
        
        # パーセンテージ
        assert progress["stats"]["unchanged_percentage"] == pytest.approx(71.4, abs=0.1)
        assert progress["stats"]["deleted_percentage"] == pytest.approx(28.6, abs=0.1)
        assert progress["stats"]["added_percentage"] == pytest.approx(37.5, abs=0.1)

    def test_format_time(self, generator):
        """時間フォーマットのテスト"""
        assert generator._format_time(0.0) == "0:00.00"
        assert generator._format_time(5.5) == "0:05.50"
        assert generator._format_time(65.25) == "1:05.25"
        assert generator._format_time(3661.5) == "61:01.50"

    def test_format_time_range(self, generator):
        """時間範囲フォーマットのテスト"""
        assert generator._format_time_range(0.0, 5.5) == "0:00.00 - 0:05.50"
        assert generator._format_time_range(60.0, 65.5) == "1:00.00 - 1:05.50"

    def test_get_css_class(self, generator):
        """CSSクラス取得のテスト"""
        assert generator._get_css_class(DifferenceType.UNCHANGED) == "diff-unchanged"
        assert generator._get_css_class(DifferenceType.DELETED) == "diff-deleted"
        assert generator._get_css_class(DifferenceType.ADDED) == "diff-added"

    def test_is_filler(self, generator):
        """フィラー判定のテスト"""
        # フィラー
        assert generator._is_filler("えー") is True
        assert generator._is_filler("あのー") is True
        assert generator._is_filler("まあ") is True
        assert generator._is_filler("えー、") is True  # 句読点付き
        
        # フィラーではない
        assert generator._is_filler("こんにちは") is False
        assert generator._is_filler("今日") is False

    def test_block_to_item(self, generator):
        """ブロックからアイテムへの変換"""
        block = DifferenceBlock(
            type=DifferenceType.DELETED,
            text="えー",
            start_time=0.5,
            end_time=0.7,
            char_positions=[]
        )
        
        item = generator._block_to_item(block)
        
        assert item["text"] == "えー"
        assert item["char_count"] == 2
        assert item["is_filler"] is True
        assert item["start_time"] == 0.5
        assert item["end_time"] == 0.7
        assert item["duration"] == 0.2
        assert item["time_display"] == "0:00.50 - 0:00.70"

    def test_tooltip_generation(self, generator):
        """ツールチップ生成のテスト"""
        # 時間情報ありのブロック
        block1 = DifferenceBlock(
            type=DifferenceType.UNCHANGED,
            text="テスト",
            start_time=1.0,
            end_time=2.5,
            char_positions=[]
        )
        tooltip1 = generator._generate_tooltip(block1)
        assert "保持" in tooltip1
        assert "3文字" in tooltip1
        assert "1.5秒" in tooltip1
        assert "0:01.00 - 0:02.50" in tooltip1
        
        # 時間情報なしのブロック
        block2 = DifferenceBlock(
            type=DifferenceType.ADDED,
            text="追加",
            start_time=None,
            end_time=None,
            char_positions=[]
        )
        tooltip2 = generator._generate_tooltip(block2)
        assert "追加" in tooltip2
        assert "2文字" in tooltip2
        assert "秒" not in tooltip2  # 時間情報なし

    def test_deletion_summary_with_many_items(self, generator):
        """多数のアイテムを含む削除サマリー"""
        # 7個のフィラーを作成
        filler_blocks = []
        for i in range(7):
            filler_blocks.append(
                DifferenceBlock(
                    type=DifferenceType.DELETED,
                    text="えー",
                    start_time=i * 0.5,
                    end_time=i * 0.5 + 0.2,
                    char_positions=[]
                )
            )
        
        summary = generator.generate_deletion_summary(filler_blocks)
        
        filler_group = summary["groups"][0]
        assert filler_group["count"] == 7
        assert len(filler_group["items"]) == 5  # 最初の5個のみ
        assert filler_group["has_more"] is True  # 表示しきれないアイテムあり