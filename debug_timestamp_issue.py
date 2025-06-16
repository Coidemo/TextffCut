#!/usr/bin/env python3
"""
タイムスタンプ問題のデバッグ
"""
import json
from core.transcription import TranscriptionResult

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# 「っす」の位置を確認
target = "なかったっす。"
pos = full_text.find(target)
if pos >= 0:
    print(f"「{target}」の位置: {pos}から{pos + len(target)}")
    print(f"文字数: {len(target)}")
    
    # 「っす。」の個別文字位置
    sho_pos = full_text.find("っ", pos)
    su_pos = full_text.find("す", sho_pos)
    maru_pos = full_text.find("。", su_pos)
    
    print(f"\n個別文字の位置:")
    print(f"  「っ」: 位置 {sho_pos}")
    print(f"  「す」: 位置 {su_pos}")
    print(f"  「。」: 位置 {maru_pos}")
    
    # セグメント0のwords確認
    seg = transcription.segments[0]
    current_pos = 0
    
    print(f"\n=== セグメント0のwordsをチェック ===")
    for i, word in enumerate(seg.words):
        word_text = word.word if hasattr(word, 'word') else word.get('word', '')
        word_len = len(word_text)
        
        # 「っ」「す」「。」の位置にある単語を表示
        if current_pos <= sho_pos < current_pos + word_len:
            print(f"位置{sho_pos}の「っ」: word[{i}]=\"{word_text}\" (位置{current_pos}-{current_pos+word_len})")
        if current_pos <= su_pos < current_pos + word_len:
            print(f"位置{su_pos}の「す」: word[{i}]=\"{word_text}\" (位置{current_pos}-{current_pos+word_len})")
        if current_pos <= maru_pos < current_pos + word_len:
            print(f"位置{maru_pos}の「。」: word[{i}]=\"{word_text}\" (位置{current_pos}-{current_pos+word_len})")
            
        current_pos += word_len