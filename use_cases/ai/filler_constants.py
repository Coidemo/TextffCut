"""
フィラー関連の定数定義

brute_force_clip_generator.py と word_level_filler_polish.py で共有する。
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
    ],
    key=len,
    reverse=True,
)

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

    # [NOISE:apology]
    if any(kw in text for kw in _APOLOGY_KEYWORDS) and len(text) < 20:
        return "[NOISE:apology]"

    return None
