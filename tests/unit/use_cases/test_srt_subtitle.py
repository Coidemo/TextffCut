"""SRT字幕生成のテスト

Phase 1スコアリング改善、SENTENCE_ENDINGS追加、フィラー除去のテスト。
GiNZA文節ベーススコアリング、POS正規化のテスト。
APIキーフォールバックのテスト。
"""

from unittest.mock import MagicMock, patch

from core.japanese_line_break import JapaneseLineBreakRules
from use_cases.ai.srt_subtitle_generator import (
    SENTENCE_ENDINGS,
    _ends_with_sentence,
    _entries_from_char_times,
    _parse_pos,
    _phase1_split,
    _remove_inline_fillers,
    _transcribe_output_audio,
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


class TestTranscribeOutputAudioApiKey:
    """_transcribe_output_audio APIキーフォールバックのテスト"""

    def test_explicit_api_key_takes_priority(self):
        """引数で渡したapi_keyが優先される"""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.segments = [
            MagicMock(text="テスト", start=0.0, end=1.0),
        ]
        mock_client.return_value.audio.transcriptions.create.return_value = mock_resp

        with (
            patch("use_cases.ai.srt_subtitle_generator.os.environ.get", return_value=None),
            patch("use_cases.ai.srt_subtitle_generator._extract_audio_parts_parallel", return_value=["/tmp/p0.wav"]),
            patch("subprocess.run") as mock_run,
            patch("builtins.open", MagicMock()),
            (
                patch("use_cases.ai.srt_subtitle_generator.OpenAI", mock_client)
                if False
                else patch.dict("sys.modules", {})
            ),
        ):
            # OpenAIのimportをモックするために、関数内のロジックだけテスト
            # api_key引数ありの場合、環境変数は参照されないことを確認
            from use_cases.ai import srt_subtitle_generator

            original_env_get = srt_subtitle_generator.os.environ.get
            env_calls = []

            def tracking_env_get(key, *args):
                env_calls.append(key)
                return None

            with patch.object(srt_subtitle_generator.os.environ, "get", side_effect=tracking_env_get):
                # api_key="sk-test" を渡す → 環境変数は参照されない
                # ただしOpenAIのimportで例外が出るため、Noneが返る
                result = _transcribe_output_audio([(0.0, 1.0)], MagicMock(), api_key="sk-test")
                # 環境変数は参照されないはず
                assert "OPENAI_API_KEY" not in env_calls
                assert "TEXTFFCUT_API_KEY" not in env_calls

    def test_fallback_to_api_key_manager(self):
        """環境変数なし時にapi_key_managerフォールバックが呼ばれる"""
        mock_manager = MagicMock()
        mock_manager.load_api_key.return_value = "sk-from-manager"

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("utils.api_key_manager.api_key_manager", mock_manager),
        ):
            # api_key=None + 環境変数なし → api_key_managerが呼ばれるはず
            # OpenAIのimportで例外が出るが、api_key_managerは呼ばれる
            result = _transcribe_output_audio([(0.0, 1.0)], MagicMock(), api_key=None)
            mock_manager.load_api_key.assert_called_once()

    def test_returns_none_when_no_api_key(self):
        """APIキーが一切ない場合はNoneを返す"""
        mock_manager = MagicMock()
        mock_manager.load_api_key.return_value = None

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("utils.api_key_manager.api_key_manager", mock_manager),
        ):
            result = _transcribe_output_audio([(0.0, 1.0)], MagicMock(), api_key=None)
            assert result is None


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
        words = [_word("こ", 10.0, 11.0), _word("ん", 11.0, 12.0), _word("に", 12.0, 13.0), _word("ち", 13.0, 14.0), _word("は", 14.0, 15.0)]
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
        """重なりが0.1秒だけなら、その0.1秒に含まれる word だけ採用。
        バグ前は全テキスト（"まああの" 4文字）がこの0.1秒に詰め込まれていた。
        """
        # seg [113.5-115.5s] "まああの" 4文字、word timestamps で各語を振る
        words = [
            _word("ま", 113.5, 113.7),  # ← 最初の0.2s
            _word("あ", 113.7, 114.0),
            _word("あ", 114.0, 114.5),
            _word("の", 114.5, 115.5),
        ]
        seg = _seg(113.5, 115.5, "まああの", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        # レンジは [113.5-113.6] の0.1秒だけ
        time_ranges = [(113.5, 113.6)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        # word「ま」(113.5-113.7)だけがレンジと重なる → 1部だけ収集
        # バグ前は "まああの" 全文が tl 0-0.1 に詰め込まれていた
        assert len(parts) == 1
        text, tl_s, tl_e = parts[0]
        assert text == "ま"
        assert tl_s == 0.0
        # tl_e は word の end か range end の小さいほう
        assert tl_e <= 0.1 + 0.01

    def test_segment_spans_two_ranges_words_go_to_each(self):
        """1セグメントが2レンジに跨る場合、各レンジに対応する word がそれぞれ収集される。"""
        # seg [100-110s] "ABCDEFGHIJ" 10文字、word timestamps
        words = [_word(ch, 100.0 + i, 101.0 + i) for i, ch in enumerate("ABCDEFGHIJ")]
        seg = _seg(100.0, 110.0, "ABCDEFGHIJ", words)
        transcription = MagicMock()
        transcription.segments = [seg]

        # レンジ1: 100-103s (word A,B,C), レンジ2: 107-110s (word H,I,J)
        time_ranges = [(100.0, 103.0), (107.0, 110.0)]
        tmap = build_timeline_map(time_ranges)
        parts = collect_parts(time_ranges, tmap, transcription, speed=1.0)

        # 各レンジごとに別のpartが出る
        # part1: "ABC" at tl 0-3
        # part2: "HIJ" at tl 3-6
        texts = [p[0] for p in parts]
        assert "ABC" in texts
        assert "HIJ" in texts
        # D,E,F,Gは含まれない
        combined = "".join(texts)
        assert "D" not in combined and "E" not in combined

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
