"""
シンプルなSequenceMatcherテスト
"""

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# テスト用データ
original_text = "私はプログラマーです。毎日コードを書いています。"
edited_text = "私はAIプログラマーです。"

print("="*60)
print("シンプルなSequenceMatcherテスト")
print("="*60)
print(f"原文: {original_text}")
print(f"編集: {edited_text}")
print()

# SequenceMatcherでテスト
gateway = SequenceMatcherTextProcessorGateway()

# 通常の差分検出テスト
print("【通常の差分検出】")
diff = gateway.find_differences(original_text, edited_text)

if diff.differences:
    for i, (diff_type, text, positions) in enumerate(diff.differences):
        print(f"\n差分{i+1}:")
        print(f"  タイプ: {diff_type.value}")
        print(f"  テキスト: \"{text}\"")
        if positions:
            print(f"  位置: {positions}")

# 正規化のテスト
print("\n\n【正規化のテスト】")
test_text = "バイアスが　かかって しまわない ために"
normalized = gateway.normalize_for_comparison(test_text)
print(f"元: \"{test_text}\"")
print(f"正規化後: \"{normalized}\"")

# 抜粋検索のテスト
print("\n\n【抜粋検索のシミュレーション】")
full_text = "これはテストです。バイアスがかかってしまわないために指針となる考え方などありますか。その他のテキスト。"
excerpt = "バイアスがかかってしまわないために"

print(f"全文: \"{full_text}\"")
print(f"抜粋: \"{excerpt}\"")

# 正規化して検索
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_excerpt = gateway.normalize_for_comparison(excerpt)

position = normalized_full.find(normalized_excerpt)
print(f"\n正規化後の全文: \"{normalized_full}\"")
print(f"正規化後の抜粋: \"{normalized_excerpt}\"")
print(f"見つかった位置: {position}")

if position != -1:
    print(f"マッチした部分: \"{normalized_full[position:position+len(normalized_excerpt)]}\"")