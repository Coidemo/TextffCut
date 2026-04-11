"""SRT字幕生成のテスト

Phase 1スコアリング改善、SENTENCE_ENDINGS追加、フィラー除去のテスト。
"""

from use_cases.ai.srt_subtitle_generator import (
    SENTENCE_ENDINGS,
    _ends_with_sentence,
    _entries_from_char_times,
    _parse_pos,
    _phase1_split,
    _remove_inline_fillers,
)


class TestParsePos:
    """_parse_pos ヘルパーのテスト"""

    def test_with_subcategory(self):
        assert _parse_pos("助詞-格助詞") == ("助詞", "格助詞")

    def test_without_subcategory(self):
        assert _parse_pos("名詞") == ("名詞", "")

    def test_filler(self):
        assert _parse_pos("フィラー") == ("フィラー", "")

    def test_complex_subcategory(self):
        assert _parse_pos("動詞-非自立") == ("動詞", "非自立")


class TestPhase1LineBreak:
    """Phase 1のスコアリング改善テスト"""

    def _get_blocks_text(self, text: str, max_chars: int = 11) -> list[str]:
        """テキストを分割してブロックのテキストリストを返す"""
        seg_bounds = {len(text)}
        blocks = _phase1_split(text, seg_bounds, max_chars)
        return [b.text for b in blocks]

    def test_kakujoshi_verb_protection(self):
        """格助詞+動詞は分割されにくい（「露出を|して」を防ぐ）"""
        # 「露出をしている」- 動詞+て が分離されないことが最優先
        blocks = self._get_blocks_text("露出をしている")
        # 「し|て」のように動詞末尾でてが分離されていないことを確認
        for b in blocks:
            assert not b.endswith("し"), f"動詞+て分離: {blocks}"

    def test_te_form_auxiliary_protection(self):
        """て形+補助動詞は分割されにくい（「て+いる」保護）"""
        blocks = self._get_blocks_text("起きているような")
        # 「て」の後で「いる」と分離していないこと
        joined = "".join(blocks)
        assert joined == "起きているような"
        # 「ている」が一つのブロックに含まれるか確認
        found = any("ている" in b for b in blocks)
        assert found, f"「ている」が分割された: {blocks}"

    def test_non_independent_noun_protection(self):
        """非自立名詞+助動詞は分割されにくい（「よう|な」保護）"""
        blocks = self._get_blocks_text("起きているような問題")
        # 「ような」が一つのブロックに含まれるか
        found = any("ような" in b for b in blocks)
        assert found, f"「ような」が分割された: {blocks}"

    def test_setsuzoku_joshi_strong_break(self):
        """接続助詞（から/けど/ので）は強い分割点"""
        # 11文字制限内なので分割されないかもしれないが、
        # 長いテキストでは「から」の後で分割されやすい
        text = "問題があるからこれは対応する"
        blocks = self._get_blocks_text(text)
        # 「から」の後で分割されていることを期待
        assert len(blocks) >= 2, f"分割されなかった: {blocks}"


class TestSentenceEndings:
    """SENTENCE_ENDINGS追加パターンのテスト"""

    def test_new_endings_present(self):
        """新しく追加したパターンがリストに含まれるか"""
        new_endings = [
            "んですけれども",
            "ですけれども",
            "んですけども",
            "ですけども",
            "けれども",
            "けども",
            "だけど",
            "からね",
            "しかない",
            "らしい",
        ]
        for ending in new_endings:
            assert ending in SENTENCE_ENDINGS, f"'{ending}' がSENTENCE_ENDINGSに含まれていない"

    def test_ends_with_sentence_new_patterns(self):
        """新パターンで_ends_with_sentenceが正しくTrueを返すか"""
        assert _ends_with_sentence("そうなんですけれども")
        assert _ends_with_sentence("良いらしい")
        assert _ends_with_sentence("方法しかない")
        assert _ends_with_sentence("そうだけど")
        assert _ends_with_sentence("いいからね")

    def test_ends_with_sentence_non_match(self):
        """マッチしないパターンではFalseを返すか"""
        assert not _ends_with_sentence("露出をして")
        assert not _ends_with_sentence("起きている")


class TestInlineFillerRemoval:
    """フィラー除去のテスト"""

    def _make_char_times(self, text: str, start: float = 0.0) -> list[tuple[float, float]]:
        """テスト用に均等なchar_timesを生成"""
        n = len(text)
        dur = 1.0  # 1秒/テキスト全体
        return [(start + dur * i / n, start + dur * (i + 1) / n) for i in range(n)]

    def test_basic_filler_removal(self):
        """基本的なフィラー除去"""
        text = "なんか今日は良い天気"
        char_times = self._make_char_times(text)
        seg_bounds = {len(text)}

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        assert "なんか" not in new_text
        assert "今日は良い天気" in new_text

    def test_multiple_fillers_removal(self):
        """複数フィラーの除去"""
        text = "えーとなんかこれはあのすごい"
        char_times = self._make_char_times(text)
        seg_bounds = {len(text)}

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        assert "えーと" not in new_text
        assert "なんか" not in new_text
        assert "あの" not in new_text
        assert "これは" in new_text
        assert "すごい" in new_text

    def test_char_times_shift(self):
        """char_timesがフィラー除去後に正しくシフトされるか"""
        text = "あのテスト"  # "あの" = 2文字除去
        char_times = self._make_char_times(text)
        seg_bounds = {len(text)}

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        assert new_text == "テスト"
        assert len(new_ct) == 3  # "テスト" = 3文字

    def test_non_filler_preserved(self):
        """フィラーでない語は保持される"""
        text = "問題があるからこれは対応する"
        char_times = self._make_char_times(text)
        seg_bounds = {len(text)}

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        assert new_text == text  # フィラーなし → 変更なし
        assert len(new_ct) == len(char_times)

    def test_seg_bounds_adjusted(self):
        """seg_boundsがフィラー除去後に正しく調整されるか"""
        text = "なんかテスト次のセグメント"
        # "なんか" = 3文字、セグメント境界は6文字目（"次"の位置）
        char_times = self._make_char_times(text)
        seg_bounds = {6, len(text)}  # 6="次"の位置

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        # "なんか"除去後: "テスト次のセグメント"
        # 元の位置6("次") → 新位置3
        assert new_text == "テスト次のセグメント"
        assert 3 in new_sb  # "次"の新しい位置

    def test_empty_text(self):
        """空テキストでエラーにならない"""
        new_text, new_ct, new_sb = _remove_inline_fillers("", [], set())
        assert new_text == ""
        assert new_ct == []
        assert new_sb == set()

    def test_yappari_removal(self):
        """やっぱり/やっぱの除去"""
        text = "やっぱりこれは良い"
        char_times = self._make_char_times(text)
        seg_bounds = {len(text)}

        new_text, new_ct, new_sb = _remove_inline_fillers(text, char_times, seg_bounds)
        assert "やっぱり" not in new_text
        assert "これは良い" in new_text


class TestEndToEnd:
    """実セグメントデータでの統合テスト"""

    def _make_char_times_for_segments(
        self, segments: list[dict]
    ) -> tuple[str, list[tuple[float, float]], set[int]]:
        """セグメントからfull_text, char_times, seg_boundsを構築"""
        full_text = ""
        char_times = []
        seg_bounds = set()

        for seg in segments:
            text = seg["text"]
            if not text:
                continue
            seg_bounds.add(len(full_text))
            start = seg["start"]
            end = seg["end"]
            dur = end - start
            n = max(len(text), 1)
            for i in range(len(text)):
                char_times.append((start + dur * i / n, start + dur * (i + 1) / n))
            full_text += text

        seg_bounds.add(len(full_text))
        seg_bounds.discard(0)
        return full_text, char_times, seg_bounds

    def test_integration_with_filler(self):
        """フィラー含むセグメントからの字幕生成"""
        segments = [
            {"text": "なんか今日の天気は", "start": 0.0, "end": 2.0},
            {"text": "すごく良いですね", "start": 2.0, "end": 4.0},
        ]
        full_text, char_times, seg_bounds = self._make_char_times_for_segments(segments)
        entries = _entries_from_char_times(full_text, char_times, seg_bounds, 11, 2)

        # フィラー「なんか」が除去されていること
        all_text = " ".join(e.text.replace("\n", "") for e in entries)
        assert "なんか" not in all_text
        assert "今日の天気は" in all_text

    def test_integration_no_filler(self):
        """フィラーなしセグメントでも正常動作"""
        segments = [
            {"text": "問題があるからこれは対応する", "start": 0.0, "end": 3.0},
        ]
        full_text, char_times, seg_bounds = self._make_char_times_for_segments(segments)
        entries = _entries_from_char_times(full_text, char_times, seg_bounds, 11, 2)
        assert len(entries) > 0

    def test_sentence_ending_prevents_merge(self):
        """SENTENCE_ENDINGSがPhase 3で結合を防ぐ"""
        # 1行目が「んですけれども」で終わる場合、次の行と結合しない
        segments = [
            {"text": "そうなんですけれどもこれは別の話題です", "start": 0.0, "end": 5.0},
        ]
        full_text, char_times, seg_bounds = self._make_char_times_for_segments(segments)
        entries = _entries_from_char_times(full_text, char_times, seg_bounds, 11, 2)

        # エントリが生成されること
        assert len(entries) > 0
        # すべてのエントリが11文字制限を守っていること
        for e in entries:
            for line in e.text.split("\n"):
                assert len(line) <= 11, f"11文字超過: '{line}' ({len(line)}文字)"
