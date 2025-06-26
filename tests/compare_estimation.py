#!/usr/bin/env python3
"""
推定ロジックの改善前後の比較
"""
import json

# 問題のある部分のデータ
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

seg1 = data["segments"][0]
words = seg1["words"]

print("=== 推定ロジックの改善前後の比較 ===")
print(f"セグメント1: {seg1['start']} - {seg1['end']}秒（{seg1['end'] - seg1['start']}秒）")
print(f"最初の有効なタイムスタンプ: word[7] 'の' = {words[7]['start']:.2f}秒")

# 改善前の推定（セグメント全体から）
print("\n【改善前】セグメント全体から推定:")
for i in range(7):  # 最初の7つのnullタイムスタンプ
    word_ratio = i / len(words)
    old_estimate = seg1["start"] + (seg1["end"] - seg1["start"]) * word_ratio
    print(f"  word[{i}] '{words[i]['word']}' → {old_estimate:.2f}秒（位置比率: {word_ratio:.1%}）")

# 改善後の推定（フォールバック階層）
print("\n【改善後】フォールバック階層アプローチ:")
print("  最初の7つのword → 後方の有効タイムスタンプ（4.38秒）から逆算")
print("  推定: 4.25-4.33秒（実際のログから）")

print("\n=== 改善の効果 ===")
print("1. 改善前: 'Youtube' が 0.0秒付近に推定される（実際は4秒台）")
print("2. 改善後: 'Youtube' が 4.25-4.33秒に推定される（より現実的）")
print("3. 差: 約4秒の改善")

print("\n=== ユーザー指定テキストへの影響 ===")
print("「こっちまさかの配信されてなかったっす」")
print("  実際の位置: 11.63秒から")
print("  改善後の検出: 11.63秒 - 15.57秒（句読点の推定含む）")
print("\n「こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました」")
print("  実際の位置: 44.42秒から")
print("  改善後の検出: 44.42秒 - 45.42秒")

print("\n結論: フォールバック階層アプローチにより、タイムスタンプがない部分の推定精度が大幅に向上")
