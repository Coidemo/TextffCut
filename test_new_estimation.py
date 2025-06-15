#!/usr/bin/env python3
"""
新しいフォールバック階層アプローチのテスト
"""
import json
from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# 文字起こし結果を読み込み
json_path = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# ユーザーが指定したテキスト
edited_text = "こっちまさかの配信されてなかったっす。こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"

print("=== 新しいフォールバック階層アプローチのテスト ===")
print(f"ユーザー指定テキスト: {edited_text}")

# TextProcessorで差分検索
text_processor = TextProcessor()
diff = text_processor.find_differences(full_text, edited_text)

print(f"\n共通部分の数: {len(diff.common_positions)}")
for i, pos in enumerate(diff.common_positions):
    print(f"  共通部分{i+1}: '{pos.text}'")

# 時間範囲を取得
print("\n=== 時間範囲の取得 ===")
try:
    time_ranges = diff.get_time_ranges(transcription)
    print(f"\n検出された時間範囲:")
    for i, (start, end) in enumerate(time_ranges):
        print(f"  範囲{i+1}: {start:.2f}秒 - {end:.2f}秒 (長さ: {end-start:.2f}秒)")
    
    # 全体の時間を計算
    if time_ranges:
        total_start = min(start for start, _ in time_ranges)
        total_end = max(end for _, end in time_ranges)
        print(f"\n全体: {total_start:.2f}秒 - {total_end:.2f}秒 (総長: {total_end-total_start:.2f}秒)")
        
except Exception as e:
    print(f"\nエラー発生: {e}")
    import traceback
    traceback.print_exc()

# セグメント1の最初のwordsを詳細確認
print("\n=== セグメント1の最初のwords詳細 ===")
seg1 = transcription.segments[0]
print(f"セグメント1: {seg1.start:.1f}秒 - {seg1.end:.1f}秒")

# 最初の10wordsとその推定状況を確認
print("\n最初の10words:")
for i in range(min(10, len(seg1.words))):
    word = seg1.words[i]
    word_text = word.get('word', '')
    word_start = word.get('start')
    word_end = word.get('end')
    
    if word_start is None:
        print(f"  [{i:2d}] '{word_text}' - タイムスタンプなし → 推定が必要")
    else:
        print(f"  [{i:2d}] '{word_text}' - {word_start:.2f}秒")

print("\n=== テスト完了 ===")