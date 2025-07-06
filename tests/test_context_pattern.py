"""
文脈パターン解析機能のテストケース
"""

from core.text_processor import ContextPattern, TextProcessor


class TestContextPattern:
    """文脈パターン解析のテスト"""

    def setup_method(self):
        """テストメソッドの前処理"""
        self.processor = TextProcessor()

    def test_parse_simple_text(self):
        """通常テキスト（文脈指定なし）のパース"""
        text = "はい、分かりました。"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "はい、分かりました。"
        assert pattern.before_context is None
        assert pattern.after_context is None
        assert not pattern.has_context()

    def test_parse_before_context(self):
        """前文脈指定のパース"""
        text = "{それでは始めましょう。}はい、分かりました。"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "はい、分かりました。"
        assert pattern.before_context == "それでは始めましょう。"
        assert pattern.after_context is None
        assert pattern.has_context()

    def test_parse_after_context(self):
        """後文脈指定のパース"""
        text = "はい、分かりました。{これで終了です。}"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "はい、分かりました。"
        assert pattern.before_context is None
        assert pattern.after_context == "これで終了です。"
        assert pattern.has_context()

    def test_parse_both_contexts(self):
        """前後両方の文脈指定のパース"""
        text = "{それでは}はい、分かりました。{これで}"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "はい、分かりました。"
        assert pattern.before_context == "それでは"
        assert pattern.after_context == "これで"
        assert pattern.has_context()

    def test_parse_empty_context(self):
        """空の文脈指定のパース"""
        text = "{}はい、分かりました。{}"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "はい、分かりました。"
        assert pattern.before_context is None  # 空文字列はNoneに変換
        assert pattern.after_context is None
        assert not pattern.has_context()

    def test_parse_with_spaces(self):
        """スペースを含む文脈指定のパース"""
        text = "{ 前の文脈 }ターゲット{ 後の文脈 }"
        pattern = self.processor.parse_context_pattern(text)

        assert pattern.target_text == "ターゲット"
        assert pattern.before_context == " 前の文脈 "
        assert pattern.after_context == " 後の文脈 "

    def test_parse_nested_braces(self):
        """ネストした波括弧を含むテキストのパース"""
        # 単純な実装なので、ネストは正しく処理されない
        text = "{前{入れ子}}ターゲット"
        pattern = self.processor.parse_context_pattern(text)

        # 最初の閉じ括弧までが前文脈となる
        assert pattern.target_text == "}ターゲット"
        assert pattern.before_context == "前{入れ子"


class TestContextSearch:
    """文脈を考慮した検索のテスト"""

    def setup_method(self):
        """テストメソッドの前処理"""
        self.processor = TextProcessor()
        self.test_text = "こんにちは。はい、分かりました。それでは始めましょう。はい、分かりました。これで終了です。"

    def test_find_with_no_context(self):
        """文脈指定なしの検索"""
        pattern = ContextPattern(target_text="はい、分かりました。")
        positions = self.processor.find_with_context(self.test_text, pattern)

        # 2箇所見つかるはず
        assert len(positions) == 2
        assert positions[0] == 6  # 最初の出現位置
        assert positions[1] == 27  # 2番目の出現位置

    def test_find_with_before_context(self):
        """前文脈指定での検索"""
        pattern = ContextPattern(target_text="はい、分かりました。", before_context="それでは始めましょう。")
        positions = self.processor.find_with_context(self.test_text, pattern)

        # 1箇所のみ見つかるはず（2番目の出現）
        assert len(positions) == 1
        assert positions[0] == 27

    def test_find_with_after_context(self):
        """後文脈指定での検索"""
        pattern = ContextPattern(target_text="はい、分かりました。", after_context="これで終了です。")
        positions = self.processor.find_with_context(self.test_text, pattern)

        # 1箇所のみ見つかるはず（2番目の出現）
        assert len(positions) == 1
        assert positions[0] == 27

    def test_find_with_both_contexts(self):
        """前後両方の文脈指定での検索"""
        pattern = ContextPattern(
            target_text="はい、分かりました。",
            before_context="それでは始めましょう。",
            after_context="これで終了です。",
        )
        positions = self.processor.find_with_context(self.test_text, pattern)

        # 1箇所のみ見つかるはず
        assert len(positions) == 1
        assert positions[0] == 27

    def test_find_with_wrong_context(self):
        """マッチしない文脈での検索"""
        pattern = ContextPattern(target_text="はい、分かりました。", before_context="存在しない文脈")
        positions = self.processor.find_with_context(self.test_text, pattern)

        # 見つからないはず
        assert len(positions) == 0

    def test_find_context_at_boundary(self):
        """テキスト境界での文脈検索"""
        # テキストの先頭
        pattern1 = ContextPattern(target_text="こんにちは。", before_context="何か")  # テキストの範囲外
        positions1 = self.processor.find_with_context(self.test_text, pattern1)
        assert len(positions1) == 0

        # テキストの末尾
        pattern2 = ContextPattern(target_text="これで終了です。", after_context="何か")  # テキストの範囲外
        positions2 = self.processor.find_with_context(self.test_text, pattern2)
        assert len(positions2) == 0


class TestSegmentIndependentSearch:
    """セグメント独立検索のテスト"""

    def setup_method(self):
        """テストメソッドの前処理"""
        self.processor = TextProcessor()

        # テスト用の文字起こし結果（モック）
        class MockTranscription:
            def __init__(self):
                self.segments = []

        self.transcription = MockTranscription()

    def test_separator_split(self):
        """区切り文字での分割テスト"""
        text = "セクション1\n---\nセクション2\n---\nセクション3"
        sections = self.processor.split_text_by_separator(text)

        assert len(sections) == 3
        assert sections[0] == "セクション1"
        assert sections[1] == "セクション2"
        assert sections[2] == "セクション3"

    def test_context_pattern_integration(self):
        """文脈指定と区切り文字の統合テスト"""
        edited_text = "{前文脈}ターゲット1\n---\nターゲット2{後文脈}"
        sections = self.processor.split_text_by_separator(edited_text)

        assert len(sections) == 2

        # 各セクションの文脈パターンを解析
        pattern1 = self.processor.parse_context_pattern(sections[0])
        assert pattern1.target_text == "ターゲット1"
        assert pattern1.before_context == "前文脈"
        assert pattern1.after_context is None

        pattern2 = self.processor.parse_context_pattern(sections[1])
        assert pattern2.target_text == "ターゲット2"
        assert pattern2.before_context is None
        assert pattern2.after_context == "後文脈"
