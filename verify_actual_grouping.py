"""
実際のグループ化を正確に確認
"""

import json
from pathlib import Path
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from adapters.gateways.text_processing.normalized_lcs_gateway import NormalizedLCSTextProcessorGateway

# キャッシュファイルを読み込み
cache_path = Path("/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json")

with open(cache_path, encoding="utf-8") as f:
    data = json.load(f)

legacy_result = LegacyTranscriptionResult.from_dict(data)
full_text = "".join(seg.text for seg in legacy_result.segments)

# 元の編集テキスト（スペース付き）
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# ゲートウェイで差分検出
gateway = NormalizedLCSTextProcessorGateway()
diff_result = gateway.find_differences(full_text, edited_text)

print("=== 実際の差分検出結果 ===")
print(f"差分数: {len(diff_result.differences)}")

# UNCHANGEDの部分だけを抽出して表示
from domain.entities.text_difference import DifferenceType

unchanged_parts = [(i, text) for i, (dtype, text, _) in enumerate(diff_result.differences) 
                   if dtype == DifferenceType.UNCHANGED]

print(f"\nUNCHANGED部分: {len(unchanged_parts)}個")
print("\n最初の10個のUNCHANGED部分:")
for idx, (diff_idx, text) in enumerate(unchanged_parts[:10]):
    print(f"{idx+1}. 差分{diff_idx+1}: '{text}' ({len(text)}文字)")

# 「ありますか」に関連する部分を探す
print("\n=== 「あり」を含むUNCHANGED部分 ===")
for diff_idx, text in unchanged_parts:
    if 'あり' in text:
        print(f"差分{diff_idx+1}: '{text}' ({len(text)}文字)")

# 1文字のUNCHANGED部分を確認
print("\n=== 1文字のUNCHANGED部分 ===")
single_char_parts = [(diff_idx, text) for diff_idx, text in unchanged_parts if len(text) == 1]
print(f"1文字の部分: {len(single_char_parts)}個")
for i, (diff_idx, text) in enumerate(single_char_parts[:10]):
    print(f"  差分{diff_idx+1}: '{text}'")