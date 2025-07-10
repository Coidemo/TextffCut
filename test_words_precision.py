"""
wordsレベルの精度確認テスト
"""

import json
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway

# JSON to object converter
def dict_to_obj(d):
    if isinstance(d, dict):
        obj = SimpleNamespace()
        for k, v in d.items():
            setattr(obj, k, dict_to_obj(v))
        return obj
    elif isinstance(d, list):
        return [dict_to_obj(item) for item in d]
    else:
        return d

# 文字起こし結果を読み込む
print("=== Wordsレベルの精度確認 ===\n")

try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
except FileNotFoundError:
    print("警告: 実際の文字起こしファイルが見つかりません。サンプルデータで確認します。")
    # サンプルデータ
    legacy_result = SimpleNamespace(
        text="バイアスがかかってしまわないために一定の指針となる",
        segments=[
            {
                "id": "0",
                "start": 0.0,
                "end": 3.0,
                "text": "バイアスがかかってしまわないために一定の指針となる",
                "words": [
                    {"word": "バ", "start": 0.0, "end": 0.1},
                    {"word": "イ", "start": 0.1, "end": 0.2},
                    {"word": "ア", "start": 0.2, "end": 0.3},
                    {"word": "ス", "start": 0.3, "end": 0.4},
                    {"word": "が", "start": 0.4, "end": 0.5},
                    {"word": "か", "start": 0.5, "end": 0.6},
                    {"word": "か", "start": 0.6, "end": 0.7},
                    {"word": "っ", "start": 0.7, "end": 0.8},
                    {"word": "て", "start": 0.8, "end": 0.9},
                    {"word": "し", "start": 0.9, "end": 1.0},
                    {"word": "ま", "start": 1.0, "end": 1.1},
                    {"word": "わ", "start": 1.1, "end": 1.2},
                    {"word": "な", "start": 1.2, "end": 1.3},
                    {"word": "い", "start": 1.3, "end": 1.4},
                    {"word": "た", "start": 1.4, "end": 1.5},
                    {"word": "め", "start": 1.5, "end": 1.6},
                    {"word": "に", "start": 1.6, "end": 1.7},
                    {"word": "一", "start": 1.7, "end": 1.8},
                    {"word": "定", "start": 1.8, "end": 1.9},
                    {"word": "の", "start": 1.9, "end": 2.0},
                    {"word": "指", "start": 2.0, "end": 2.1},
                    {"word": "針", "start": 2.1, "end": 2.2},
                    {"word": "と", "start": 2.2, "end": 2.3},
                    {"word": "な", "start": 2.3, "end": 2.4},
                    {"word": "る", "start": 2.4, "end": 2.5},
                ]
            }
        ]
    )

# ドメイン形式に変換
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)

# CharacterArrayBuilderで文字配列を構築
builder = CharacterArrayBuilder()
char_array, full_text = builder.build_from_transcription(domain_result)

print(f"1. 文字配列の構築結果:")
print(f"   - 文字数: {len(char_array)}")
print(f"   - 再構築テキスト: {full_text[:50]}...")

# 最初の10文字の詳細を表示
print("\n2. 最初の10文字の詳細:")
print("   文字 | 開始時間 | 終了時間 | 継続時間")
print("   " + "-" * 40)
for i, char_info in enumerate(char_array[:10]):
    duration = char_info.end - char_info.start
    print(f"   {char_info.char}    | {char_info.start:8.3f} | {char_info.end:8.3f} | {duration:8.3f}")

# 連続性チェック
print("\n3. タイムスタンプの連続性チェック:")
gaps = []
for i in range(1, min(20, len(char_array))):
    prev_char = char_array[i-1]
    curr_char = char_array[i]
    gap = curr_char.start - prev_char.end
    if abs(gap) > 0.001:  # 1ミリ秒以上のギャップ
        gaps.append((i, prev_char.char, curr_char.char, gap))

if gaps:
    print("   ギャップが検出されました:")
    for i, prev, curr, gap in gaps[:5]:
        print(f"   - 位置{i}: '{prev}' → '{curr}' (ギャップ: {gap:.3f}秒)")
else:
    print("   ✓ タイムスタンプは連続しています")

# 編集テキストとのマッチングテスト
print("\n4. 編集テキストとのマッチングテスト:")
edited_text = "バイアスがかかってしまわないために指針となる"  # 「一定の」を削除

gateway = SequenceMatcherTextProcessorGateway()
diff = gateway.find_differences(full_text, edited_text)

# マッチした部分の時間精度を確認
print(f"\n5. マッチした部分の時間精度:")
for i, (diff_type, text, positions) in enumerate(diff.differences):
    if diff_type.value == "unchanged" and positions:
        start_pos, end_pos = positions[0]
        if 0 <= start_pos < len(char_array) and 0 <= end_pos <= len(char_array):
            start_char = char_array[start_pos]
            end_char = char_array[min(end_pos - 1, len(char_array) - 1)]
            
            print(f"\n   マッチ{i+1}: \"{text[:20]}...\"" if len(text) > 20 else f"\n   マッチ{i+1}: \"{text}\"")
            print(f"   - 文字位置: {start_pos}-{end_pos}")
            print(f"   - 開始文字: '{start_char.char}' (時間: {start_char.start:.3f}秒)")
            print(f"   - 終了文字: '{end_char.char}' (時間: {end_char.end:.3f}秒)")
            print(f"   - 合計時間: {end_char.end - start_char.start:.3f}秒")

# wordsの有無を確認
print("\n6. Wordsフィールドの存在確認:")
has_words_count = 0
no_words_count = 0
for segment in domain_result.segments:
    if hasattr(segment, 'words') and segment.words:
        has_words_count += 1
    else:
        no_words_count += 1

print(f"   - wordsありセグメント: {has_words_count}個")
print(f"   - wordsなしセグメント: {no_words_count}個")

if has_words_count > 0:
    print("\n   ✓ wordsレベルの精密なタイムスタンプが使用されています")
else:
    print("\n   ⚠ wordsレベルのタイムスタンプが存在しません（線形補間が使用されます）")