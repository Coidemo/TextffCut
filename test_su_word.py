#!/usr/bin/env python3
"""
「す」のwordを詳しく確認
"""
import json
from core.transcription import TranscriptionResult

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# 問題の部分
test_text = "なかったっす。"
pos = full_text.find(test_text)
end_pos = pos + len(test_text)  # 73

# セグメント0の該当部分を確認
seg = transcription.segments[0]
current_pos = 0

print(f"検索範囲: 位置{pos}から{end_pos}")
print(f"\n=== word詳細 (位置66-73の範囲) ===")

for i, word in enumerate(seg.words):
    word_text = word.word if hasattr(word, 'word') else word.get('word', '')
    word_start = word.start if hasattr(word, 'start') else word.get('start')
    word_end = word.end if hasattr(word, 'end') else word.get('end')
    word_len = len(word_text)
    
    # 該当範囲のwordを表示
    if 66 <= i <= 73:
        duration = (word_end - word_start) if word_start and word_end else None
        print(f"word[{i}]: \"{word_text}\" pos={current_pos}-{current_pos+word_len}, start={word_start}, end={word_end}, duration={duration}")
        
        # 特に「す」に注目
        if word_text == "す" and current_pos == 71:
            print(f"  ★ これが「す」！")
            print(f"  -> current_pos < end_pos? {current_pos < end_pos}")
            print(f"  -> end_pos <= current_pos + word_len? {end_pos <= current_pos + word_len}")
            print(f"  -> 条件 'current_pos < end_pos <= current_pos + word_len'? {current_pos < end_pos <= current_pos + word_len}")
    
    current_pos += word_len