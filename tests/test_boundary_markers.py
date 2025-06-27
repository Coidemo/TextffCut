"""
境界マーカー解析機能のテスト
"""


from core.text_processor import TextProcessor


class TestBoundaryMarkers:
    """境界マーカー機能のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.text_processor = TextProcessor()

    def test_parse_single_marker(self):
        """単一マーカーの解析テスト"""
        # 前のクリップを延ばす
        text = "今日は[0.5>]いい天気ですね"
        adjustments = self.text_processor.parse_boundary_markers(text)
        assert len(adjustments) == 1
        assert adjustments[0]["target"] == "previous"
        assert adjustments[0]["adjustment"] == 0.5
        assert adjustments[0]["marker"] == "[0.5>]"

        # 前のクリップを縮める
        text = "今日は[0.3<]いい天気ですね"
        adjustments = self.text_processor.parse_boundary_markers(text)
        assert len(adjustments) == 1
        assert adjustments[0]["target"] == "previous"
        assert adjustments[0]["adjustment"] == -0.3

        # 後のクリップを早める
        text = "今日は[<0.2]いい天気ですね"
        adjustments = self.text_processor.parse_boundary_markers(text)
        assert len(adjustments) == 1
        assert adjustments[0]["target"] == "next"
        assert adjustments[0]["adjustment"] == -0.2

        # 後のクリップを遅らせる
        text = "今日は[>0.4]いい天気ですね"
        adjustments = self.text_processor.parse_boundary_markers(text)
        assert len(adjustments) == 1
        assert adjustments[0]["target"] == "next"
        assert adjustments[0]["adjustment"] == 0.4

    def test_parse_multiple_markers(self):
        """複数マーカーの解析テスト"""
        text = "今日は[0.5>][<0.3]いい天気ですね[0.2<][>0.1]明日も"
        adjustments = self.text_processor.parse_boundary_markers(text)

        assert len(adjustments) == 4

        # 1つ目：前のクリップを延ばす
        assert adjustments[0]["target"] == "previous"
        assert adjustments[0]["adjustment"] == 0.5

        # 2つ目：後のクリップを早める
        assert adjustments[1]["target"] == "next"
        assert adjustments[1]["adjustment"] == -0.3

        # 3つ目：前のクリップを縮める
        assert adjustments[2]["target"] == "previous"
        assert adjustments[2]["adjustment"] == -0.2

        # 4つ目：後のクリップを遅らせる
        assert adjustments[3]["target"] == "next"
        assert adjustments[3]["adjustment"] == 0.1

    def test_parse_decimal_values(self):
        """小数点を含む値の解析テスト"""
        text = "今日は[1.25>][<0.75]いい天気"
        adjustments = self.text_processor.parse_boundary_markers(text)

        assert len(adjustments) == 2
        assert adjustments[0]["adjustment"] == 1.25
        assert adjustments[1]["adjustment"] == -0.75

    def test_remove_boundary_markers(self):
        """マーカー除去のテスト"""
        # 単一マーカー
        text = "今日は[0.5>]いい天気ですね"
        cleaned = self.text_processor.remove_boundary_markers(text)
        assert cleaned == "今日はいい天気ですね"

        # 複数マーカー
        text = "今日は[0.5>][<0.3]いい天気ですね[0.2<][>0.1]明日も"
        cleaned = self.text_processor.remove_boundary_markers(text)
        assert cleaned == "今日はいい天気ですね明日も"

        # マーカーなし
        text = "今日はいい天気ですね"
        cleaned = self.text_processor.remove_boundary_markers(text)
        assert cleaned == "今日はいい天気ですね"

    def test_apply_boundary_adjustments_simple(self):
        """境界調整の適用テスト（シンプルケース）"""
        # 2つのクリップ
        time_ranges = [(10.0, 20.0), (30.0, 40.0)]

        # 境界を調整
        adjustments = [
            {"position": 10, "target": "previous", "adjustment": 0.5},  # 1つ目を延ばす
            {"position": 10, "target": "next", "adjustment": -0.3},  # 2つ目を早める
        ]

        text = "今日は[0.5>][<0.3]いい天気ですね"

        adjusted = self.text_processor.apply_boundary_adjustments(time_ranges, adjustments, text)

        assert len(adjusted) == 2
        # 1つ目のクリップ：終了が0.5秒延長
        assert adjusted[0] == (10.0, 20.5)
        # 2つ目のクリップ：開始が0.3秒早まる
        assert adjusted[1] == (29.7, 40.0)

    def test_apply_boundary_adjustments_multiple(self):
        """境界調整の適用テスト（複数境界）"""
        # 3つのクリップ
        time_ranges = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0)]

        # 複数の境界を調整
        adjustments = [
            {"position": 10, "target": "previous", "adjustment": 0.5},  # 1つ目を延ばす
            {"position": 10, "target": "next", "adjustment": -0.3},  # 2つ目を早める
            {"position": 30, "target": "previous", "adjustment": -0.2},  # 2つ目を縮める
            {"position": 30, "target": "next", "adjustment": 0.1},  # 3つ目を遅らせる
        ]

        text = "今日は[0.5>][<0.3]いい天気ですね[0.2<][>0.1]明日も"

        adjusted = self.text_processor.apply_boundary_adjustments(time_ranges, adjustments, text)

        assert len(adjusted) == 3
        # 1つ目のクリップ：終了が0.5秒延長
        assert adjusted[0] == (10.0, 20.5)
        # 2つ目のクリップ：開始が0.3秒早まり、終了が0.2秒早まる
        assert adjusted[1] == (29.7, 39.8)
        # 3つ目のクリップ：開始が0.1秒遅れる
        assert adjusted[2] == (50.1, 60.0)

    def test_apply_boundary_adjustments_edge_cases(self):
        """境界調整のエッジケーステスト"""
        # 空の調整リスト
        time_ranges = [(10.0, 20.0), (30.0, 40.0)]
        adjusted = self.text_processor.apply_boundary_adjustments(time_ranges, [], "テキスト")
        assert adjusted == time_ranges

        # 空の時間範囲
        adjustments = [{"position": 0, "target": "previous", "adjustment": 0.5}]
        adjusted = self.text_processor.apply_boundary_adjustments([], adjustments, "テキスト")
        assert adjusted == []

        # 負の時刻になる調整（0にクリップされる）
        time_ranges = [(1.0, 5.0), (10.0, 15.0)]
        adjustments = [{"position": 10, "target": "next", "adjustment": -15.0}]  # 大きく早める
        adjusted = self.text_processor.apply_boundary_adjustments(time_ranges, adjustments, "今日は[<15.0]いい天気")
        # 2つ目のクリップの開始が0になる
        assert adjusted[1][0] == 0.0
        assert adjusted[1][1] > adjusted[1][0]  # 終了は開始より後

    def test_integration_with_diff_detection(self):
        """差分検出との統合テスト"""
        # 元のテキスト
        original = "今日はいい天気ですね。明日も晴れるでしょう。"

        # 編集後のテキスト（マーカー付き）
        edited_with_markers = "今日は[0.5>][<0.3]いい天気ですね。明日も晴れるでしょう。"

        # マーカーを除去してから差分検出
        cleaned_edited = self.text_processor.remove_boundary_markers(edited_with_markers)
        diff = self.text_processor.find_differences(original, cleaned_edited)

        # 差分がないことを確認（マーカー以外は同じテキスト）
        assert len(diff.added_chars) == 0
