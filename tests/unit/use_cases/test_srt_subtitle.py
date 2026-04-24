"""SRT字幕生成のテスト

Phase 1スコアリング改善、SENTENCE_ENDINGS追加、フィラー除去のテスト。
GiNZA文節ベーススコアリング、POS正規化のテスト。
"""

from unittest.mock import MagicMock

from core.japanese_line_break import JapaneseLineBreakRules
from use_cases.ai.srt_subtitle_generator import (
    SENTENCE_ENDINGS,
    _ends_with_sentence,
    _entries_from_char_times,
    _parse_pos,
    _phase1_split,
    _remove_inline_fillers,
    build_timeline_map,
    collect_parts,
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
        # 「あの」はGiNZAが連体詞と判定するため、リスト除去の対象外
        # （指示代名詞「あの人」の誤除去を防ぐ）
        assert "これは" in new_text
        assert "すごい" in new_text

    def test_char_times_shift(self):
        """char_timesがフィラー除去後に正しくシフトされるか"""
        text = "えーとテスト"  # "えーと" = 3文字除去
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

    def test_youwa_after_kanji_preserved(self):
        """漢字直後の「要は」は "必要は" "重要は" 等の複合語末尾なので保持する"""
        for text in ("必要はない", "重要は別にある", "概要は以下", "需要はある"):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert new_text == text, f"漢字 prefix の「要は」が誤除去された: {text!r} → {new_text!r}"

    def test_youwa_at_start_removed(self):
        """文頭の「要は」はフィラーとして除去される"""
        text = "要は簡単に言うと"
        ct = self._make_char_times(text)
        sb = {len(text)}
        new_text, _, _ = _remove_inline_fillers(text, ct, sb)
        assert "要は" not in new_text
        assert "簡単に言うと" in new_text

    # --- 新規: 文脈依存「あの」「まあ」の処理 -----------------------------

    def test_ano_demonstrative_preserved(self):
        """連体詞「あの+人/時/こと」は保持される"""
        for text in ("あの人はすごい", "あの時の話", "あのこともあった", "あの頃は楽しかった"):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert text == new_text, f"demonstrative should be preserved: {text!r} → {new_text!r}"

    def test_ano_filler_removed(self):
        """フィラー「あの+一般名詞/動詞」は除去される"""
        # 実データ由来の例
        cases = [
            ("あの世界はどんどん変わる", "世界はどんどん変わる"),
            ("あの仕事がちゃんと回る", "仕事がちゃんと回る"),
            ("あの意外とそうですね", "意外とそうですね"),
            ("あのシンプルに言うと", "シンプルに言うと"),
        ]
        for text, expected_contains in cases:
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "あの" not in new_text, f"filler should be removed: {text!r} → {new_text!r}"
            assert expected_contains in new_text

    def test_ano_with_comma_removed(self):
        """「あの、」は常にフィラー扱いで除去"""
        text = "あの、そうですね"
        ct = self._make_char_times(text)
        sb = {len(text)}
        new_text, _, _ = _remove_inline_fillers(text, ct, sb)
        assert "あの" not in new_text

    def test_maa_adverb_preserved(self):
        """副詞「まあ+評価語」は保持（まあいい/まあ大丈夫）"""
        for text in ("まあいいか", "まあ大丈夫だよ", "まあ仕方ないね"):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "まあ" in new_text, f"adverb まあ should be preserved: {text!r} → {new_text!r}"

    def test_maa_filler_removed(self):
        """フィラー「まあ+一般語」は除去"""
        cases = [
            ("まあ、そうですね", "そうですね"),
            ("まあ普通にやれば", "普通にやれば"),
        ]
        for text, expected_contains in cases:
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "まあ" not in new_text, f"filler まあ should be removed: {text!r} → {new_text!r}"
            assert expected_contains in new_text

    # --- 相槌系 filler: 「うん」「はい」「ええ」---

    def test_un_aizuchi_removed(self):
        """相槌の「うん」(前後が句読点) は除去"""
        cases = [
            ("ですね。うん。あと現場",),
            ("キロね、うん、すごい",),
        ]
        for (text,) in cases:
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "うん" not in new_text, f"aizuchi うん should be removed: {text!r} → {new_text!r}"

    def test_un_in_word_preserved(self):
        """「思うん」「使うん」「戦うん」等の動詞撥音便は保持"""
        for text in (
            "ったと思うんですけど",
            "3時間使うんだっけ",
            "感じが戦うんですけど",
        ):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "うん" in new_text, f"verb suffix うん should be preserved: {text!r} → {new_text!r}"

    def test_hai_aizuchi_removed(self):
        """相槌の「はい」(前後が句読点) は除去"""
        for text in (
            "います。はい、なんかで",
            "なんで、はい。金曜日",
            "したね。はい。例・そ",
        ):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "はい" not in new_text, f"aizuchi はい should be removed: {text!r} → {new_text!r}"

    def test_hai_in_word_preserved(self):
        """「やるとかはいい」の「は+いい」は保持 (「はい」と誤認しない)"""
        text = "やるとかはいいと思います"
        ct = self._make_char_times(text)
        sb = {len(text)}
        new_text, _, _ = _remove_inline_fillers(text, ct, sb)
        assert "はいい" in new_text, f"は+いい should be preserved: {text!r} → {new_text!r}"

    # --- 厳格判定系 filler: 「そう」---

    def test_sou_strict_both_boundaries_removed(self):
        """前後両方が句読点の「そう」は削除 (単独相槌のみ)"""
        text = "そうだろう、そう、みんなね"
        ct = self._make_char_times(text)
        sb = {len(text)}
        new_text, _, _ = _remove_inline_fillers(text, ct, sb)
        # 「そうだろう」の「そう」は副詞として保持 (後ろに「だ」が続く)
        assert "そうだろう" in new_text, f"adverb そう should be preserved: {text!r} → {new_text!r}"
        # 「、そう、」の「そう」は前後両方句読点なので削除
        # 「みんな」は保持
        assert "みんなね" in new_text
        # そう が減っている (3 個 → 1 個)
        assert new_text.count("そう") == 1

    def test_sou_adverb_preserved(self):
        """「そういう」「そうだね」「そう考える」等の副詞/動詞接続は保持"""
        for text in (
            "そういうことですね",
            "そうだねって話",
            "なんで、そう考えとく",
            "みんながそうやって、",
        ):
            ct = self._make_char_times(text)
            sb = {len(text)}
            new_text, _, _ = _remove_inline_fillers(text, ct, sb)
            assert "そう" in new_text, f"adverb そう should be preserved: {text!r} → {new_text!r}"


class TestEndToEnd:
    """実セグメントデータでの統合テスト"""

    def _make_char_times_for_segments(self, segments: list[dict]) -> tuple[str, list[tuple[float, float]], set[int]]:
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


class TestPosNormalization:
    """GiNZA UniDic→IPADIC POS正規化のテスト"""

    def test_filler_normalization(self):
        """感動詞-フィラー → フィラー"""
        assert JapaneseLineBreakRules._normalize_pos_tag("感動詞-フィラー") == "フィラー"

    def test_non_independent_normalization(self):
        """非自立可能 → 非自立"""
        assert JapaneseLineBreakRules._normalize_pos_tag("動詞-非自立可能") == "動詞-非自立"

    def test_three_level_tag_truncation(self):
        """3レベルタグを大分類-小分類に切り詰め"""
        assert JapaneseLineBreakRules._normalize_pos_tag("名詞-普通名詞-サ変可能") == "名詞-普通名詞"

    def test_simple_tag_passthrough(self):
        """助詞-格助詞はそのまま"""
        assert JapaneseLineBreakRules._normalize_pos_tag("助詞-格助詞") == "助詞-格助詞"

    def test_single_level_tag(self):
        """助動詞はそのまま"""
        assert JapaneseLineBreakRules._normalize_pos_tag("助動詞") == "助動詞"


class TestBunsetuBoundaries:
    """GiNZA文節境界のテスト"""

    def test_basic_bunsetu(self):
        """基本的な文節分割"""
        bounds = JapaneseLineBreakRules.get_bunsetu_boundaries("露出をしている")
        # 「露出を|している」→ 文節境界は3（「し」の位置）
        assert 3 in bounds, f"文節境界が期待通りでない: {bounds}"

    def test_te_iru_same_bunsetu(self):
        """「している」が同一文節内に収まる"""
        bounds = JapaneseLineBreakRules.get_bunsetu_boundaries("露出をしている")
        # 「している」内部（位置4=「て」の後、位置5=「い」の後）は文節境界にならない
        assert 4 not in bounds, f"「して|いる」が文節分割された: {bounds}"

    def test_setsuzoku_joshi_boundary(self):
        """接続助詞「から」の後が文節境界"""
        bounds = JapaneseLineBreakRules.get_bunsetu_boundaries("問題があるからこれは対応する")
        # 「あるから|」の後に文節境界がある
        assert any(b > 5 for b in bounds), f"「から」後に文節境界がない: {bounds}"

    def test_omotta_n_dakke_na_single_bunsetu(self):
        """「思ったんだっけな」が1文節にまとまる"""
        bounds = JapaneseLineBreakRules.get_bunsetu_boundaries("思ったんだっけな")
        # 全体が1文節なら内部に文節境界はない
        assert len(bounds) == 0, f"「思ったんだっけな」が分割された: {bounds}"

    def test_empty_text(self):
        """空テキストでエラーにならない"""
        bounds = JapaneseLineBreakRules.get_bunsetu_boundaries("")
        assert bounds == set()


class TestCompatTokenizer:
    """後方互換トークナイザーシムのテスト"""

    def test_tokenizer_returns_compat(self):
        """_get_tokenizer()がシムを返す"""
        tokenizer = JapaneseLineBreakRules._get_tokenizer()
        assert tokenizer is not False

    def test_compat_token_surface(self):
        """互換トークンのsurface属性"""
        tokenizer = JapaneseLineBreakRules._get_tokenizer()
        tokens = list(tokenizer.tokenize("テスト"))
        assert any(t.surface == "テスト" for t in tokens)

    def test_compat_token_part_of_speech_format(self):
        """互換トークンのpart_of_speechがカンマ区切り形式"""
        tokenizer = JapaneseLineBreakRules._get_tokenizer()
        tokens = list(tokenizer.tokenize("いいかな"))
        for t in tokens:
            parts = t.part_of_speech.split(",")
            assert len(parts) == 4, f"part_of_speechが4要素でない: {t.part_of_speech}"

    def test_compat_shuujoshi_detection(self):
        """srt_diff_exporter互換: 終助詞のin検索が動作"""
        tokenizer = JapaneseLineBreakRules._get_tokenizer()
        tokens = list(tokenizer.tokenize("いいかな"))
        shuujoshi_found = any("終助詞" in t.part_of_speech for t in tokens)
        assert shuujoshi_found, "終助詞が検出されなかった"



# ---------------------------------------------------------------------------
# collect_parts の境界マッチング（word-level timestamp対応）
# ---------------------------------------------------------------------------


def _seg(start, end, text, words=None):
    """テスト用のセグメントモック。word-level timestampを含む。"""
    s = MagicMock()
    s.start = start
    s.end = end
    s.text = text
    s.words = words
    return s


def _word(w, start, end):
    """テスト用のワードモック。"""
    mw = MagicMock()
    mw.word = w
    mw.start = start
    mw.end = end
    return mw


class TestCollectPartsWordLevel:
    """collect_parts が word-level timestamp を使い、
    短い重なりでセグメント全文を詰め込むバグを回避することを検証。
    """

    def test_full_segment_in_range_uses_all_words(self):
        """セグメント全体がレンジ内なら全テキストを採用。"""
        # seg [10-15s] "こんにちは" 5文字、レンジ [10-15s]
        words = [
            _word("こ", 10.0, 11.0),
            _word("ん", 11.0, 12.0),
            _word("に", 12.0, 13.0),
            _word("ち", 13.0, 14.0),
            _word("は", 14.0, 15.0),
        ]
        seg = _seg(10.0, 15.0, "こんにちは", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        time_ranges = [(10.0, 15.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        assert len(parts) == 1
        text, tl_s, tl_e = parts[0]
        assert text == "こんにちは"
        assert tl_s == 0.0
        assert abs(tl_e - 5.0) < 0.01

    def test_tiny_overlap_only_captures_overlapping_words(self):
        """短い range でも、tolerance (0.3s) を超えて離れた word は含まない。
        バグ前は全テキスト（"まああの" 4文字）がこの0.1秒に詰め込まれていた。
        """
        # seg [113.5-117.0s] "まああの" — 各 word の間隔を tolerance (0.3s) 以上空ける
        words = [
            _word("ま", 113.5, 113.7),
            _word("あ", 115.0, 115.2),  # 1.3s 離れた位置 → tolerance 外
            _word("あ", 115.5, 115.7),
            _word("の", 116.0, 116.2),
        ]
        seg = _seg(113.5, 117.0, "まああの", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        # レンジは [113.5-113.6] の0.1秒だけ
        time_ranges = [(113.5, 113.6)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        # word「ま」(113.5-113.7)だけがレンジと重なる → 1部だけ収集
        assert len(parts) == 1
        text, tl_s, tl_e = parts[0]
        assert text == "ま"
        assert tl_s == 0.0
        assert tl_e <= 0.25  # word.end (113.7) クランプ先は range.end (113.6) ではなく word.end

    def test_segment_spans_two_ranges_words_go_to_each(self):
        """1セグメントが2レンジに跨る場合、各レンジに対応する word がそれぞれ収集される。
        どのレンジとも overlap が無い word は drop される。"""
        # range1 [100-103]: A[100-101], B[101-102], C[102-103]
        # range2 [110-114]: K[110-111], L[111-112], M[112-113], N[113-114]
        # 中間 word D-J はどのレンジとも overlap なし → drop
        words = [
            _word("A", 100.0, 101.0),
            _word("B", 101.0, 102.0),
            _word("C", 102.0, 103.0),
            _word("D", 103.5, 104.0),
            _word("E", 104.5, 105.0),
            _word("F", 105.5, 106.0),
            _word("G", 106.5, 107.0),
            _word("H", 107.5, 108.0),
            _word("I", 108.5, 109.0),
            _word("J", 109.0, 109.5),
            _word("K", 110.0, 111.0),
            _word("L", 111.0, 112.0),
            _word("M", 112.0, 113.0),
            _word("N", 113.0, 114.0),
        ]
        seg = _seg(100.0, 114.0, "ABCDEFGHIJKLMN", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        time_ranges = [(100.0, 103.0), (110.0, 114.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        texts = [p[0] for p in parts]
        assert "ABC" in texts
        assert "KLMN" in texts
        combined = "".join(texts)
        # 中間 word はすべて overlap 無し → 含まれない
        for ch in "DEFGHIJ":
            assert ch not in combined

    def test_orphan_word_without_overlap_is_dropped(self):
        """どの range とも overlap しない word は drop される。

        無音削除で range 間の gap に落ちた word を救済する責務は、SRT 層ではなく
        無音削除層の _rescue_missing_words が担う。SRT 層は time_ranges を真実として
        扱い、range 外の word は拾わない（orphan tolerance は廃止）。
        """
        # range1 [100-103] と range2 [103.15-106] の間の 0.15s gap に word X を配置
        words = [
            _word("A", 100.0, 101.0),
            _word("B", 101.0, 102.0),
            _word("X", 103.00, 103.10),  # どの range とも overlap なし
            _word("Y", 103.20, 104.0),
            _word("Z", 104.0, 105.0),
        ]
        seg = _seg(100.0, 105.0, "ABXYZ", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        time_ranges = [(100.0, 103.0), (103.15, 106.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        combined = "".join(p[0] for p in parts)
        # X は SRT 層では drop される（別途 _rescue_missing_words で range 側救済）
        assert "X" not in combined, f"orphan word X が SRT 層で拾われた: parts={parts}"
        assert combined == "ABYZ", f"順序が崩れた: {combined}"

    def test_segment_boundary_does_not_fragment_parts(self):
        """同一 range 内で Whisper segment が切り替わっても part は分断されない（Fix1）。"""
        # seg1 [100-102] "AB" / seg2 [102-104] "CD" — いずれも range [100-104] に収まる
        seg1 = _seg(100.0, 102.0, "AB", [_word("A", 100.0, 101.0), _word("B", 101.0, 102.0)])
        seg2 = _seg(102.0, 104.0, "CD", [_word("C", 102.0, 103.0), _word("D", 103.0, 104.0)])
        transcription = MagicMock()
        transcription.segments = [seg1, seg2]

        time_ranges = [(100.0, 104.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        # バグ前は seg 境界で flush されて 2 parts になっていた
        assert len(parts) == 1, f"segment 境界で part が分断された: {parts}"
        text, tl_s, tl_e = parts[0]
        assert text == "ABCD"
        assert tl_s == 0.0
        assert abs(tl_e - 4.0) < 0.01

    def test_missing_words_raises(self):
        """words が無いセグメントはエラーにする（キャッシュ無しと同等扱い）。"""
        seg = _seg(10.0, 15.0, "こんにちは", words=None)
        transcription = MagicMock()
        transcription.segments = [seg]
        time_ranges = [(10.0, 15.0)]
        tmap = build_timeline_map(time_ranges)

        import pytest as _pytest

        with _pytest.raises(ValueError, match="word"):
            collect_parts(time_ranges, tmap, transcription, speed=1.0)

    def test_speed_adjusted_timestamps(self):
        """time_ranges は speed 除算済み、seg は元時間の前提で正しく変換される。"""
        # seg [120-126s] "123456" 6文字、1文字=1秒
        words = [_word(ch, 120.0 + i, 121.0 + i) for i, ch in enumerate("123456")]
        seg = _seg(120.0, 126.0, "123456", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        # speed=1.2, time_rangeは 100-105 (= orig 120-126)
        time_ranges = [(100.0, 105.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.2)

        assert len(parts) == 1
        text, tl_s, tl_e = parts[0]
        assert text == "123456"
        assert tl_s == 0.0
        assert abs(tl_e - 5.0) < 0.01


class TestCharTimeMapWordLevel:
    """_build_char_time_map が word 境界ベースで char_times を構築することの検証（Fix3）。"""

    def test_char_times_follow_word_boundaries_not_uniform(self):
        """part 内で word ごとの tl が保持され、膨張 word の影響が局所化される。"""
        from use_cases.ai.srt_subtitle_generator import _build_char_time_map, _collect_parts_core

        # word 'の' が 1.98 秒（大幅膨張）、他は 0.1 秒。実音響は 'の' の末尾にある想定。
        words = [
            _word("な", 100.0, 100.02),
            _word("の", 100.02, 102.0),  # 膨張
            _word("で", 102.0, 102.1),
            _word("す", 102.1, 102.2),
        ]
        seg = _seg(100.0, 102.2, "なのです", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        time_ranges = [(100.0, 102.2)]
        tmap = build_timeline_map(time_ranges)
        parts_with_words = _collect_parts_core(time_ranges, tmap, transcription, speed=1.0)
        full, ctimes, _ = _build_char_time_map(parts_with_words)

        assert full == "なのです"
        assert len(ctimes) == 4
        # 'な' は 0.0-0.02 付近
        assert ctimes[0][0] == 0.0
        assert ctimes[0][1] < 0.1
        # 'の' は膨張 word なので 0.02-2.0 に広がる
        assert ctimes[1][0] < 0.1
        assert abs(ctimes[1][1] - 2.0) < 0.05
        # 'で' は 'の' の膨張を引きずらず、単独 word の tl に従う（2.0-2.1）
        assert abs(ctimes[2][0] - 2.0) < 0.05
        assert abs(ctimes[2][1] - 2.1) < 0.05
        # 'す' も同様
        assert abs(ctimes[3][0] - 2.1) < 0.05

    def test_char_times_monotonic_across_multiple_parts(self):
        """複数 part を連結しても char_times は単調非減少。"""
        from use_cases.ai.srt_subtitle_generator import _build_char_time_map, _collect_parts_core

        words = [
            _word("A", 100.0, 101.0),
            _word("B", 101.0, 102.0),
            _word("C", 110.0, 111.0),
            _word("D", 111.0, 112.0),
        ]
        seg = _seg(100.0, 112.0, "ABCD", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        time_ranges = [(100.0, 102.0), (110.0, 112.0)]
        tmap = build_timeline_map(time_ranges)
        parts_with_words = _collect_parts_core(time_ranges, tmap, transcription, speed=1.0)
        full, ctimes, _ = _build_char_time_map(parts_with_words)

        assert full == "ABCD"
        assert len(ctimes) == 4
        prev_end = -1.0
        for i, (cs, ce) in enumerate(ctimes):
            assert cs >= prev_end - 1e-6, f"ctimes[{i}] が後退: {cs} < {prev_end}"
            assert ce >= cs, f"ctimes[{i}] で end<start: {cs} {ce}"
            prev_end = ce
