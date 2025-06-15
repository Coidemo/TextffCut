#!/usr/bin/env python3
"""
タイムスタンプ推定ロジックの問題を分析
"""
import json

# 問題のある部分のデータを抽出
json_path = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 最初のセグメントのwordsを分析
seg1 = data['segments'][0]
print("=== セグメント1のwords分析 ===")
print(f"セグメント時間: {seg1['start']} - {seg1['end']}秒")
print(f"テキスト: {seg1['text'][:100]}...")

# 「こっちまさかの配信されてなかったっす」の部分を探す
target = "こっちまさかの配信されてなかったっす"
target_start = seg1['text'].find(target)
print(f"\n'{target}' の位置: {target_start}文字目")

# 該当するwordsを探す
current_pos = 0
target_words = []
print("\n=== 該当部分のwords ===")
for i, word in enumerate(seg1['words']):
    word_text = word['word']
    word_len = len(word_text)
    
    if current_pos <= target_start + len(target) and current_pos + word_len > target_start:
        target_words.append({
            'index': i,
            'word': word_text,
            'start': word['start'],
            'end': word['end'],
            'position': current_pos
        })
    
    current_pos += word_len

# 結果を表示
print(f"\n該当words数: {len(target_words)}")
for w in target_words[:10]:
    if w['start'] is None:
        print(f"  [{w['index']:3d}] '{w['word']}' - タイムスタンプなし (位置: {w['position']})")
    else:
        print(f"  [{w['index']:3d}] '{w['word']}' - {w['start']:.2f}～{w['end']:.2f}秒 (位置: {w['position']})")

# タイムスタンプがない文字の前後を調査
print("\n=== タイムスタンプ推定の問題分析 ===")
print("最初の'Y'のケース:")
print("  - 前のword: なし（最初のword）")
print("  - 後のword: 'o' (タイムスタンプなし)")
print("  → セグメント全体から推定するしかない")

# 実際の推定値を計算してみる
print("\n=== 現在の推定ロジックの問題 ===")
print("1. 最初の数文字（Youtube）はすべてタイムスタンプがない")
print("2. セグメント全体の時間（0-27秒）から位置比率で推定")
print("3. しかし、実際の「こっちまさかの」は11.63秒から始まっている")
print("4. つまり、最初の11秒分は別の内容（挨拶など）")

# より正確な推定方法の提案
print("\n=== 改善案 ===")
print("1. タイムスタンプがあるwordの密度を考慮")
print("2. 近隣の有効なタイムスタンプから線形補間")
print("3. セグメント全体ではなく、局所的な範囲で推定")
print("4. 最悪の場合はセグメント境界を使用（現在の動作）")