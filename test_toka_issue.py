"""
「とか」削除問題の詳細調査
"""

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from adapters.gateways.text_processing.search_based_lcs_gateway import SearchBasedLCSTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# 問題のテキスト
original_text = "ちゃんとした文章とかで表現していない"
edited_text = "ちゃんとした文章で表現していない"

print("="*80)
print("「とか」削除問題の調査")
print("="*80)
print(f"原文: \"{original_text}\"")
print(f"編集: \"{edited_text}\"")
print(f"削除された部分: \"とか\"")
print()

# SequenceMatcherでテスト
print("【SequenceMatcherの結果】")
sm_gateway = SequenceMatcherTextProcessorGateway()
sm_diff = sm_gateway.find_differences(original_text, edited_text)

print("\n差分検出結果:")
for i, (diff_type, text, positions) in enumerate(sm_diff.differences):
    print(f"\n{i+1}. タイプ: {diff_type.value}")
    print(f"   テキスト: \"{text}\"")
    if positions:
        print(f"   位置: {positions}")

# UNCHANGED部分だけを抽出
unchanged_parts = []
for diff_type, text, positions in sm_diff.differences:
    if diff_type == DifferenceType.UNCHANGED:
        unchanged_parts.append(text)

print(f"\n結合されたUNCHANGED部分: \"{''.join(unchanged_parts)}\"")
print(f"期待される結果: \"{edited_text}\"")
print(f"一致: {(''.join(unchanged_parts)) == edited_text}")

# より詳細な文字レベルの解析
print("\n" + "-"*40)
print("\n【文字レベルの詳細解析】")

# 正規化後のテキストも確認
normalized_original = sm_gateway.normalize_for_comparison(original_text)
normalized_edited = sm_gateway.normalize_for_comparison(edited_text)

print(f"\n正規化後:")
print(f"原文: \"{normalized_original}\"")
print(f"編集: \"{normalized_edited}\"")

# スペース除去後も確認
no_space_original = sm_gateway.remove_spaces(normalized_original)
no_space_edited = sm_gateway.remove_spaces(normalized_edited)

print(f"\nスペース除去後:")
print(f"原文: \"{no_space_original}\"")
print(f"編集: \"{no_space_edited}\"")

# LCSでも比較
print("\n" + "-"*40)
print("\n【LCS（SearchBasedLCS）の結果】")
lcs_gateway = SearchBasedLCSTextProcessorGateway()
lcs_diff = lcs_gateway.find_differences(original_text, edited_text)

lcs_unchanged_parts = []
for diff_type, text, positions in lcs_diff.differences:
    if diff_type == DifferenceType.UNCHANGED:
        lcs_unchanged_parts.append(text)

print(f"LCSのUNCHANGED部分: \"{''.join(lcs_unchanged_parts)}\"")

# より大きなコンテキストでテスト
print("\n" + "="*80)
print("\n【より大きなコンテキストでのテスト】")

large_original = "ほとんどの人が自分の考えをちゃんとした文章とかで表現していないのでバイアスに気づくどころか"
large_edited = "ほとんどの人が自分の考えをちゃんとした文章で表現していないのでバイアスに気づくどころか"

print(f"\n大きな原文: \"{large_original}\"")
print(f"大きな編集: \"{large_edited}\"")

sm_diff_large = sm_gateway.find_differences(large_original, large_edited)

print("\n差分検出結果（大きなコンテキスト）:")
for i, (diff_type, text, positions) in enumerate(sm_diff_large.differences):
    if diff_type == DifferenceType.UNCHANGED:
        print(f"\nUNCHANGED{i+1}: \"{text}\"")
        if positions:
            start, end = positions[0]
            print(f"  原文での該当部分: \"{large_original[start:end]}\"")
    elif diff_type == DifferenceType.DELETED:
        print(f"\nDELETED{i+1}: \"{text}\"")

# プレビュー生成をシミュレート
print("\n" + "="*80)
print("\n【プレビュー生成のシミュレーション】")

# UNCHANGEDな部分だけを使ってプレビューを作成
preview_parts = []
for diff_type, text, positions in sm_diff_large.differences:
    if diff_type == DifferenceType.UNCHANGED and positions:
        start, end = positions[0]
        # 原文から該当部分を抽出
        preview_parts.append(large_original[start:end])

preview_text = ''.join(preview_parts)
print(f"\nプレビューテキスト: \"{preview_text}\"")
print(f"期待されるテキスト: \"{large_edited}\"")
print(f"\n問題: プレビューに「とか」が含まれているか？ {'はい' if 'とか' in preview_text else 'いいえ'}")