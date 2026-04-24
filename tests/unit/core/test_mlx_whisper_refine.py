"""mlx_whisper_refine.py の単体テスト。

PR #119 で追加された境界重複 dedup と hallucination 検出の回帰防止。
実音声で検証済みの事例 (edited.json 由来) を fixture 化して検出精度を固定する。
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from core.mlx_whisper_refine import (
    BOUNDARY_MATCH_MIN_CHARS,
    BOUNDARY_TOUCH_SEC,
    _longest_suffix_prefix_match,
    _merge_vad_into_chunks,
    dedupe_boundary_overlaps,
    detect_hallucination,
    retry_hallucinated_segments,
    split_long_segments,
    transcribe_refined,
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


# ============================================================
# Integration-level テスト (mlx_whisper と librosa を mock)
# ============================================================


class TestRetryHallucinatedSegments:
    """hallucination 判定された範囲の再 transcribe ロジック。"""

    @staticmethod
    def _mock_librosa_load(path: str, sr: int, mono: bool) -> tuple:
        # 60 秒分のダミー音声 (16kHz)
        return np.zeros(sr * 60, dtype=np.float32), sr

    def test_no_bad_segments_returns_input_as_is(self) -> None:
        """hallucination なしの segments はそのまま返す (mlx_whisper 呼ばれない)。"""
        segs = [_seg(0.0, 5.0, "普通の自然な発話です")]
        with patch("mlx_whisper.transcribe") as mock_tx:
            out = retry_hallucinated_segments(
                audio_path="fake.wav",
                model_path="fake-model",
                segments=segs,
            )
        assert out == segs
        mock_tx.assert_not_called()

    def test_hallucinated_segment_is_replaced(self) -> None:
        """hallucination 判定された segment が retry 結果で置換される。"""
        bad = _seg(10.0, 40.0, "まあ" * 50)  # 反復 hallucination
        ok_before = _seg(0.0, 10.0, "普通の文")
        ok_after = _seg(40.0, 45.0, "別の普通の文")
        segs = [ok_before, bad, ok_after]

        # mlx_whisper retry は健全なテキストを返す
        fake_retry = {"segments": [{"start": 0.0, "end": 29.0, "text": "直された自然な発話"}]}
        with (
            patch("mlx_whisper.transcribe", return_value=fake_retry) as mock_tx,
            patch("librosa.load", side_effect=self._mock_librosa_load),
        ):
            out = retry_hallucinated_segments(
                audio_path="fake.wav",
                model_path="fake-model",
                segments=segs,
                initial_prompt="hint",
            )
        # bad が取り除かれ、retry 結果が挿入される
        texts = [s["text"] for s in out]
        assert "まあ" * 50 not in texts
        assert "直された自然な発話" in texts
        # 前後の健全 segment は保持
        assert ok_before in out
        assert ok_after in out
        # mlx_whisper.transcribe が 1 回呼ばれる
        mock_tx.assert_called_once()
        # 保守的設定が渡されていること
        kwargs = mock_tx.call_args.kwargs
        assert kwargs["condition_on_previous_text"] is False
        assert kwargs["compression_ratio_threshold"] == 1.6

    def test_retry_still_hallucinated_keeps_original(self) -> None:
        """retry 結果も hallucination ならば元セグメントを保持 (悪化防止)。"""
        bad = _seg(10.0, 40.0, "まあ" * 50)
        segs = [bad]
        # retry も hallucination を返す
        fake_retry = {"segments": [{"start": 0.0, "end": 29.0, "text": "まあ" * 50}]}
        with (
            patch("mlx_whisper.transcribe", return_value=fake_retry),
            patch("librosa.load", side_effect=self._mock_librosa_load),
        ):
            out = retry_hallucinated_segments(
                audio_path="fake.wav",
                model_path="fake-model",
                segments=segs,
            )
        # 元セグメントが保持される
        assert out == segs

    def test_retry_exception_keeps_original(self) -> None:
        """retry で例外が起きても元セグメントを保持してパイプラインを継続する。"""
        bad = _seg(10.0, 40.0, "まあ" * 50)
        segs = [bad]
        with (
            patch("mlx_whisper.transcribe", side_effect=RuntimeError("network down")),
            patch("librosa.load", side_effect=self._mock_librosa_load),
        ):
            # 例外を握って元セグメントを保持、呼び出し元には伝播しない
            out = retry_hallucinated_segments(
                audio_path="fake.wav",
                model_path="fake-model",
                segments=segs,
            )
        assert out == segs

    def test_adjacent_bad_ranges_are_merged(self) -> None:
        """近接した hallucination range は 1 つの retry にマージされる (2秒以内)。"""
        bad1 = _seg(10.0, 20.0, "まあ" * 50)
        bad2 = _seg(21.0, 30.0, "うん" * 50)  # 1 秒差なのでマージ
        segs = [bad1, bad2]
        fake_retry = {"segments": [{"start": 0.0, "end": 21.0, "text": "まともな発話"}]}
        with (
            patch("mlx_whisper.transcribe", return_value=fake_retry) as mock_tx,
            patch("librosa.load", side_effect=self._mock_librosa_load),
        ):
            out = retry_hallucinated_segments(
                audio_path="fake.wav",
                model_path="fake-model",
                segments=segs,
            )
        # 1 回だけ retry 呼ばれ、両方置換される
        assert mock_tx.call_count == 1
        assert not any("まあ" * 50 == s["text"] for s in out)
        assert not any("うん" * 50 == s["text"] for s in out)


def _disable_vad():
    """VAD を失敗させて従来 (一発 transcribe) 経路にフォールバックさせる patch。"""
    return patch("core.mlx_whisper_refine._vad_speech_ranges", side_effect=RuntimeError("no vad"))


class TestTranscribeRefined:
    """transcribe_refined (主パイプライン) の 3 ステップ orchestration (VAD 失敗フォールバック経路)。"""

    def test_empty_transcription_passes_through(self) -> None:
        """mlx_whisper.transcribe が空結果を返すと dedup/retry も no-op。"""
        fake_result = {"segments": [], "language": "ja"}
        with _disable_vad(), patch("mlx_whisper.transcribe", return_value=fake_result):
            out = transcribe_refined(
                audio_path="fake.wav",
                model_path="fake-model",
                language="ja",
            )
        assert out["segments"] == []
        assert out["language"] == "ja"

    def test_dedup_then_retry_pipeline(self) -> None:
        """通常 transcribe → 境界 dedup → hallucination retry が順に走ること。"""
        initial_segments = [
            _seg(0.0, 5.0, "これは普通の発話"),
            _seg(5.0, 10.0, "これは普通の発話"),  # 直前と完全同一、dedup 対象
            _seg(10.0, 40.0, "まあ" * 50),  # hallucination、retry 対象
        ]
        initial_result = {"segments": initial_segments, "language": "ja"}
        retry_result = {"segments": [{"start": 0.0, "end": 29.0, "text": "直された文"}]}

        calls: list[dict] = []

        def fake_transcribe(*args, **kwargs):
            calls.append(kwargs)
            return initial_result if len(calls) == 1 else retry_result

        with (
            _disable_vad(),
            patch("mlx_whisper.transcribe", side_effect=fake_transcribe),
            patch(
                "librosa.load",
                side_effect=lambda *a, **k: (np.zeros(16000 * 60, dtype=np.float32), 16000),
            ),
        ):
            out = transcribe_refined(
                audio_path="fake.wav",
                model_path="fake-model",
            )
        assert len(calls) == 2
        texts = [s["text"] for s in out["segments"]]
        assert texts.count("これは普通の発話") == 1
        assert "直された文" in texts
        assert "まあ" * 50 not in texts

    def test_mlx_kwargs_passthrough(self) -> None:
        """**mlx_kwargs が mlx_whisper.transcribe に渡されること。"""
        with _disable_vad(), patch(
            "mlx_whisper.transcribe", return_value={"segments": [], "language": "ja"}
        ) as mock_tx:
            transcribe_refined(
                audio_path="fake.wav",
                model_path="fake-model",
                word_timestamps=True,
            )
        assert mock_tx.call_args.kwargs["word_timestamps"] is True


class TestVadSpeechRanges:
    """_vad_speech_ranges は動画ファイル (.mp4) でも ffmpeg 経由で動作する。"""

    def test_converts_non_wav_via_ffmpeg(self) -> None:
        """silero_vad.read_audio は torchaudio 依存で mp4 非対応なので、
        一度 ffmpeg で 16kHz mono WAV に変換してから VAD を実行すること。
        """
        import core.mlx_whisper_refine as mr

        fake_ranges = [{"start": 0.5, "end": 2.0}, {"start": 3.0, "end": 5.5}]
        ffmpeg_calls: list[list[str]] = []

        def fake_subprocess_run(cmd, **kwargs):
            ffmpeg_calls.append(cmd)
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m

        with (
            patch("subprocess.run", side_effect=fake_subprocess_run),
            patch.object(mr, "_vad_speech_ranges", wraps=mr._vad_speech_ranges),
            patch("silero_vad.load_silero_vad", return_value=object()),
            patch("silero_vad.read_audio", return_value=np.zeros(16000 * 10, dtype=np.float32)),
            patch("silero_vad.get_speech_timestamps", return_value=fake_ranges),
        ):
            result = mr._vad_speech_ranges("videos/input.mp4")
        # ffmpeg が呼ばれて変換したこと
        assert any(cmd[0] == "ffmpeg" for cmd in ffmpeg_calls)
        # 戻り値の形
        assert result == [(0.5, 2.0), (3.0, 5.5)]


class TestSplitLongSegments:
    """VAD 統合後の長 segment を word-level で sub-split するロジック。"""

    @staticmethod
    def _w(text: str, start: float, end: float) -> dict:
        return {"word": text, "start": start, "end": end}

    def test_short_segment_not_split(self) -> None:
        """duration が target 以下なら分割しない。"""
        seg = {
            "start": 0.0,
            "end": 3.0,
            "text": "短い",
            "words": [self._w("短", 0.0, 1.5), self._w("い", 1.5, 3.0)],
        }
        assert split_long_segments([seg]) == [seg]

    def test_split_at_period(self) -> None:
        """句点「。」で分割される。"""
        seg = {
            "start": 0.0,
            "end": 12.0,
            "text": "前半です。後半です",
            "words": [
                self._w("前", 0.0, 2.0),
                self._w("半", 2.0, 3.0),
                self._w("で", 3.0, 4.0),
                self._w("す", 4.0, 5.0),
                self._w("。", 5.0, 5.5),  # 句点の直後で分割
                self._w("後", 5.5, 7.0),
                self._w("半", 7.0, 9.0),
                self._w("で", 9.0, 11.0),
                self._w("す", 11.0, 12.0),
            ],
        }
        result = split_long_segments([seg])
        # 少なくとも 2 個に分割 (句点の後で切る)
        assert len(result) >= 2
        # 最初の sub は句点まで含む
        assert "。" in result[0]["text"]
        # 全 word が保存される (テキスト保持)
        all_text = "".join(s["text"] for s in result)
        assert all_text == "前半です。後半です"

    def test_split_at_word_gap(self) -> None:
        """word 間 gap >= 0.3s で分割される (句点無しのケース)。"""
        seg = {
            "start": 0.0,
            "end": 12.0,
            "text": "あああ いいい",
            "words": [
                self._w("あ", 0.0, 1.5),
                self._w("あ", 1.5, 3.0),
                self._w("あ", 3.0, 5.0),
                # 0.5s gap
                self._w("い", 5.5, 7.5),
                self._w("い", 7.5, 9.5),
                self._w("い", 9.5, 12.0),
            ],
        }
        result = split_long_segments([seg])
        assert len(result) >= 2

    def test_word_level_timestamp_preserved(self) -> None:
        """分割後も各 word の timestamp はそのまま保持される。"""
        seg = {
            "start": 0.0,
            "end": 10.0,
            "text": "XX。YY",
            "words": [
                self._w("X", 0.0, 2.0),
                self._w("X", 2.0, 4.0),
                self._w("。", 4.0, 4.5),
                self._w("Y", 6.0, 8.0),  # 1.5s gap
                self._w("Y", 8.0, 10.0),
            ],
        }
        result = split_long_segments([seg])
        # 全 sub の words を flat にする
        all_words = []
        for s in result:
            all_words.extend(s["words"])
        # 元の 5 word が全部保持される
        assert len(all_words) == 5
        # 先頭 word の start は 0.0
        assert all_words[0]["start"] == 0.0
        # 末尾 word の end は 10.0
        assert all_words[-1]["end"] == 10.0

    def test_no_words_not_split(self) -> None:
        """word-level timestamp が無い segment は分割対象外。"""
        seg = {"start": 0.0, "end": 20.0, "text": "長いけど words なし", "words": []}
        assert split_long_segments([seg]) == [seg]

    def test_extra_fields_preserved(self) -> None:
        """分割時に segment の任意フィールド (id, chars 等) も sub に引き継がれる。"""
        seg = {
            "id": "original-id",
            "start": 0.0,
            "end": 12.0,
            "text": "AB。CD",
            "words": [
                self._w("A", 0.0, 2.0),
                self._w("B", 2.0, 4.0),
                self._w("。", 4.0, 4.5),
                self._w("C", 5.0, 7.0),  # 0.5s gap
                self._w("D", 7.0, 12.0),
            ],
        }
        result = split_long_segments([seg])
        assert all(s.get("id") == "original-id" for s in result)


class TestMergeVadIntoChunks:
    """VAD speech 区間を max_chunk_sec 以下の chunk にマージするロジック。"""

    def test_empty_returns_empty(self) -> None:
        assert _merge_vad_into_chunks([]) == []

    def test_short_ranges_merge_into_single_chunk(self) -> None:
        """すべて max_chunk_sec 内に収まれば 1 chunk にマージされる。"""
        ranges = [(0.0, 2.0), (3.0, 5.0), (6.0, 10.0)]
        result = _merge_vad_into_chunks(ranges, max_chunk_sec=30.0)
        assert result == [(0.0, 10.0)]

    def test_split_when_exceeds_max_chunk_sec(self) -> None:
        """max_chunk_sec を超える場合は新 chunk を開始。"""
        ranges = [(0.0, 10.0), (11.0, 20.0), (50.0, 55.0)]
        result = _merge_vad_into_chunks(ranges, max_chunk_sec=25.0)
        assert result == [(0.0, 20.0), (50.0, 55.0)]

    def test_chunk_boundary_at_max_chunk_sec(self) -> None:
        """ちょうど max_chunk_sec なら同 chunk に入る (<=)。"""
        ranges = [(0.0, 5.0), (25.0, 28.0)]
        result = _merge_vad_into_chunks(ranges, max_chunk_sec=28.0)
        assert result == [(0.0, 28.0)]


class TestTranscribeRefinedWithVad:
    """VAD が有効な場合のパイプライン: chunk 分割 → 個別 transcribe → 元時刻オフセット。"""

    def test_chunks_are_transcribed_separately_and_offset_applied(self) -> None:
        """VAD が chunk を返せば各々 transcribe され、元時刻にオフセットされる。"""
        # VAD が 2 chunks を返す (10-20s, 40-50s)
        # chunk ごとに異なる segment を返す
        chunk_results = [
            {"segments": [{"start": 0.5, "end": 8.0, "text": "chunk1 の発話"}]},
            {"segments": [{"start": 0.2, "end": 7.0, "text": "chunk2 の発話"}]},
        ]
        call_idx = [0]

        def fake_transcribe(*args, **kwargs):
            r = chunk_results[call_idx[0]]
            call_idx[0] += 1
            return r

        with (
            patch("core.mlx_whisper_refine._vad_speech_ranges", return_value=[(10.0, 20.0), (40.0, 50.0)]),
            patch("core.mlx_whisper_refine._extract_audio_range"),  # ffmpeg 呼び出しを no-op に
            patch("mlx_whisper.transcribe", side_effect=fake_transcribe),
        ):
            out = transcribe_refined(
                audio_path="fake.wav",
                model_path="fake-model",
                language="ja",
            )

        # 2 chunks 分の segment、両方とも元時刻にオフセットされている
        assert len(out["segments"]) == 2
        # chunk 1 は padding 0.2s 引いた 9.8s をオフセットに加える
        seg1 = out["segments"][0]
        assert abs(seg1["start"] - (0.5 + 9.8)) < 1e-6
        assert seg1["text"] == "chunk1 の発話"
        # chunk 2 は 39.8s をオフセットに加える
        seg2 = out["segments"][1]
        assert abs(seg2["start"] - (0.2 + 39.8)) < 1e-6
        assert seg2["text"] == "chunk2 の発話"

    def test_empty_segments_in_chunks_are_skipped(self) -> None:
        """chunk が空 segment (text 空白) を返した場合は除外される。"""
        chunk_results = [
            {"segments": [{"start": 0.0, "end": 1.0, "text": "   "}, {"start": 2.0, "end": 3.0, "text": "本物"}]},
        ]
        with (
            patch("core.mlx_whisper_refine._vad_speech_ranges", return_value=[(5.0, 8.0)]),
            patch("core.mlx_whisper_refine._extract_audio_range"),
            patch("mlx_whisper.transcribe", return_value=chunk_results[0]),
        ):
            out = transcribe_refined(audio_path="fake.wav", model_path="fake-model")
        assert len(out["segments"]) == 1
        assert out["segments"][0]["text"] == "本物"

    def test_vad_returns_empty_falls_back_to_normal(self) -> None:
        """VAD が speech 区間を検出できなければ従来経路 (一発 transcribe) へフォールバック。"""
        with (
            patch("core.mlx_whisper_refine._vad_speech_ranges", return_value=[]),
            patch("mlx_whisper.transcribe", return_value={"segments": [{"start": 0.0, "end": 1.0, "text": "fallback"}], "language": "ja"}) as mock_tx,
        ):
            out = transcribe_refined(audio_path="fake.wav", model_path="fake-model")
        # 通常モード: 一発 transcribe が呼ばれる
        assert mock_tx.call_count == 1
        assert out["segments"][0]["text"] == "fallback"


# ============================================================
# CLI <-> MLX_MODEL_MAP 同期テスト (N5 / R2 対策)
# ============================================================


class TestCliModelMapSync:
    """core.transcription.Transcriber.MLX_MODEL_MAP と CLI --model choices の
    同期が取れていること (二重管理での drift 防止)。"""

    def test_all_mlx_models_exposed_in_cli(self) -> None:
        from core.transcription import Transcriber
        from textffcut_cli.command import build_parser

        parser = build_parser()
        # argparse の choices を抽出
        model_action = next(a for a in parser._actions if a.dest == "model")
        cli_choices: set[str] = set(model_action.choices or [])
        mlx_keys: set[str] = set(Transcriber.MLX_MODEL_MAP.keys())

        missing = mlx_keys - cli_choices
        assert not missing, (
            f"MLX_MODEL_MAP に定義されているが CLI --model choices に未登録: {missing}. "
            f"textffcut_cli/command.py の build_parser() choices を更新してください。"
        )
