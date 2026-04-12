"""
タイトル画像の色セグメント境界スナップテスト

GiNZA依存をモックして、_snap_segments_to_word_boundaries() の
セグメント境界スナップ処理をテストする。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from use_cases.ai.title_image_generator import (
    TitleImageDesign,
    TitleLine,
    TitleTextSegment,
    _snap_segments_to_word_boundaries,
)


def _make_design(lines: list[list[tuple[str, str]]]) -> TitleImageDesign:
    """テスト用のデザインを簡易作成する。

    lines: [[(text, color), ...], ...]
    """
    title_lines = []
    for segs in lines:
        segments = [TitleTextSegment(text=t, color=c) for t, c in segs]
        title_lines.append(TitleLine(segments=segments))
    return TitleImageDesign(lines=title_lines)


class TestSnapSegmentsToWordBoundaries:
    """_snap_segments_to_word_boundaries() のテスト"""

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[2, 3, 5],  # "今日|の|天気" → [2, 3, 5]
    )
    def test_already_on_boundary(self, _mock_wb):
        """セグメント境界が既に単語境界上にある場合は変更なし"""
        design = _make_design(
            [
                [("今日", "#FF0000"), ("の", "#FFFFFF"), ("天気", "#00FF00")],
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        texts = [seg.text for seg in result.lines[0].segments]
        assert texts == ["今日", "の", "天気"]
        # 色も維持
        colors = [seg.color for seg in result.lines[0].segments]
        assert colors == ["#FF0000", "#FFFFFF", "#00FF00"]

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[2, 3, 5],  # "今日|の|天気" → [2, 3, 5]
    )
    def test_snap_mid_word_boundary(self, _mock_wb):
        """単語の途中で分割されている場合、最寄り境界にスナップ"""
        # "今" | "日の天気" — 境界が1（"今"の後）で単語境界にない
        design = _make_design(
            [
                [("今", "#FF0000"), ("日の天気", "#00FF00")],
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        # 境界1は最寄りの単語境界2にスナップ → "今日" | "の天気"
        texts = [seg.text for seg in result.lines[0].segments]
        joined = "".join(texts)
        assert joined == "今日の天気"
        assert texts[0] == "今日"
        # "今日"のmidpoint=1.0 は元セグ1 [1,5) に属する → 色は#00FF00
        assert result.lines[0].segments[0].color == "#00FF00"

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[3, 5, 7, 8, 10],  # "おはよう|ござい|ます|！|今日" → [3, 5, 7, 8, 10]
    )
    def test_snap_preserves_text_integrity(self, _mock_wb):
        """スナップ後もテキスト結合結果が元テキストと一致"""
        design = _make_design(
            [
                [("おはよ", "#FF0000"), ("うございます！今日", "#00FF00")],
            ]
        )
        original_text = "おはようございます！今日"
        result = _snap_segments_to_word_boundaries(design)

        reconstructed = "".join(seg.text for seg in result.lines[0].segments)
        assert reconstructed == original_text

    def test_single_segment_unchanged(self):
        """1セグメントのみの行は変更なし"""
        design = _make_design(
            [
                [("今日の天気", "#FF0000")],
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        assert len(result.lines[0].segments) == 1
        assert result.lines[0].segments[0].text == "今日の天気"
        assert result.lines[0].segments[0].color == "#FF0000"

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[],  # 解析失敗
    )
    def test_empty_boundaries_returns_unchanged(self, _mock_wb):
        """GiNZA解析が空リストを返した場合はそのまま返す"""
        design = _make_design(
            [
                [("今", "#FF0000"), ("日の天気", "#00FF00")],
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        texts = [seg.text for seg in result.lines[0].segments]
        assert texts == ["今", "日の天気"]

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[2, 3, 5],
    )
    def test_style_attributes_inherited(self, _mock_wb):
        """スナップ後もスタイル属性（gradient, weight等）が正しく継承される"""
        line = TitleLine(
            segments=[
                TitleTextSegment(
                    text="今日",
                    font_size=180,
                    color="#FFFFFF",
                    gradient=("#FFD700", "#FF8C00"),
                    weight="Eb",
                ),
                TitleTextSegment(
                    text="の天気",
                    font_size=120,
                    color="#00FF00",
                    gradient=None,
                    weight="Bd",
                ),
            ],
            outer_outline_color="#000000",
            outer_outline_width=8,
        )
        design = TitleImageDesign(lines=[line])
        result = _snap_segments_to_word_boundaries(design)

        # 境界は既にword boundary上 → セグメントはそのまま
        seg0 = result.lines[0].segments[0]
        assert seg0.text == "今日"
        assert seg0.gradient == ("#FFD700", "#FF8C00")
        assert seg0.weight == "Eb"
        assert seg0.font_size == 180

        # 2番目のセグメントも属性維持
        seg1 = result.lines[0].segments[1]
        assert seg1.text == "の天気"
        assert seg1.gradient is None
        assert seg1.weight == "Bd"

        # ラインのアウトライン属性も維持
        assert result.lines[0].outer_outline_color == "#000000"
        assert result.lines[0].outer_outline_width == 8

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[2, 4, 6],  # "今日|は晴|れだ"
    )
    def test_multiple_lines(self, _mock_wb):
        """複数行がそれぞれ独立にスナップされる"""
        design = _make_design(
            [
                [("今日は晴れだ", "#FFFFFF")],  # 1セグメント → 変更なし
                [("今日は", "#FF0000"), ("晴れだ", "#00FF00")],  # 境界3 → 2か4にスナップ
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        # 1行目: 1セグメントのため変更なし
        assert len(result.lines[0].segments) == 1
        assert result.lines[0].segments[0].text == "今日は晴れだ"

        # 2行目: スナップ処理が適用される
        texts_line2 = [seg.text for seg in result.lines[1].segments]
        joined = "".join(texts_line2)
        assert joined == "今日は晴れだ"

    def test_design_level_attributes_preserved(self):
        """line_spacing, padding_top がそのまま維持される"""
        design = TitleImageDesign(
            lines=[
                TitleLine(segments=[TitleTextSegment(text="テスト", color="#FFF")]),
            ],
            line_spacing=20,
            padding_top=100,
        )
        result = _snap_segments_to_word_boundaries(design)
        assert result.line_spacing == 20
        assert result.padding_top == 100

    @patch(
        "core.japanese_line_break.JapaneseLineBreakRules.get_word_boundaries",
        return_value=[2, 3, 5],  # "天気|が|良い"
    )
    def test_three_segments_one_misaligned(self, _mock_wb):
        """3セグメントで1つだけずれている場合"""
        # "天気" | "が良" | "い" — 2番目の境界が4（単語境界にない）
        design = _make_design(
            [
                [("天気", "#FF0000"), ("が良", "#00FF00"), ("い", "#0000FF")],
            ]
        )
        result = _snap_segments_to_word_boundaries(design)

        # 境界: 2(OK), 4→3にスナップ → "天気" | "が" | "良い"
        texts = [seg.text for seg in result.lines[0].segments]
        joined = "".join(texts)
        assert joined == "天気が良い"
