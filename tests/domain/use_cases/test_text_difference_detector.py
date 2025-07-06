"""
TextDifferenceDetectorのテスト
"""

import pytest

from domain.entities.text_difference import DifferenceType
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.use_cases.text_difference_detector import TextDifferenceDetector


class TestTextDifferenceDetector:
    """TextDifferenceDetectorのテスト"""

    def setup_method(self):
        """テストのセットアップ"""
        self.detector = TextDifferenceDetector()

    def test_detect_punctuation_addition(self):
        """句読点追加の検出"""
        # セグメントをスペースなしで結合した文字起こし結果
        original = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますねその代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています"
        # ユーザーが句読点を追加
        edited = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"

        result = self.detector.detect_differences(original, edited)

        assert result is not None
        assert len(result.differences) == 4  # 2つの共通部分と2つの句読点

        # 追加された句読点を確認
        added_chars = result.added_chars
        assert "。" in added_chars
        assert len(added_chars) == 1  # 。のみ
        assert result.added_count == 2  # 2箇所に追加

    def test_detect_excerpt_with_punctuation(self):
        """抜粋テキストでの句読点追加の検出"""
        # 長い文字起こし結果
        original = (
            "はいこんにちはこんにちはよろしくお願いしますというわけで配信がされているかどうかのチェックをしつつシェアしますお願いします"
            + "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね"
            + "その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています"
            + "お金持ちから税金を取ろう派ですね"
        )

        # ユーザーが一部を抜粋して句読点を追加
        edited = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"

        result = self.detector.detect_differences(original, edited)

        assert result is not None
        assert result.added_chars == {"。"}
        assert result.added_count == 2

    def test_detect_no_changes(self):
        """変更なしの検出"""
        text = "これは変更されないテキストです"

        result = self.detector.detect_differences(text, text)

        assert result is not None
        assert not result.has_changes
        assert result.unchanged_count == 1
        assert result.added_count == 0

    def test_detect_with_transcription_result(self):
        """TranscriptionResult付きでの検出"""
        # TranscriptionResultを作成
        segments = [
            TranscriptionSegment(
                id="1", text="お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて", start=0.0, end=3.0
            ),
            TranscriptionSegment(
                id="2", text="社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね", start=3.0, end=6.0
            ),
        ]

        transcription = TranscriptionResult(
            id="test",
            language="ja",
            segments=segments,
            original_audio_path="/test/path",
            model_size="base",
            processing_time=10.0,
        )

        original = transcription.text  # スペースなしで結合される
        edited = original.replace("ますね", "ますね。")

        result = self.detector.detect_differences(original, edited, transcription)

        assert result is not None
        assert "。" in result.added_chars

    def test_empty_texts(self):
        """空テキストのエラーハンドリング"""
        # 両方空の場合はTextDifferenceのバリデーションでエラー
        with pytest.raises(ValueError):
            self.detector.detect_differences("", "")

    def test_detect_complex_changes(self):
        """複雑な変更の検出（現在は全体を追加として扱う）"""
        original = "これは元のテキストです"
        edited = "これは大幅に変更されたテキストになりました"

        result = self.detector.detect_differences(original, edited)

        assert result is not None
        assert result.added_count == 1
        assert result.differences[0][0] == DifferenceType.ADDED
        assert result.differences[0][1] == edited
