#!/usr/bin/env python3
"""
パフォーマンス最適化の効果測定
"""
import json
import time
from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# ログレベルを一時的に変更
import logging
logging.getLogger('core.text_processor').setLevel(logging.ERROR)

# 文字起こし結果を読み込み
json_path = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

transcription = TranscriptionResult.from_dict(data)
full_text = transcription.get_full_text()

# ユーザーが指定したテキスト
edited_text = "こっちまさかの配信されてなかったっす。こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"

print("=== パフォーマンステスト ===")

# 複数回実行して平均時間を計測
times = []
for i in range(5):
    start_time = time.time()
    
    text_processor = TextProcessor()
    diff = text_processor.find_differences(full_text, edited_text)
    time_ranges = diff.get_time_ranges(transcription)
    
    end_time = time.time()
    elapsed = end_time - start_time
    times.append(elapsed)
    print(f"実行{i+1}: {elapsed:.3f}秒")

avg_time = sum(times) / len(times)
print(f"\n平均実行時間: {avg_time:.3f}秒")

print(f"\n検出された時間範囲:")
for i, (start, end) in enumerate(time_ranges):
    print(f"  範囲{i+1}: {start:.2f}秒 - {end:.2f}秒")

# メモリ使用量の確認
import sys
print(f"\n推定メモリ使用量:")
print(f"  TranscriptionResult: {sys.getsizeof(transcription) / 1024:.1f} KB")
print(f"  全文テキスト: {sys.getsizeof(full_text) / 1024:.1f} KB")