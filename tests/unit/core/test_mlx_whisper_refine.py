"""mlx_whisper_refine.py の単体テスト。

PR #119 で追加された境界重複 dedup と hallucination 検出の回帰防止。
実音声で検証済みの事例 (edited.json 由来) を fixture 化して検出精度を固定する。
"""

from __future__ import annotations

import pytest

from core.mlx_whisper_refine import (
    BOUNDARY_MATCH_MIN_CHARS,
    BOUNDARY_TOUCH_SEC,
    _longest_suffix_prefix_match,
    dedupe_boundary_overlaps,
    detect_hallucination,
)


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


class TestLongestSuffixPrefixMatch:
    """a の末尾が b の冒頭に一致する最長文字数を返す関数。"""

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            # 完全一致
            ("質問。", "質問。", 3),
            ("あのー", "あのー", 3),
            # suffix-prefix 一致
            ("超エクストリーム", "エクストリームな方", 7),
            ("まあ昨日田中圭さんと限界ライフ配布", "限界ライフ配布の事例がありますか", 7),
            # 一致なし
            ("SNSに出るところまで", "メディアに出るところまで", 0),
            ("", "何か", 0),
            ("何か", "", 0),
        ],
    )
    def test_match_length(self, a: str, b: str, expected: int) -> None:
        assert _longest_suffix_prefix_match(a, b) == expected

    def test_max_len_cap(self) -> None:
        """max_len で長大一致の探索が打ち切られること。"""
        a = "あ" * 100
        b = "あ" * 100
        # デフォルト max_len=30 でキャップされる
        assert _longest_suffix_prefix_match(a, b) == 30


class TestDetectHallucination:
    """反復 hallucination 検出器。"""

    def test_short_segment_not_hallucination(self) -> None:
        """15 文字未満は短発話として判定スキップ。"""
        assert detect_hallucination("はい") is False
        assert detect_hallucination("まあまあ") is False

    def test_repetitive_long_text_is_hallucination(self) -> None:
        """「まあ」を大量反復した典型的 hallucination パターン。"""
        text = "まあ" * 50  # 100 文字
        assert detect_hallucination(text) is True

    def test_dense_repetition_short_phrase(self) -> None:
        """「はいはいはい…」のような短フレーズの高密度反復。"""
        text = "はいはいはい" * 5  # 30 文字、bigram「はい」が支配的
        assert detect_hallucination(text) is True

    def test_natural_sentence_not_hallucination(self) -> None:
        """普通の日本語文は bigram 反復率・圧縮比ともに低い。"""
        text = "これは普通の日本語の文章で、特に反復もなく自然な発話を想定しています。"
        assert detect_hallucination(text) is False

    def test_long_natural_sentence_not_hallucination(self) -> None:
        """長い自然文でも誤検出しないこと。"""
        text = (
            "あのー、今日は情報収集の話なんですけれども、生成AIが出てきたことで"
            "情報の取り方がだいぶ変わってきたなと思っていて、そういう話を"
            "したいと思います"
        )
        assert detect_hallucination(text) is False


class TestDedupeBoundaryOverlaps:
    """境界重複検出 (Type A/B) + 誤検出回避 (Type C)。

    edited.json 由来の実事例から fixture 化。
    """

    # ---- Type A: 完全重複 ----

    @pytest.mark.parametrize(
        ("a_text", "b_text"),
        [
            ("質問。", "質問。"),
            ("はい", "はい"),
            ("うん", "うん"),
            ("あの", "あの"),
            ("そっちを目立たせようとしてるなら", "そっちを目立たせようとしてるなら"),
        ],
    )
    def test_type_a_full_duplicate_at_boundary(self, a_text: str, b_text: str) -> None:
        segs = [_seg(100.0, 105.0, a_text), _seg(105.0, 110.0, b_text)]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 1, f"完全重複 '{a_text}' が削除されるべき"
        assert out[0]["text"] == a_text

    # ---- Type B: 単語跨ぎ ----

    def test_type_b_word_crossing(self) -> None:
        """「エクストリーム」が 30 秒境界を跨いで両方に出現するケース。"""
        segs = [
            _seg(1050.0, 1056.3, "超エクストリーム"),
            _seg(1056.3, 1062.0, "エクストリームな方"),
        ]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 2
        # b 側で重複分が削除される
        assert out[1]["text"] == "な方"

    def test_type_b_trim_with_leading_punct(self) -> None:
        """b の冒頭に残る句読点・空白は lstrip される。"""
        segs = [
            _seg(100.0, 105.0, "ありがとうございます"),
            _seg(105.0, 110.0, "ありがとうございます、本当に助かりました"),
        ]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 2
        assert out[1]["text"] == "本当に助かりました"

    # ---- Type C: 触ってはいけない自然な繰り返し ----

    @pytest.mark.parametrize(
        ("a_text", "b_text"),
        [
            ("SNSに出るところまで", "メディアに出るところまで"),
            ("当たり前ではないと思いますけどね", "そんな当たり前じゃないと思います"),
            ("321円ありがとうございます。", "スパチャありがとうございます。"),
        ],
    )
    def test_type_c_natural_repetition_preserved(self, a_text: str, b_text: str) -> None:
        """類似度は高いが suffix-prefix 一致していない自然な繰り返しは保持。"""
        segs = [_seg(100.0, 105.0, a_text), _seg(105.0, 110.0, b_text)]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 2
        assert out[0]["text"] == a_text
        assert out[1]["text"] == b_text

    # ---- 境界 touch しないケース ----

    def test_gap_between_segments_preserves(self) -> None:
        """|a.end - b.start| >= 0.1s なら重複判定しない (自然な pause)。"""
        segs = [
            _seg(100.0, 105.0, "あの"),
            _seg(107.0, 110.0, "あの"),  # 2 秒の間隔あり
        ]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 2

    # ---- 境界条件 ----

    def test_empty_list(self) -> None:
        assert dedupe_boundary_overlaps([]) == []

    def test_single_segment(self) -> None:
        segs = [_seg(0.0, 5.0, "test")]
        out = dedupe_boundary_overlaps(segs)
        assert out == segs
        assert out is not segs  # shallow copy

    def test_multiple_consecutive_duplicates(self) -> None:
        """連続 3 つ以上の完全重複も順次削除される (hallucination シーケンス)。"""
        segs = [
            _seg(0.0, 2.0, "まああああ"),
            _seg(2.0, 4.0, "まああああ"),
            _seg(4.0, 6.0, "まああああ"),
            _seg(6.0, 8.0, "まああああ"),
        ]
        out = dedupe_boundary_overlaps(segs)
        assert len(out) == 1

    def test_raises_on_aligned_segments(self) -> None:
        """aligner 後の segments (words 持ち) は AssertionError。"""
        segs = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "テスト",
                "words": [{"word": "テ", "start": 0.0, "end": 1.0}],
            },
            _seg(5.0, 10.0, "テスト2"),
        ]
        with pytest.raises(AssertionError):
            dedupe_boundary_overlaps(segs)


class TestThresholdConstants:
    """閾値定数が仕様通りに公開されていること。"""

    def test_boundary_touch_sec(self) -> None:
        assert BOUNDARY_TOUCH_SEC == 0.1

    def test_boundary_match_min_chars(self) -> None:
        assert BOUNDARY_MATCH_MIN_CHARS == 7
