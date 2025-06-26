#!/usr/bin/env python3
"""
現在のタイムスタンプ推定ロジックの問題を詳細に検証
"""
import json

json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

seg1 = data["segments"][0]
words = seg1["words"]

print("=== セグメント1の最初の部分のタイムスタンプ状況 ===")
print(f"セグメント: {seg1['start']:.1f}秒 - {seg1['end']:.1f}秒")
print(f"テキスト冒頭: {seg1['text'][:30]}...")

# 最初の30wordsを確認
print("\n最初の30words:")
for i in range(min(30, len(words))):
    w = words[i]
    ts_status = "✓" if w["start"] is not None else "✗"
    print(f"  [{i:2d}] {ts_status} '{w['word']}' ", end="")
    if w["start"] is not None:
        print(f"({w['start']:.2f}秒)")
    else:
        print("(タイムスタンプなし)")

# タイムスタンプがある最初のwordを探す
first_valid_idx = None
for i, w in enumerate(words):
    if w["start"] is not None:
        first_valid_idx = i
        break

print(
    f"\n最初の有効なタイムスタンプ: word[{first_valid_idx}] = '{words[first_valid_idx]['word']}' ({words[first_valid_idx]['start']:.2f}秒)"
)

# 現在の推定ロジックをシミュレート
print("\n=== 現在の推定ロジックのシミュレーション ===")

# 例: 最初の'Y'の推定
word_idx = 0
print(f"\nword[{word_idx}] = '{words[word_idx]['word']}' の推定:")

# 1. 前後のタイムスタンプを探す
prev_timestamps = []
next_timestamps = []

# 前方検索（最大5つ前まで） - 最初なので前はない
for prev_idx in range(max(0, word_idx - 5), word_idx):
    if words[prev_idx]["start"] is not None:
        prev_timestamps.append((prev_idx, words[prev_idx]["start"], words[prev_idx]["end"]))

# 後方検索（最大5つ後まで）
for next_idx in range(word_idx + 1, min(len(words), word_idx + 6)):
    if words[next_idx]["start"] is not None:
        next_timestamps.append((next_idx, words[next_idx]["start"], words[next_idx]["end"]))

print(f"  前のタイムスタンプ: {len(prev_timestamps)}個")
print(f"  後のタイムスタンプ: {len(next_timestamps)}個")

if next_timestamps and not prev_timestamps:
    # 後のタイムスタンプのみある場合
    next_idx, next_start, next_end = next_timestamps[0]
    print(f"  最初の有効なタイムスタンプ: word[{next_idx}] = '{words[next_idx]['word']}' ({next_start:.2f}秒)")

    # 現在のロジック：セグメント全体から推定
    segment_duration = seg1["end"] - seg1["start"]
    word_ratio = word_idx / len(words)
    estimated_start = seg1["start"] + segment_duration * word_ratio
    print(f"  現在の推定: {estimated_start:.2f}秒 (セグメント全体の{word_ratio:.1%}の位置)")

    # 問題点
    print(f"\n  問題: 実際の最初の有効タイムスタンプは{next_start:.2f}秒なのに、")
    print(f"       推定値は{estimated_start:.2f}秒（差: {next_start - estimated_start:.2f}秒）")

# 改善案のデモ
print("\n=== 改善案のデモ ===")
print("案1: 最初の有効なタイムスタンプまでの文字数比率で推定")

# 最初の有効なタイムスタンプまでの文字数を数える
chars_until_first_valid = 0
for i in range(first_valid_idx):
    chars_until_first_valid += len(words[i]["word"])

print(f"  最初の{first_valid_idx}個のwordの文字数: {chars_until_first_valid}")
print(f"  最初の有効タイムスタンプ: {words[first_valid_idx]['start']:.2f}秒")

# 改善された推定
improved_estimate = words[first_valid_idx]["start"] * (word_idx / first_valid_idx) if first_valid_idx > 0 else 0
print(f"  改善された推定: {improved_estimate:.2f}秒")

print("\n案2: セグメントの実際の発話開始時間を考慮")
print("  多くの場合、セグメントの最初は無音や間がある")
print("  最初の有効なタイムスタンプを発話開始と見なす")
