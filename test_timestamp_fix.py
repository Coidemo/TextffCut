#!/usr/bin/env python3
"""
タイムスタンプ修正のテスト
"""
import json
import logging
from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# デバッグログを有効化
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('core.text_processor')
logger.setLevel(logging.DEBUG)

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# 問題のテキストをテスト
test_text = "こっちまさかの配信されてなかったっす。こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"

print("=== タイムスタンプ修正テスト ===")
print(f"テスト文字列: {test_text}")
print()

text_processor = TextProcessor()
diff = text_processor.find_differences(full_text, test_text)
time_ranges = diff.get_time_ranges(transcription)

print("\n=== 結果 ===")
if time_ranges:
    print("検出された時間範囲:")
    for i, (start, end) in enumerate(time_ranges):
        print(f"  範囲{i+1}: {start:.3f}秒 - {end:.3f}秒")
else:
    print("時間範囲が見つかりませんでした")

print("\n期待される結果:")
print("  範囲1: 11.629秒 - 13.950秒")
print("  範囲2: 44.418秒 - 45.399秒")