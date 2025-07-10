"""
音声プレビューに「とか」が含まれる問題の調査
"""

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.value_objects import TimeRange
import json

# 問題のテキスト
original_text = "ちゃんとした文章とかで表現していない"
edited_text = "ちゃんとした文章で表現していない"

print("="*80)
print("音声プレビュー問題の調査")
print("="*80)
print(f"原文: \"{original_text}\"")
print(f"編集: \"{edited_text}\"")
print(f"削除された部分: \"とか\"")
print()

# SequenceMatcherで差分検出
print("【1. 差分検出】")
gateway = SequenceMatcherTextProcessorGateway()
diff = gateway.find_differences(original_text, edited_text)

print("\n差分検出結果:")
for i, (diff_type, text, positions) in enumerate(diff.differences):
    print(f"\n{i+1}. タイプ: {diff_type.value}")
    print(f"   テキスト: \"{text}\"")
    if positions:
        print(f"   位置: {positions}")

# 時間範囲を計算するためのダミーデータを作成
print("\n" + "-"*40)
print("\n【2. 時間範囲の計算】")

# ダミーの文字起こし結果を作成（1文字1秒の単純なケース）
segments = []
words = []
for i, char in enumerate(original_text):
    words.append({
        "word": char,
        "start": float(i),
        "end": float(i + 1),
        "confidence": 1.0
    })

# セグメントを作成
segment = TranscriptionSegment(
    id="0",
    start=0.0,
    end=float(len(original_text)),
    text=original_text,
    words=words
)

# TranscriptionResultを作成（textプロパティは自動計算される）
transcription_result = TranscriptionResult(
    id="test-id",
    video_id="test-video",
    duration=float(len(original_text)),
    segments=[segment],
    language="ja",
    model_size="large"
)

# 時間範囲を計算
print("\nget_time_rangesを呼び出し中...")
try:
    time_ranges = gateway.get_time_ranges(diff, transcription_result)
    
    print(f"\n計算された時間範囲: {len(time_ranges)}個")
    for i, tr in enumerate(time_ranges):
        print(f"\n時間範囲{i+1}:")
        print(f"  開始: {tr.start}秒")
        print(f"  終了: {tr.end}秒")
        print(f"  継続時間: {tr.end - tr.start}秒")
        
        # この時間範囲が原文のどの部分に対応するか確認
        start_idx = int(tr.start)
        end_idx = int(tr.end)
        if 0 <= start_idx < len(original_text) and 0 <= end_idx <= len(original_text):
            extracted_text = original_text[start_idx:end_idx]
            print(f"  対応するテキスト: \"{extracted_text}\"")
            if "とか" in extracted_text:
                print("  ⚠️ 警告: この範囲に「とか」が含まれています！")
        
except Exception as e:
    print(f"\nエラー: {e}")
    import traceback
    traceback.print_exc()

# 問題の診断
print("\n" + "="*80)
print("\n【診断】")

# UNCHANGEDの位置情報を詳しく調べる
unchanged_blocks = [(text, positions) for diff_type, text, positions in diff.differences if diff_type == DifferenceType.UNCHANGED]

print(f"\nUNCHANGEDブロック数: {len(unchanged_blocks)}")
for i, (text, positions) in enumerate(unchanged_blocks):
    print(f"\nブロック{i+1}: \"{text}\"")
    if positions:
        for j, (start, end) in enumerate(positions):
            print(f"  位置{j+1}: {start}-{end}")
            # 原文での実際のテキストを確認
            actual = original_text[start:end]
            print(f"  原文での内容: \"{actual}\"")
            if actual != text:
                print("  ⚠️ 問題: 差分のテキストと原文の内容が一致しません！")
                print(f"     期待: \"{text}\"")
                print(f"     実際: \"{actual}\"")

# 期待される時間範囲
print("\n\n【期待される時間範囲】")
print("1. 「ちゃんとした文章」: 0-8秒")
print("2. 「で表現していない」: 10-18秒（「とか」の2秒分をスキップ）")

print("\n\n【結論】")
print("時間範囲の計算で、削除された「とか」の部分（8-10秒）も含まれてしまっている可能性があります。")
print("これにより、音声プレビューに「とか」が含まれることになります。")