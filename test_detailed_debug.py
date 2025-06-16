#!/usr/bin/env python3
"""
詳細なデバッグ情報を出力
"""
import json
import logging
from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# デバッグログを有効化
logging.basicConfig(level=logging.DEBUG)

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# 問題の部分だけをテスト
test_text = "なかったっす。"

print("=== 詳細デバッグ ===")
print(f"検索テキスト: '{test_text}'")
print(f"検索テキストの長さ: {len(test_text)}文字")

# テキスト位置を確認
pos = full_text.find(test_text)
print(f"\n元テキスト内の位置: {pos}から{pos + len(test_text)}")
print(f"各文字の位置:")
for i, char in enumerate(test_text):
    print(f"  '{char}' : 位置 {pos + i}")

# セグメント0の該当部分を確認
seg = transcription.segments[0]
current_pos = 0

print(f"\n=== 該当するwordsを探索 ===")
for i, word in enumerate(seg.words):
    word_text = word.word if hasattr(word, 'word') else word.get('word', '')
    word_start = word.start if hasattr(word, 'start') else word.get('start')
    word_end = word.end if hasattr(word, 'end') else word.get('end')
    word_len = len(word_text)
    
    # 該当範囲のwordを表示
    if current_pos <= pos < current_pos + word_len or current_pos <= pos + len(test_text) - 1 < current_pos + word_len:
        duration = (word_end - word_start) if word_start and word_end else None
        print(f"word[{i}]: \"{word_text}\" pos={current_pos}-{current_pos+word_len}, start={word_start}, end={word_end}, duration={duration}")
        
        # 終了位置の判定
        if current_pos < pos + len(test_text) <= current_pos + word_len:
            print(f"  -> これが終了word！ end_pos={pos + len(test_text)}, current_pos+word_len={current_pos + word_len}")
            print(f"  -> end_pos == current_pos + word_len? {pos + len(test_text) == current_pos + word_len}")
            
            # 次のwordを確認
            if i + 1 < len(seg.words):
                next_word = seg.words[i + 1]
                next_text = next_word.word if hasattr(next_word, 'word') else next_word.get('word', '')
                print(f"  -> 次のword: \"{next_text}\"")
                if next_text in ['。', '、', '！', '？', '．', '，']:
                    print(f"  -> 次は句読点！ end_pos == current_pos + word_len + len(next)? {pos + len(test_text) == current_pos + word_len + len(next_text)}")
    
    current_pos += word_len

# 実際の差分検索を実行
print("\n=== 差分検索実行 ===")
text_processor = TextProcessor()
diff = text_processor.find_differences(full_text, test_text)
time_ranges = diff.get_time_ranges(transcription)

if time_ranges:
    for i, (start, end) in enumerate(time_ranges):
        print(f"時間範囲{i+1}: {start:.3f}秒 - {end:.3f}秒")