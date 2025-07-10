"""
LCSアルゴリズムがなぜ「バイアス」より前の文字を見つけるのか調査
"""

# 問題を再現する最小限の例
original = "はいありますかこんにちはバイアスがかかってしまわないために指針となる考え方などありますか"
edited = "バイアスがかかってしまわないために指針となる考え方などありますか"

print("=== テキスト ===")
print(f"元: '{original}'")
print(f"編: '{edited}'")
print(f"\n元テキストの構造:")
print(f"- 位置0-6: 'はいありますか'")
print(f"- 位置13-: 'バイアス...'")
print(f"- 最後の方: '...ありますか'")

# LCSのDPテーブルを作成して可視化
def compute_lcs_with_path(text1, text2):
    m, n = len(text1), len(text2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # DPテーブルを埋める
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if text1[i-1] == text2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    # バックトラックの詳細を記録
    print(f"\n=== バックトラックの詳細 ===")
    print(f"開始: 右下[{m},{n}]から")
    
    positions = []
    i, j = m, n
    step = 0
    
    while i > 0 and j > 0:
        step += 1
        if step > 50:  # 最初の50ステップのみ
            print("...")
            break
            
        if text1[i-1] == text2[j-1]:
            positions.append((i-1, j-1))
            print(f"Step {step}: [{i-1},{j-1}] '{text1[i-1]}' マッチ！")
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            print(f"Step {step}: [{i},{j}] ↑上へ（元の'{text1[i-1]}'をスキップ）")
            i -= 1
        else:
            print(f"Step {step}: [{i},{j}] ←左へ（編集の'{text2[j-1]}'をスキップ）")
            j -= 1
    
    positions.reverse()
    return positions, dp

positions, dp_table = compute_lcs_with_path(original, edited)

print(f"\n=== LCSの結果 ===")
print(f"マッチ数: {len(positions)}")

# 「バイアス」の位置を確認
bias_start_orig = original.find("バイアス")
bias_start_edit = edited.find("バイアス")
print(f"\n「バイアス」の位置:")
print(f"- 元テキスト: {bias_start_orig}")
print(f"- 編集テキスト: {bias_start_edit}")

# マッチの中で「バイアス」より前のものを探す
print(f"\n=== 「バイアス」より前のマッチ ===")
before_bias_matches = [(orig_idx, edit_idx) for orig_idx, edit_idx in positions 
                       if orig_idx < bias_start_orig]

if before_bias_matches:
    print(f"見つかりました！{len(before_bias_matches)}個")
    for orig_idx, edit_idx in before_bias_matches[:10]:
        print(f"  元[{orig_idx}]='{original[orig_idx]}' ↔ 編[{edit_idx}]='{edited[edit_idx]}'")
        # この文字が編集テキストのどこの文字か
        if edit_idx < 17:  # 「バイアス...ために」の部分
            print(f"    → これは編集テキストの「バイアス」部分の文字です！")
        else:
            print(f"    → これは編集テキストの後半部分の文字です")

# なぜこうなるのか説明
print(f"\n=== なぜ「バイアス」より前の文字がマッチするのか ===")
print("LCSのバックトラックは右下（最後）から始まります。")
print("つまり、編集テキストの最後の「か」から順に遡っていきます。")
print("\n例えば編集テキストの「ありますか」（最後の方）の文字は、")
print("元テキストの最初の「はいありますか」の文字とマッチする可能性があります。")

# 実際の順序を確認
print(f"\n=== マッチの実際の順序（最初の20個） ===")
for i, (orig_idx, edit_idx) in enumerate(positions[:20]):
    print(f"{i+1}. 元[{orig_idx}]='{original[orig_idx]}' ↔ 編[{edit_idx}]='{edited[edit_idx]}'")