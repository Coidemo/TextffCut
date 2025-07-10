"""
LCSアルゴリズムの動作を1文字ずつ追跡して説明
"""

# 実際の問題部分を抜き出して確認
original = "指針となる考え方などありますか何か情報を得てみて"
edited = "指針となる考え方などありますか指針となる考えを"

print("=== 比較する文字列 ===")
print(f"元:   '{original}'")
print(f"検索: '{edited}'")
print()

# DPテーブルを作成して、どこで何が起きているか確認
m, n = len(original), len(edited)
dp = [[0] * (n + 1) for _ in range(m + 1)]

# DPテーブルを埋める
for i in range(1, m + 1):
    for j in range(1, n + 1):
        if original[i-1] == edited[j-1]:
            dp[i][j] = dp[i-1][j-1] + 1
        else:
            dp[i][j] = max(dp[i-1][j], dp[i][j-1])

# 「ありますか」の部分を詳しく見る
print("=== 「ありますか」周辺の一致状況 ===")
# 「ありますか」は元テキストの位置10-14
# 検索テキストでも位置10-14
for i in range(10, 16):  # 「ありますか」とその後
    if i < m:
        print(f"位置{i}: 元='{original[i]}' ", end="")
        # この文字が検索テキストのどこと一致するか確認
        for j in range(n):
            if original[i] == edited[j] and dp[i+1][j+1] == dp[i][j] + 1:
                print(f"↔ 検索[{j}]='{edited[j]}' ✓", end="")
                break
        print()

# バックトラックして実際のマッチを確認
print("\n=== バックトラックの過程 ===")
positions = []
i, j = m, n

print(f"開始位置: 元[{i-1}], 検索[{j-1}]")

step = 0
while i > 0 and j > 0 and step < 20:  # 最初の20ステップのみ
    step += 1
    if original[i-1] == edited[j-1]:
        print(f"Step {step}: 元[{i-1}]='{original[i-1]}' = 検索[{j-1}]='{edited[j-1]}' → マッチ！")
        positions.append((i-1, j-1))
        i -= 1
        j -= 1
    elif dp[i-1][j] > dp[i][j-1]:
        print(f"Step {step}: 上へ移動（元テキストの'{original[i-1]}'をスキップ）")
        i -= 1
    else:
        print(f"Step {step}: 左へ移動（検索テキストの'{edited[j-1]}'をスキップ）")
        j -= 1

# 結果を整理
positions.reverse()
print(f"\n=== マッチ結果 ===")
print(f"マッチした文字数: {len(positions)}")

# 連続性をチェック
groups = []
current_group = []
for idx, (orig_idx, edit_idx) in enumerate(positions):
    if idx == 0 or (orig_idx != positions[idx-1][0] + 1 or edit_idx != positions[idx-1][1] + 1):
        if current_group:
            groups.append(current_group)
        current_group = [(orig_idx, edit_idx)]
    else:
        current_group.append((orig_idx, edit_idx))
if current_group:
    groups.append(current_group)

print(f"\n連続したグループ数: {len(groups)}")
for i, group in enumerate(groups):
    start_orig, _ = group[0]
    end_orig, _ = group[-1]
    text = original[start_orig:end_orig+1]
    print(f"グループ{i+1}: '{text}' ({len(text)}文字)")

# なぜ断片化するのか説明
print("\n=== なぜ「ありますか」が断片化するのか ===")
print("元:   「...ありますか何か情報を得てみて」")
print("検索: 「...ありますか指針となる考えを」")
print("\n「か」の次が違うので、LCSは別の場所から文字を拾ってくる可能性があります")
print("例えば、元テキストの後ろの方にも「指」「針」などの文字があれば、")
print("そちらとマッチさせた方が全体として長い共通部分列になる場合があります")