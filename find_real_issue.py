"""
実際の問題を正確に再現
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

# 実際の処理と同じように全文を取得
try:
    full_text = legacy_result.get_full_text()
except:
    full_text = "".join(seg.text for seg in legacy_result.segments)

# ユーザーが入力した編集テキスト（スペース付き）
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

print("=== 実際の処理を再現 ===")
print(f"元テキスト（全文）: {len(full_text)}文字")
print(f"編集テキスト: {len(edited_text)}文字")

# 実際のゲートウェイで差分検出
gateway = NormalizedLCSTextProcessorGateway()
diff_result = gateway.find_differences(full_text, edited_text)

print(f"\n=== 差分検出結果 ===")
print(f"差分数: {len(diff_result.differences)}")

# UNCHANGEDで1文字のものを探す
from domain.entities.text_difference import DifferenceType
single_chars = []
for i, (dtype, text, _) in enumerate(diff_result.differences):
    if dtype == DifferenceType.UNCHANGED and len(text) == 1:
        single_chars.append((i, text))

print(f"\n1文字のUNCHANGED: {len(single_chars)}個")

# 「い」を探す
for diff_idx, char in single_chars:
    if char == 'い':
        print(f"\n差分{diff_idx+1}: '{char}'")
        # 元テキストでの位置を探す
        pos = full_text.find(char)
        print(f"元テキストでの最初の'{char}'の位置: {pos}")
        if pos != -1:
            print(f"コンテキスト: '{full_text[max(0, pos-10):pos+20]}'")

# なぜこの「い」が検出されるのか調査
print("\n=== なぜ位置1の「い」が検出されるのか ===")

# 正規化後のテキストで確認
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_edit = gateway.normalize_for_comparison(edited_text)

print(f"\n正規化後:")
print(f"元: {len(normalized_full)}文字")
print(f"編: {len(normalized_edit)}文字")

# 編集テキストに「い」が何個あるか
edit_i_count = normalized_edit.count('い')
print(f"\n編集テキストの「い」の数: {edit_i_count}個")

# 編集テキストの「い」の位置を全て表示
i_positions = []
for i, char in enumerate(normalized_edit):
    if char == 'い':
        i_positions.append(i)
        context = normalized_edit[max(0, i-10):i+20]
        print(f"位置{i}: '{context}'")

print(f"\n=== 仮説 ===")
print("編集テキストには複数の「い」があり、")
print("LCSアルゴリズムがそのうちの1つを元テキストの位置1の「い」とマッチさせている可能性")

# 実際のLCSマッチを確認
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
detector = TextDifferenceDetectorLCS()
positions = detector._compute_lcs_positions(normalized_full, normalized_edit)

# 位置1の「い」がマッチしているか確認
print(f"\n=== LCSマッチの詳細（位置1周辺） ===")
matches_near_1 = []
for orig_idx, edit_idx in positions:
    if 0 <= orig_idx <= 10:  # 位置0-10のマッチ
        matches_near_1.append((orig_idx, edit_idx))
        
if matches_near_1:
    print(f"位置0-10のマッチ: {len(matches_near_1)}個")
    for orig_idx, edit_idx in matches_near_1:
        print(f"元[{orig_idx}]='{normalized_full[orig_idx]}' ↔ 編[{edit_idx}]='{normalized_edit[edit_idx]}'")

# 編集テキストの位置156-174あたりの「い」がどうマッチしているか確認
print(f"\n=== 編集テキストの後半の「い」のマッチ状況 ===")
for orig_idx, edit_idx in positions:
    if 156 <= edit_idx <= 200 and normalized_edit[edit_idx] == 'い':
        print(f"元[{orig_idx}]='{normalized_full[orig_idx]}' ↔ 編[{edit_idx}]='{normalized_edit[edit_idx]}'")
        # 元テキストの位置を確認
        if orig_idx < 100:
            print(f"  → これは元テキストの最初の方（位置{orig_idx}）の文字です！")
            context = normalized_full[max(0, orig_idx-10):orig_idx+10]
            print(f"  元のコンテキスト: '{context}'")