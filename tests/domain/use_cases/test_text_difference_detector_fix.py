"""
差分検出の修正テスト

長いテキストの一部を抜粋した場合でも正しく検出されることを確認
"""

import pytest

from domain.entities.transcription import TranscriptionResult
from domain.use_cases.text_difference_detector import TextDifferenceDetector


class TestTextDifferenceDetectorFix:
    """差分検出の修正テスト"""

    @pytest.fixture
    def detector(self):
        """テスト用のdetectorを作成"""
        return TextDifferenceDetector()

    def test_long_excerpt_detection(self, detector):
        """長い抜粋（元のテキストの90%以上）が正しく検出されることを確認"""
        # 元のテキスト（ユーザーの実際のケースを模擬）
        original_text = (
            "上司からのフィードバックまず自分ができてから言えよという気持ちになってしまうことがあります "
            "多分あの意見と誰が言っているかを区別できてないというところが問題だと思っていて "
            "マネージャー自身ができているかどうかって超どうでもよいんですよねだってあの野球の監督の人が選手に指示をしたところでじゃあ監督が打てよって "
            "言われても監督は打てないじゃないですかなのでそもそも仕事の質が違うのであって "
            "コードレビューは書き方について指示ができるが別に自分では書けないという人たくさんいるのでそこを一緒にしているとややこしいと思いますね "
            "これはプレイヤーあるあるなのでそこを区別できてないと苦しむと思いますあのメタ社のねマークザッカーバーグもエンジニアの中に入ってなんか "
            "最近ってほどでもないんですけどプログラミングをやるイベントがあった時にあんまりにも書けなくてびっくりしたってエンジニアが言ってたんですよ "
            "なんかそういう記事があってそれって多分全然起こり得るだろうなと思っていてマークザッカーバーグが自分よりも書けない人ばっかり集めてたら会社成長しないので "
            "自分よりも圧倒的にコードが書ける人たちをたくさん集めてこういうサービスやってっていう経営とか執行のトップレベルをやってるわけなので "
            "あのコードかけるかというと書けないと思います書けるんですけどねあのそんなに一流のエンジニアほど書けなくなっているはずなんですよ "
            "なので上司もコードレビューしたり公開た方がいいようは全然言えるがプレイヤーとしての仕事ができるかというのは別問題なので "
            "なので自分ができてから言えよっていうふうに思っているのはそもそもの出発点が違うかなと思いました "
            "はい区別した方がいいですねこれあのなんで言うかというと自分が上司になった時に自分のレベルでしか指示できない人って組織の上限をそこで定めてしまっているので個人のレベルに "
            "その組織のレベルが一致してしまうのですごく良くないのであのこういう考えの人が会社にいるとすごい迷惑っていうのがあったりしますねはい "
            "これは最後に追加された文章です"
        )
        
        # 編集テキスト（最後の一文を削除 = 元のテキストの約93%）
        edited_text = original_text.replace("これは最後に追加された文章です", "").strip()
        
        # 差分検出
        result = detector.detect_differences(original_text, edited_text, None)
        
        # 検証
        assert len(result.differences) > 0
        
        # 編集テキストは元のテキストに完全に含まれるので、全体がUNCHANGEDのはず
        assert len(result.differences) == 1
        assert result.differences[0][0].value == "unchanged"
        assert result.differences[0][1] == edited_text
        
        # 全体が赤色（ADDED）になっていないことを確認
        added_diffs = [d for d in result.differences if d[0].value == "added"]
        assert len(added_diffs) == 0

    def test_partial_text_extraction(self, detector):
        """元のテキストの一部を抽出した場合の検出テスト"""
        original_text = (
            "これは最初の文章です。"
            "これは中間の文章です。"
            "これは最後の文章です。"
        )
        
        # 中間部分のみを抽出
        edited_text = "これは中間の文章です。"
        
        # 差分検出
        result = detector.detect_differences(original_text, edited_text, None)
        
        # 検証
        assert len(result.differences) == 1
        assert result.differences[0][0].value == "unchanged"
        assert result.differences[0][1] == edited_text

    def test_threshold_boundary_case(self, detector):
        """閾値境界のケーステスト（元のテキストの80-99%）"""
        original_text = "a" * 100  # 100文字
        
        test_cases = [
            (80, True),   # 80%は抜粋として扱われる
            (85, True),   # 85%も抜粋として扱われる
            (90, True),   # 90%も抜粋として扱われる
            (95, True),   # 95%も抜粋として扱われる
            (99, True),   # 99%も抜粋として扱われる
            (100, False), # 100%は通常の差分検出
            (101, False), # 101%も通常の差分検出
        ]
        
        for percentage, should_be_excerpt in test_cases:
            edited_text = "a" * percentage
            result = detector.detect_differences(original_text, edited_text, None)
            
            if should_be_excerpt and percentage < 100:
                # 抜粋として処理される場合
                assert len(result.differences) == 1
                assert result.differences[0][0].value == "unchanged"
            elif percentage == 100:
                # 同じ長さの場合は通常の差分検出
                assert len(result.differences) == 1
                assert result.differences[0][0].value == "unchanged"
            else:
                # 元より長い場合は通常の差分検出
                assert len(result.differences) >= 1
    
    def test_user_reported_issue(self, detector):
        """ユーザーが報告した問題：60分の文字起こしから2分を抜粋し、一部削除すると全体が赤になる"""
        # 60分相当の長い文字起こし（簡略化）
        original_text = "これは60分の会議の内容です。" * 100  # 長いテキスト
        
        # その中の一部（2分相当）を抜粋
        excerpt_start = "これは60分の会議の内容です。"
        excerpt = excerpt_start * 5  # 2分相当
        
        # 抜粋の一部を削除（"会議の"を削除）
        edited_text = excerpt.replace("会議の", "")
        
        # 差分検出
        result = detector.detect_differences(original_text, edited_text, None)
        
        # 検証：全体が赤（ADDED）になっていないこと
        # "これは60分の内容です。"という部分は元のテキストに存在しないが、
        # 個々の文字は存在するので、文字単位では大部分がUNCHANGEDになるはず
        unchanged_count = sum(1 for d in result.differences if d[0].value == "unchanged")
        added_count = sum(1 for d in result.differences if d[0].value == "added")
        
        # 大部分の文字は元のテキストに存在するはず
        total_chars = sum(len(d[1]) for d in result.differences)
        unchanged_chars = sum(len(d[1]) for d in result.differences if d[0].value == "unchanged")
        
        # 8割以上の文字が元のテキストに存在することを確認
        assert unchanged_chars / total_chars > 0.8, f"変更なしの文字が少なすぎます: {unchanged_chars}/{total_chars}"
    
    def test_exact_diff_behavior(self, detector):
        """difffのような正確な文字単位の差分検出"""
        original_text = "明日は雨が降るでしょう"
        edited_text = "明日は雪が降るでしょう"
        
        # 差分検出
        result = detector.detect_differences(original_text, edited_text, None)
        
        # "雨" → "雪" の変更を検出
        # "明日は" と "が降るでしょう" は変更なし
        # "雪" は追加（元のテキストに存在しない）
        
        # 差分の内容を確認
        diff_texts = [(d[0].value, d[1]) for d in result.differences]
        
        # 最低限、"雪"がADDEDとして検出されることを確認
        added_texts = [d[1] for d in result.differences if d[0].value == "added"]
        assert "雪" in "".join(added_texts)