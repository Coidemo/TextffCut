#!/usr/bin/env python3
"""
テキスト検索の詳細分析
"""
import json

from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)

# ユーザーが指定したテキスト
edited_text = (
    "こっちまさかの配信されてなかったっす。こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"
)

# 検索対象の部分テキスト
target_texts = [
    "こっちまさかの配信されてなかったっす",
    "こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました",
]

print("=== 各部分の詳細位置分析 ===")

# 全文から各部分の位置を調べる
full_text = transcription.get_full_text()

for target in target_texts:
    print(f"\n'{target}' の分析:")

    # 全文での位置を探す
    pos = full_text.find(target)
    if pos != -1:
        print(f"  全文での位置: {pos}文字目")

        # どのセグメントに含まれているか
        current_pos = 0
        for i, seg in enumerate(transcription.segments):
            seg_len = len(seg.text)
            if current_pos <= pos < current_pos + seg_len:
                print(f"  セグメント{i + 1}に含まれる（{seg.start:.1f}秒 - {seg.end:.1f}秒）")
                print(f"  セグメント内での位置: {pos - current_pos}文字目")

                # wordsの状態を確認
                if hasattr(seg, "words") and seg.words:
                    # セグメント内でのターゲット位置
                    seg_target_start = pos - current_pos
                    seg_target_end = seg_target_start + len(target)

                    # 対応するwordsを探す
                    word_pos = 0
                    target_words = []
                    for word in seg.words:
                        word_text = word.get("word", "")
                        word_len = len(word_text)

                        # このwordがターゲット範囲に含まれるか
                        if word_pos < seg_target_end and word_pos + word_len > seg_target_start:
                            target_words.append(
                                {
                                    "word": word_text,
                                    "start": word.get("start"),
                                    "end": word.get("end"),
                                    "position": word_pos,
                                }
                            )

                        word_pos += word_len

                    print(f"\n  対応するwords（{len(target_words)}個）:")
                    for w in target_words[:5]:  # 最初の5個
                        if w["start"] is None:
                            print(f"    '{w['word']}' - タイムスタンプなし（位置: {w['position']}）")
                        else:
                            print(f"    '{w['word']}' - {w['start']:.2f}秒～{w['end']:.2f}秒（位置: {w['position']}）")

                    if len(target_words) > 5:
                        print(f"    ... 他{len(target_words) - 5}個")

                    # 有効なタイムスタンプを持つ最初と最後のwordを見つける
                    first_valid = None
                    last_valid = None

                    for w in target_words:
                        if w["start"] is not None:
                            if first_valid is None:
                                first_valid = w
                            last_valid = w

                    if first_valid and last_valid:
                        print(f"\n  推定される実際の時間範囲: {first_valid['start']:.2f}秒 - {last_valid['end']:.2f}秒")
                    else:
                        print("\n  警告: 有効なタイムスタンプを持つwordが見つかりません")
                        # セグメント全体の時間を使用
                        print(f"  セグメント全体の時間を使用: {seg.start:.2f}秒 - {seg.end:.2f}秒")

                break
            current_pos += seg_len

# 区切り文字を使った検索のテスト
print("\n\n=== 区切り文字（---）を使った検索テスト ===")
edited_with_separator = "こっちまさかの配信されてなかったっす。---こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"

text_processor = TextProcessor()
time_ranges = text_processor.find_differences_with_separator(full_text, edited_with_separator, transcription, "---")

print("\n区切り文字を使った場合の時間範囲:")
for i, (start, end) in enumerate(time_ranges):
    print(f"  範囲{i + 1}: {start:.2f}秒 - {end:.2f}秒 (長さ: {end - start:.2f}秒)")
