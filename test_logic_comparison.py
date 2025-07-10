"""
差分検出ロジックの詳細比較
"""

from difflib import SequenceMatcher

# シンプルな例で動作を確認
original = "私はプログラマーです"
edited = "私はAIプログラマーです"

print("="*60)
print("差分検出ロジックの比較")
print("="*60)

# SequenceMatcherの動作
print("\n【SequenceMatcher（difflib）の動作】")
print(f"原文: {original}")
print(f"編集: {edited}")

matcher = SequenceMatcher(None, original, edited)
print("\nget_opcodes()の結果:")
for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    print(f"  {tag}: 原文[{i1}:{i2}]='{original[i1:i2]}', 編集[{j1}:{j2}]='{edited[j1:j2]}'")

# より複雑な例
print("\n" + "-"*40)
original2 = "バイアスがかかってしまわないために一定の指針となる"
edited2 = "バイアスがかかってしまわないために指針となる"

print(f"\n原文: {original2}")
print(f"編集: {edited2}")

matcher2 = SequenceMatcher(None, original2, edited2)
print("\nget_opcodes()の結果:")
for tag, i1, i2, j1, j2 in matcher2.get_opcodes():
    print(f"  {tag}: 原文[{i1}:{i2}]='{original2[i1:i2]}', 編集[{j1}:{j2}]='{edited2[j1:j2]}'")

# LCSアルゴリズムの簡易実装
print("\n" + "="*60)
print("\n【LCSアルゴリズムの動作】")

def simple_lcs(s1, s2):
    """簡易LCS実装（文字単位）"""
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # DPテーブルを構築
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    # バックトラック
    i, j = m, n
    lcs_chars = []
    while i > 0 and j > 0:
        if s1[i-1] == s2[j-1]:
            lcs_chars.append(s1[i-1])
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    
    return ''.join(reversed(lcs_chars))

print(f"原文: {original2}")
print(f"編集: {edited2}")
lcs_result = simple_lcs(original2, edited2)
print(f"\nLCS結果: '{lcs_result}'")
print(f"LCS長: {len(lcs_result)}文字 / 編集文字数: {len(edited2)}文字")

# 実際の問題ケース
print("\n" + "="*60)
print("\n【実際の問題ケース】")

# 長い文での部分一致
original3 = "多角的に情報を得ていく際に自分では気づかない間にバイアスがかかってしまわないために一定の指針となる考え方などありますか"
edited3 = "バイアスがかかってしまわないために指針となる考え方などありますか"

print(f"原文（{len(original3)}文字）: {original3[:50]}...")
print(f"編集（{len(edited3)}文字）: {edited3}")

# SequenceMatcherでの検索
print("\nSequenceMatcherでの検索:")
# 正確な部分文字列検索
if edited3 in original3:
    print("  → 完全一致: あり")
else:
    print("  → 完全一致: なし")
    # 「一定の」を除いた検索
    modified_original = original3.replace("一定の", "")
    if edited3 in modified_original:
        print("  → 「一定の」を除けば一致する")

# 最長共通部分列の比較
longest_match = matcher2.find_longest_match(0, len(original3), 0, len(edited3))
print(f"\n最長連続マッチ: {longest_match}")
if longest_match.size > 0:
    print(f"  内容: '{original3[longest_match.a:longest_match.a+longest_match.size]}'")