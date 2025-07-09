#!/usr/bin/env python3
"""
printデバッグで問題を特定
"""

from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.entities.text_difference import DifferenceType

# 実際のシナリオ
original_text = """おはようございます。今日は良い天気ですね。
明日の予定について話しましょう。
会議は午後2時からです。
上司からのフィードバックまず自分ができてから言えよという気持ちになってしまうことがあります 多分あの意見と誰が言っているかを区別できてないというところが問題だと思っていて マネージャー自身ができているかどうかって超どうでもよいんですよねだってあの野球の監督の人が選手に指示をしたところでじゃあ監督が打てよって 言われても監督は打てないじゃないですかなのでそもそも仕事の質が違うのであって コードレビューは書き方について指示ができるが別に自分では書けないという人たくさんいるのでそこを一緒にしているとややこしいと思いますね これはプレイヤーあるあるなのでそこを区別できてないと苦しむと思いますあのメタ社のねマークザッカーバーグもエンジニアの中に入ってなんか 最近ってほどでもないんですけどプログラミングをやるイベントがあった時にあんまりにも書けなくてびっくりしたってエンジニアが言ってたんですよ なんかそういう記事があってそれって多分全然起こり得るだろうなと思っていてマークザッカーバーグが自分よりも書けない人ばっかり集めてたら会社成長しないので 自分よりも圧倒的にコードが書ける人たちをたくさん集めてこういうサービスやってっていう経営とか執行のトップレベルをやってるわけなので あのコードかけるかというと書けないと思います書けるんですけどねあのそんなに一流のエンジニアほど書けなくなっているはずなんですよ なので上司もコードレビューしたり公開た方がいいようは全然言えるがプレイヤーとしての仕事ができるかというのは別問題なので なので自分ができてから言えよっていうふうに思っているのはそもそもの出発点が違うかなと思いました はい区別した方がいいですねこれあのなんで言うかというと自分が上司になった時に自分のレベルでしか指示できない人って組織の上限をそこで定めてしまっているので個人のレベルに その組織のレベルが一致してしまうのですごく良くないのであのこういう考えの人が会社にいるとすごい迷惑っていうのがあったりしますねはい
それでは次の話題に移りましょう。
開発の進捗はどうですか？"""

edited_text = """上司からのフィードバックまず自分ができてから言えよという気持ちになってしまうことがあります 多分あの意見と誰が言っているかを区別できてないというところが問題だと思っていて マネージャー自身ができているかどうかって超どうでもよいんですよねだってあの野球の監督の人が選手に指示をしたところでじゃあ監督が打てよって 言われても監督は打てないじゃないですかなのでそもそも仕事の質が違うのであって コードレビューは書き方について指示ができるが別に自分では書けないという人たくさんいるのでそこを一緒にしているとややこしいと思いますね これはプレイヤーあるあるなのでそこを区別できてないと苦しむと思いますあのメタ社のねマークザッカーバーグもエンジニアの中に入ってなんか 最近ってほどでもないんですけどプログラミングをやるイベントがあった時にあんまりにも書けなくてびっくりしたってエンジニアが言ってたんですよ なんかそういう記事があってそれって多分全然起こり得るだろうなと思っていてマークザッカーバーグが自分よりも書けない人ばっかり集めてたら会社成長しないので 自分よりも圧倒的にコードが書ける人たちをたくさん集めてこういうサービスやってっていう経営とか執行のトップレベルをやってるわけなので あのコードかけるかというと書けないと思います書けるんですけどねあのそんなに一流のエンジニアほど書けなくなっているはずなんですよ なので上司もコードレビューしたり公開た方がいいようは全然言えるがプレイヤーとしての仕事ができるかというのは別問題なので なので自分ができてから言えよっていうふうに思っているのはそもそもの出発点が違うかなと思いました はい区別した方がいいですねこれあのなんで言うかというと自分が上司になった時に自分のレベルでしか指示できない人って組織の上限をそこで定めてしまっているので個人のレベルに その組織のレベルが一致してしまうのですごく良くないのであのこういう考えの人が会社にいるとすごい迷惑っていうのがあったりしますねはい"""


# TextDifferenceDetectorにprintデバッグを追加
class DebugTextDifferenceDetector(TextDifferenceDetector):
    def detect_differences(self, original_text: str, edited_text: str, transcription_result=None):
        print(f"\n[detect_differences] 開始")
        print(f"  元のテキスト長: {len(original_text)}")
        print(f"  編集テキスト長: {len(edited_text)}")
        print(f"  比率: {len(edited_text) / len(original_text) * 100:.1f}%")
        print(f"  0.8閾値: {len(original_text) * 0.8}")
        print(f"  抜粋として処理?: {len(edited_text) < len(original_text) * 0.8}")

        return super().detect_differences(original_text, edited_text, transcription_result)

    def _detect_excerpt_differences(self, original_text: str, edited_text: str, transcription_result=None):
        print(f"\n[_detect_excerpt_differences] 開始")
        result = super()._detect_excerpt_differences(original_text, edited_text, transcription_result)
        print(f"[_detect_excerpt_differences] 結果: {len(result.differences)}個の差分")
        return result

    def _detect_full_differences(self, original_text: str, edited_text: str, transcription_result=None):
        print(f"\n[_detect_full_differences] 開始")
        result = super()._detect_full_differences(original_text, edited_text, transcription_result)
        print(f"[_detect_full_differences] 結果: {len(result.differences)}個の差分")
        return result


# デバッグ版を使用
detector = DebugTextDifferenceDetector()
differences = detector.detect_differences(original_text, edited_text, None)

print("\n=== 差分検出結果 ===")
print(f"差分の数: {len(differences.differences)}")
for i, (diff_type, text, _) in enumerate(differences.differences):
    print(f"差分{i+1}: {diff_type.value}")
    print(f"  長さ: {len(text)}文字")
