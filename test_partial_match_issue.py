#!/usr/bin/env python3
"""
部分一致問題の詳細なデバッグ
"""

from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.entities.text_difference import DifferenceType

# 実際のシナリオ：元のテキストは長い文字起こし結果
original_text = """おはようございます。今日は良い天気ですね。
明日の予定について話しましょう。
会議は午後2時からです。
上司からのフィードバックまず自分ができてから言えよという気持ちになってしまうことがあります 多分あの意見と誰が言っているかを区別できてないというところが問題だと思っていて マネージャー自身ができているかどうかって超どうでもよいんですよねだってあの野球の監督の人が選手に指示をしたところでじゃあ監督が打てよって 言われても監督は打てないじゃないですかなのでそもそも仕事の質が違うのであって コードレビューは書き方について指示ができるが別に自分では書けないという人たくさんいるのでそこを一緒にしているとややこしいと思いますね これはプレイヤーあるあるなのでそこを区別できてないと苦しむと思いますあのメタ社のねマークザッカーバーグもエンジニアの中に入ってなんか 最近ってほどでもないんですけどプログラミングをやるイベントがあった時にあんまりにも書けなくてびっくりしたってエンジニアが言ってたんですよ なんかそういう記事があってそれって多分全然起こり得るだろうなと思っていてマークザッカーバーグが自分よりも書けない人ばっかり集めてたら会社成長しないので 自分よりも圧倒的にコードが書ける人たちをたくさん集めてこういうサービスやってっていう経営とか執行のトップレベルをやってるわけなので あのコードかけるかというと書けないと思います書けるんですけどねあのそんなに一流のエンジニアほど書けなくなっているはずなんですよ なので上司もコードレビューしたり公開た方がいいようは全然言えるがプレイヤーとしての仕事ができるかというのは別問題なので なので自分ができてから言えよっていうふうに思っているのはそもそもの出発点が違うかなと思いました はい区別した方がいいですねこれあのなんで言うかというと自分が上司になった時に自分のレベルでしか指示できない人って組織の上限をそこで定めてしまっているので個人のレベルに その組織のレベルが一致してしまうのですごく良くないのであのこういう考えの人が会社にいるとすごい迷惑っていうのがあったりしますねはい
それでは次の話題に移りましょう。
開発の進捗はどうですか？"""

# ユーザーが提供したテキスト（元のテキストの一部）
edited_text = """上司からのフィードバックまず自分ができてから言えよという気持ちになってしまうことがあります 多分あの意見と誰が言っているかを区別できてないというところが問題だと思っていて マネージャー自身ができているかどうかって超どうでもよいんですよねだってあの野球の監督の人が選手に指示をしたところでじゃあ監督が打てよって 言われても監督は打てないじゃないですかなのでそもそも仕事の質が違うのであって コードレビューは書き方について指示ができるが別に自分では書けないという人たくさんいるのでそこを一緒にしているとややこしいと思いますね これはプレイヤーあるあるなのでそこを区別できてないと苦しむと思いますあのメタ社のねマークザッカーバーグもエンジニアの中に入ってなんか 最近ってほどでもないんですけどプログラミングをやるイベントがあった時にあんまりにも書けなくてびっくりしたってエンジニアが言ってたんですよ なんかそういう記事があってそれって多分全然起こり得るだろうなと思っていてマークザッカーバーグが自分よりも書けない人ばっかり集めてたら会社成長しないので 自分よりも圧倒的にコードが書ける人たちをたくさん集めてこういうサービスやってっていう経営とか執行のトップレベルをやってるわけなので あのコードかけるかというと書けないと思います書けるんですけどねあのそんなに一流のエンジニアほど書けなくなっているはずなんですよ なので上司もコードレビューしたり公開た方がいいようは全然言えるがプレイヤーとしての仕事ができるかというのは別問題なので なので自分ができてから言えよっていうふうに思っているのはそもそもの出発点が違うかなと思いました はい区別した方がいいですねこれあのなんで言うかというと自分が上司になった時に自分のレベルでしか指示できない人って組織の上限をそこで定めてしまっているので個人のレベルに その組織のレベルが一致してしまうのですごく良くないのであのこういう考えの人が会社にいるとすごい迷惑っていうのがあったりしますねはい"""

print("=== 検証前の確認 ===")
print(f"元のテキストに編集テキストが含まれているか: {edited_text in original_text}")
print("")

# TranscriptionResultを作成（ダミー）
segments = [
    TranscriptionSegment(
        id="1",
        text=original_text,
        start=0.0,
        end=100.0,
        words=[],
        chars=[]
    )
]
transcription_result = TranscriptionResult(
    id="test-1",
    segments=segments,
    language="ja",
    original_audio_path="/dummy/path.wav",
    model_size="medium",
    processing_time=1.0
)

# TextDifferenceDetectorを使用
detector = TextDifferenceDetector()

# 内部メソッドを直接テスト
print("=== _remove_punctuation のテスト ===")
edited_no_punct = detector._remove_punctuation(edited_text)
print(f"句読点を除去した編集テキスト: {edited_no_punct[:50]}...")
print("")

print("=== 部分一致検索のテスト ===")
position = original_text.find(edited_no_punct)
print(f"句読点除去後の検索結果: {position}")
position_direct = original_text.find(edited_text)
print(f"直接検索の結果: {position_direct}")
print("")

# 差分検出を実行
differences = detector.detect_differences(original_text, edited_text, transcription_result)

print("=== 差分検出結果 ===")
print(f"元のテキスト長: {len(original_text)}文字")
print(f"編集テキスト長: {len(edited_text)}文字")
print(f"編集/元の比率: {len(edited_text) / len(original_text) * 100:.1f}%")
print(f"差分の数: {len(differences.differences)}")
print("")

for i, (diff_type, text, _) in enumerate(differences.differences):
    print(f"差分{i+1}: {diff_type.value}")
    print(f"  長さ: {len(text)}文字")
    if len(text) > 100:
        print(f"  内容: {text[:50]}...{text[-50:]}")
    else:
        print(f"  内容: {text}")
    print("")

# 判定結果
if all(diff_type == DifferenceType.ADDED for diff_type, _, _ in differences.differences):
    print("❌ 問題確認: すべてのテキストがADDED（赤色）として判定されています")
else:
    print("✅ 正常: 一部のテキストがUNCHANGED（緑色）として判定されています")