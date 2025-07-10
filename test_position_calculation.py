"""
位置計算の問題を詳細に調査
"""

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# 問題のテキスト
original_text = "ちゃんとした文章とかで表現していない"
edited_text = "ちゃんとした文章で表現していない"

print("="*80)
print("位置計算の詳細調査")
print("="*80)
print(f"原文: \"{original_text}\"")
print(f"編集: \"{edited_text}\"")
print()

# 文字位置を表示
print("原文の文字位置:")
for i, char in enumerate(original_text):
    print(f"  位置{i}: '{char}'")

print("\n編集テキストの文字位置:")
for i, char in enumerate(edited_text):
    print(f"  位置{i}: '{char}'")

# SequenceMatcherで差分検出
print("\n" + "-"*40)
gateway = SequenceMatcherTextProcessorGateway()
diff = gateway.find_differences(original_text, edited_text)

print("\n【差分検出結果の詳細】")
for i, (diff_type, text, positions) in enumerate(diff.differences):
    print(f"\n{i+1}. タイプ: {diff_type.value}")
    print(f"   テキスト: \"{text}\" (長さ: {len(text)})")
    if positions:
        print(f"   位置情報: {positions}")
        for j, (start, end) in enumerate(positions):
            print(f"   - 範囲{j+1}: {start}-{end}")
            print(f"     原文での内容: \"{original_text[start:end]}\"")
            
            # 位置が正しいかチェック
            if original_text[start:end] != text and diff_type == DifferenceType.UNCHANGED:
                print(f"     ⚠️ 位置計算エラー！")
                print(f"       期待: \"{text}\"")
                print(f"       実際: \"{original_text[start:end]}\"")

# 期待される結果
print("\n" + "="*80)
print("\n【期待される結果】")
print("1. UNCHANGED: \"ちゃんとした文章\" (位置: 0-8)")
print("2. DELETED: \"とか\" (位置: 8-10)")
print("3. UNCHANGED: \"で表現していない\" (位置: 10-18)")

# 実際の文字位置を詳細に確認
print("\n【詳細な文字位置の確認】")
print("原文での「章」の位置: ", original_text.find("章"))
print("原文での「章」の次の文字: ", original_text[original_text.find("章")+1])
print("原文での「と」（とかの「と」）の位置: ", original_text.find("と", 5))  # 5以降で検索
print("原文での「で」の位置: ", original_text.find("で"))

# 正規化の影響を確認
print("\n【正規化の影響】")
normalized_original = gateway.normalize_for_comparison(original_text)
normalized_edited = gateway.normalize_for_comparison(edited_text)
print(f"正規化後の原文: \"{normalized_original}\" (長さ: {len(normalized_original)})")
print(f"正規化後の編集: \"{normalized_edited}\" (長さ: {len(normalized_edited)})")

# スペース除去後も確認
no_space_original = gateway.remove_spaces(normalized_original)
no_space_edited = gateway.remove_spaces(normalized_edited)
print(f"\nスペース除去後の原文: \"{no_space_original}\" (長さ: {len(no_space_original)})")
print(f"スペース除去後の編集: \"{no_space_edited}\" (長さ: {len(no_space_edited)})")

# difflibのSequenceMatcherの動作を直接確認
print("\n" + "-"*40)
print("\n【difflibのSequenceMatcher動作確認】")
from difflib import SequenceMatcher

matcher = SequenceMatcher(None, no_space_original, no_space_edited)
print("\nget_opcodes()の結果:")
for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    print(f"  {tag}: 原文[{i1}:{i2}]='{no_space_original[i1:i2]}', 編集[{j1}:{j2}]='{no_space_edited[j1:j2]}'")