"""
フィラー関連の定数定義

brute_force_clip_generator.py と early_filler_detection.py で共有する。
"""

from __future__ import annotations

# セグメント全体がフィラーのみかを判定する
# （これらのセグメントはtime_rangesから完全に除外される）
FILLER_ONLY_TEXTS = {
    "はい",
    "うん",
    "まあ",
    "あの",
    "で",
    "なんか",
    "えー",
    "えーと",
    "えっと",
    "うーん",
    "んー",
    "ね",
    "そう",
    "そうですね",
    "まあまあ",
    "ちょっと",
    "!",
    "っていう",
    "多分",
    "なので",
    "ただ",
    "別に",
    "普通に",
    "まあそうですね",
    "そうそう",
    "そうそうそう",
    "なるほど",
    "確かに",
    "なんかその",
    "あれなんですけれども",
    "なのでね",
    # 口癖系
    "ていうか",
    "まあね",
    "そうなんですよ",
    "あーなるほど",
    "そうそうそうそう",
    "うんうん",
    "うんうんうん",
    "はいはいはい",
    "まあまあまあ",
    "いやいやいや",
    "あーそうですね",
    # 配信者特有の独り言
    "ちょっと待ってね",
    "えーっとですね",
    "どこだっけ",
    "何の話だっけ",
    "何話そうと思ったんだっけ",
}

# 純粋なフィラー（wordsタイムスタンプでスキップする対象）
# テキスト内の任意の位置でマッチさせる
# 長い順にマッチさせる（「まあまあ」→「まあ」の順）
FILLER_WORDS = sorted(
    [
        "えーっと",
        "えっとね",
        "えっと",
        "えーと",
        "あのー",
        "まあまあ",
        "まあその",
        "まあね",
        "なんかその",
        "なんかこう",
        "なんか",
        "そうですね",
        "あのね",
        "えー",
        "あの",
        "まあ",
        "まぁ",
        "うーん",
        "んー",
        "でまあ",
        "でなんか",
        "であの",
        "でその",
        "やっぱ",
        "やっぱり",
        "的な",
        "みたいな感じで",
        "じゃないですか",
        "どういうことかというと",
        "っていうのは",
        "何て言うんですかね",
        "ぶっちゃけ",
        "簡単に言うと",
        "ざっくり言うと",
        "要は",
    ],
    key=len,
    reverse=True,
)

# 文法的用法とフィラー用法の両方を持つ語
# GiNZA POS + 文脈ルールで判定し、判定不能ならLLMに委譲する
AMBIGUOUS_FILLERS = {
    "なんか",  # フィラー vs 「何か」（不定代名詞）
    "あの",  # フィラー vs 連体詞「あの人」
    "まあ",  # フィラー vs 副詞「まあいいか」
    "まぁ",  # 同上
    "やっぱ",  # フィラー vs 副詞「やっぱ○○だ」
    "やっぱり",  # 同上
    "的な",  # フィラー vs 接尾辞「具体的な」
    "みたいな感じで",  # フィラー vs 比喩「猫みたいな感じで」
    "とか",  # フィラー vs 並列助詞「AとかBとか」
    "っていうのは",  # フィラー vs 主題提示
    "じゃないですか",  # フィラー vs 実際の否定疑問
    "ぶっちゃけ",  # フィラー vs 副詞的用法
    "要は",  # フィラー vs 接続詞「要は○○だ」
}

# ノイズ検出用キーワード
_MIC_KEYWORDS = ["マイク", "音声", "聞こえ", "ミュート", "音が", "音量", "イヤホン"]
_FILLER_WORDS_SET = {"えー", "えーと", "あー", "あのー", "うーん", "まあ", "んー", "えっと", "あの"}
_GREETING_PATTERNS = [
    "おはようございます",
    "こんにちは",
    "こんばんは",
    "はいどうも",
    "お疲れ様",
    "よろしくお願い",
    "ありがとうございます",
    "ここから本編",
    "本編です",
    "本編スタート",
]
_APOLOGY_KEYWORDS = ["すいません", "すみません", "ごめんなさい", "申し訳"]

_PREAMBLE_KEYWORDS = [
    "話したいと思い",
    "話していきたいと思い",
    "話をしたいなと思",
    "解説していきます",
    "話変わるんですけど",
    "本題なんですけれども",
    "今日用意してる",
    "今日のテーマは",
    "質問読みますね",
    "質問読み上げます",
    "コメント読みます",
    "スパチャ読みます",
    "次の質問いきます",
    "次のテーマなんですけど",
]


def detect_noise_tag(text: str, text_length_limit: int = 40) -> str | None:
    """セグメントテキストからノイズタグを検出（gateway非依存版）。

    Returns:
        "[NOISE:mic]", "[NOISE:filler]", "[NOISE:greeting]", "[NOISE:apology]" or None
    """
    text = text.strip()

    # [NOISE:mic]
    if any(kw in text for kw in _MIC_KEYWORDS) and len(text) < text_length_limit:
        return "[NOISE:mic]"

    # [NOISE:filler]
    cleaned = text.replace("　", "").replace(" ", "").replace("、", "").replace("。", "")
    if cleaned in _FILLER_WORDS_SET or (len(cleaned) <= 4 and any(cleaned.startswith(f) for f in _FILLER_WORDS_SET)):
        return "[NOISE:filler]"

    # [NOISE:greeting]
    if any(text.startswith(g) or text == g for g in _GREETING_PATTERNS) and len(text) < 30:
        return "[NOISE:greeting]"

    # [NOISE:preamble]
    if any(kw in text for kw in _PREAMBLE_KEYWORDS) and len(text) < 80:
        return "[NOISE:preamble]"

    # [NOISE:apology]
    if any(kw in text for kw in _APOLOGY_KEYWORDS) and len(text) < 20:
        return "[NOISE:apology]"

    return None
