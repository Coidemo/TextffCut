"""
処理の精度を確認するテスト
"""

import json
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter
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

print("=== 精度確認テスト ===\n")

# 文字起こしデータを読み込む
with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    legacy_result = dict_to_obj(data)
    
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)

gateway = SequenceMatcherTextProcessorGateway()

# テストケース1: 基本的な差分検出
print("【テストケース1: 基本的な差分検出】")
test_text1 = """バイアスがかかってしまわないために指針となる考え方などありますか"""

from domain.use_cases.character_array_builder import CharacterArrayBuilder
builder = CharacterArrayBuilder()
char_array, full_text = builder.build_from_transcription(domain_result)

diff1 = gateway.find_differences(full_text, test_text1, skip_normalization=True)
time_ranges1 = gateway.get_time_ranges(diff1, domain_result)

print(f"時間範囲数: {len(time_ranges1)}")
for i, tr in enumerate(time_ranges1):
    print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")

# テストケース2: 境界調整マーカー付き
print("\n【テストケース2: 境界調整マーカー付き】")
test_text2 = """バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか"""

diff2 = gateway.find_differences(full_text, test_text2, skip_normalization=True)
time_ranges2 = gateway.get_time_ranges(diff2, domain_result)

print(f"時間範囲数: {len(time_ranges2)}")
for i, tr in enumerate(time_ranges2):
    print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")

# 精度の比較
print("\n【精度の比較】")
if len(time_ranges1) == 2 and len(time_ranges2) == 2:
    print("範囲1の差:")
    print(f"  開始: {time_ranges2[0].start - time_ranges1[0].start:.3f}秒")
    print(f"  終了: {time_ranges2[0].end - time_ranges1[0].end:.3f}秒")
    print("範囲2の差:")
    print(f"  開始: {time_ranges2[1].start - time_ranges1[1].start:.3f}秒（期待値: -1.0秒）")
    print(f"  終了: {time_ranges2[1].end - time_ranges1[1].end:.3f}秒")

# テストケース3: 複雑なテキスト
print("\n【テストケース3: 複雑なテキスト（削除あり）】")
test_text3 = """バイアスがかかってしまわないために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思います"""

diff3 = gateway.find_differences(full_text, test_text3, skip_normalization=True)
time_ranges3 = gateway.get_time_ranges(diff3, domain_result)

print(f"時間範囲数: {len(time_ranges3)}")
for i, tr in enumerate(time_ranges3):
    print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
    
# 差分の詳細を確認
print(f"\n差分詳細（unchanged部分のみ）:")
for i, (diff_type, text, positions) in enumerate(diff3.differences):
    if diff_type.value == "unchanged":
        print(f"  セグメント{i}: '{text[:20]}...' (位置: {positions})")

# テストケース4: 位置の正確性を確認
print("\n【テストケース4: 位置の正確性】")
# 特定の文字列を探す
search_text = "指針となる考え方"
pos_in_full = full_text.find(search_text)
print(f"'{search_text}'の位置: {pos_in_full}")

# 差分検出で同じ位置が見つかるか確認
test_text4 = search_text
diff4 = gateway.find_differences(full_text, test_text4, skip_normalization=True)

for diff_type, text, positions in diff4.differences:
    if diff_type.value == "unchanged" and positions:
        found_pos = positions[0][0]
        print(f"差分検出で見つかった位置: {found_pos}")
        print(f"位置の差: {found_pos - pos_in_full}")
        if found_pos == pos_in_full:
            print("✅ 位置が正確に一致しています")
        else:
            print("❌ 位置にずれがあります")