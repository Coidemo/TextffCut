#!/usr/bin/env python3
"""
テキスト検索の問題を検証するスクリプト
"""
import json

from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult

# 文字起こし結果を読み込み
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

# TranscriptionResultオブジェクトを作成
transcription = TranscriptionResult.from_dict(data)

# 全文を取得
full_text = transcription.get_full_text()
print("=== 文字起こし全文（最初の500文字） ===")
print(full_text[:500])
print("...")

# ユーザーが指定したテキスト
edited_text = (
    "こっちまさかの配信されてなかったっす。こちらの配信ボタンと実は微妙に連動していなくて、はい、あの、バグりました。"
)
print("\n=== ユーザー指定テキスト ===")
print(edited_text)

# TextProcessorで差分検索
text_processor = TextProcessor()

# 通常の差分検索
print("\n=== 差分検索開始 ===")
diff = text_processor.find_differences(full_text, edited_text)

print(f"\n正規化前の元テキスト長: {len(full_text)}")
print(f"正規化前の編集テキスト長: {len(edited_text)}")
print(f"正規化後の元テキスト長: {len(diff.original_text)}")
print(f"正規化後の編集テキスト長: {len(diff.edited_text)}")

print(f"\n共通部分の数: {len(diff.common_positions)}")
for i, pos in enumerate(diff.common_positions):
    print(f"  共通部分{i+1}: 位置{pos.start}-{pos.end}, テキスト: '{pos.text}'")

print(f"\n追加文字: {diff.added_chars}")

# 時間範囲を取得
try:
    time_ranges = diff.get_time_ranges(transcription)
    print("\n=== 検出された時間範囲 ===")
    for i, (start, end) in enumerate(time_ranges):
        print(f"  範囲{i+1}: {start:.2f}秒 - {end:.2f}秒 (長さ: {end-start:.2f}秒)")
except Exception as e:
    print("\n=== エラー発生 ===")
    print(f"エラー: {e}")

# セグメント情報を確認
print("\n=== セグメント情報 ===")
for i, seg in enumerate(transcription.segments[:5]):  # 最初の5セグメント
    print(f"\nセグメント{i+1}: {seg.start:.1f}秒 - {seg.end:.1f}秒")
    print(f"  テキスト: {seg.text[:100]}...")

    # wordsの状態を確認
    if hasattr(seg, "words") and seg.words:
        null_count = sum(1 for w in seg.words if w.get("start") is None or w.get("end") is None)
        print(f"  words数: {len(seg.words)}, タイムスタンプなし: {null_count}")
    else:
        print("  words: なし")

# 特定のテキストがどのセグメントに含まれているか確認
print("\n=== テキスト検索 ===")
search_texts = ["こっちまさかの配信されてなかったっす", "配信ボタンと実は微妙に連動していなくて", "バグりました"]

for search_text in search_texts:
    print(f"\n'{search_text}' を検索...")
    found = False
    for i, seg in enumerate(transcription.segments):
        if search_text in seg.text:
            print(f"  → セグメント{i+1}で発見: {seg.start:.1f}秒 - {seg.end:.1f}秒")
            found = True
    if not found:
        print("  → 見つかりませんでした")
