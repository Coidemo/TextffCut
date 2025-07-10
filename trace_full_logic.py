"""
実際の差分検出ロジックの完全な追跡
"""

import json
from pathlib import Path
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from adapters.gateways.text_processing.normalized_lcs_gateway import NormalizedLCSTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# 1. キャッシュファイルを読み込み
print("=== 1. キャッシュファイルの読み込み ===")
cache_path = Path("/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json")
with open(cache_path, encoding="utf-8") as f:
    data = json.load(f)

legacy_result = LegacyTranscriptionResult.from_dict(data)
full_text = "".join(seg.text for seg in legacy_result.segments)
print(f"文字起こし全文: {len(full_text)}文字")
print(f"最初の100文字: '{full_text[:100]}'")
print(f"最後の100文字: '{full_text[-100:]}'")

# 2. ユーザーの編集テキスト（スペース付き）
print("\n=== 2. 編集テキスト ===")
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""
print(f"編集テキスト: {len(edited_text)}文字")
print(f"最初の50文字: '{edited_text[:50]}'")

# 3. NormalizedLCSTextProcessorGatewayで差分検出
print("\n=== 3. NormalizedLCSTextProcessorGatewayの処理 ===")
gateway = NormalizedLCSTextProcessorGateway()

# 3.1 正規化
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_edit = gateway.normalize_for_comparison(edited_text)
print(f"正規化後:")
print(f"  元: {len(full_text)} → {len(normalized_full)}文字")
print(f"  編: {len(edited_text)} → {len(normalized_edit)}文字")

# 3.2 差分検出実行
diff_result = gateway.find_differences(full_text, edited_text)

# 4. 差分結果の詳細
print(f"\n=== 4. 差分検出結果 ===")
print(f"差分総数: {len(diff_result.differences)}")
print(f"diff.original_text長: {len(diff_result.original_text)}")
print(f"diff.edited_text長: {len(diff_result.edited_text)}")

# 各差分の詳細（最初の20個）
print("\n差分の詳細（最初の20個）:")
for i, (diff_type, text, _) in enumerate(diff_result.differences[:20]):
    print(f"\n差分{i+1}:")
    print(f"  タイプ: {diff_type.value}")
    print(f"  テキスト: '{text}' ({len(text)}文字)")
    
    if diff_type == DifferenceType.UNCHANGED:
        # 元テキストでの位置を確認
        pos = full_text.find(text)
        print(f"  元テキストでの位置: {pos}")
        if pos >= 0 and len(text) <= 3:  # 短いテキストの場合はコンテキストも表示
            context = full_text[max(0, pos-10):pos+len(text)+10]
            print(f"  コンテキスト: '{context}'")

# 5. 1文字のUNCHANGEDに注目
print("\n=== 5. 1文字のUNCHANGED部分 ===")
single_chars = []
for i, (diff_type, text, _) in enumerate(diff_result.differences):
    if diff_type == DifferenceType.UNCHANGED and len(text) == 1:
        single_chars.append((i, text))

print(f"1文字のUNCHANGED: {len(single_chars)}個")
for diff_idx, char in single_chars:
    print(f"  差分{diff_idx+1}: '{char}'")

# 6. 「い」の詳細調査
print("\n=== 6. 「い」の詳細調査 ===")
i_diffs = [(idx, char) for idx, char in single_chars if char == 'い']
print(f"「い」のUNCHANGED: {len(i_diffs)}個")

for diff_idx, char in i_diffs:
    print(f"\n差分{diff_idx+1}: '{char}'")
    # full_textで「い」を探す（最初の5個）
    positions = []
    start = 0
    for _ in range(5):
        pos = full_text.find('い', start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    
    print(f"  元テキストの「い」の位置（最初の5個）: {positions}")
    if positions:
        print(f"  最初の「い」のコンテキスト: '{full_text[max(0, positions[0]-5):positions[0]+10]}'")

# 7. UIでのハイライト処理をシミュレート
print("\n=== 7. UIでのハイライト処理シミュレーション ===")
print("show_diff_viewerの動作:")
print("1. UNCHANGEDブロックを長い順にソート")
print("2. 各ブロックに対して original_text.find(text) を実行")
print("3. 最初に見つかった位置をハイライト")

# UNCHANGEDブロックを取得
unchanged_blocks = [(diff_type, text) for diff_type, text, _ in diff_result.differences 
                   if diff_type == DifferenceType.UNCHANGED]

# 長さでソート（長い順）
unchanged_blocks.sort(key=lambda x: len(x[1]), reverse=True)

print(f"\nUNCHANGEDブロック（上位5個）:")
for i, (_, text) in enumerate(unchanged_blocks[:5]):
    print(f"{i+1}. '{text[:30]}...' ({len(text)}文字)")

# 問題の「い」がどう処理されるか
print("\n問題の「い」の処理:")
for _, text in unchanged_blocks:
    if text == 'い':
        pos = full_text.find(text)
        print(f"  find('い') → 位置{pos}")
        print(f"  これが位置1なら、「はい」の「い」がハイライトされてしまう！")
        break