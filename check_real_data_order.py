"""
実際のデータでLCSがどう動作するか確認
"""

import json
from pathlib import Path
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from adapters.gateways.text_processing.normalized_lcs_gateway import NormalizedLCSTextProcessorGateway
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS

# キャッシュファイルを読み込み
cache_path = Path("/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json")

with open(cache_path, encoding="utf-8") as f:
    data = json.load(f)

legacy_result = LegacyTranscriptionResult.from_dict(data)
full_text = "".join(seg.text for seg in legacy_result.segments)

# 編集テキスト（スペースなし）
edited_text = "バイアスがかかってしまわないために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものをレビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないのでバイアスに気づくどころか自分で何考えているかもわからないという状態になっているので地説でもいいので文章化したほうがいいんじゃないかなと思ってます"

# 正規化
gateway = NormalizedLCSTextProcessorGateway()
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_edit = gateway.normalize_for_comparison(edited_text)

print("=== 実際のデータでの調査 ===")
print(f"元テキスト長: {len(normalized_full)}")
print(f"編集テキスト長: {len(normalized_edit)}")

# 「バイアス」の位置
bias_pos_full = normalized_full.find("バイアス")
bias_pos_edit = normalized_edit.find("バイアス")
print(f"\n「バイアス」の位置:")
print(f"- 元: {bias_pos_full}")
print(f"- 編: {bias_pos_edit}")

# 元テキストの「バイアス」前後を確認
print(f"\n元テキストの「バイアス」周辺:")
print(f"'{normalized_full[bias_pos_full-50:bias_pos_full+50]}'")

# LCSアルゴリズムを実行
detector = TextDifferenceDetectorLCS()
positions = detector._compute_lcs_positions(normalized_full, normalized_edit)

print(f"\n=== LCSの結果 ===")
print(f"マッチ総数: {len(positions)}")

# 「バイアス」より前のマッチを探す
before_bias = []
for orig_idx, edit_idx in positions:
    if orig_idx < bias_pos_full:
        before_bias.append((orig_idx, edit_idx))

print(f"\n「バイアス」（位置{bias_pos_full}）より前のマッチ: {len(before_bias)}個")

if before_bias:
    # 最初の10個を表示
    print("\n最初の10個:")
    for i, (orig_idx, edit_idx) in enumerate(before_bias[:10]):
        orig_char = normalized_full[orig_idx]
        edit_char = normalized_edit[edit_idx]
        print(f"{i+1}. 元[{orig_idx}]='{orig_char}' ↔ 編[{edit_idx}]='{edit_char}'")
        
        # この編集位置が何の文字か確認
        if edit_idx < 30:
            context = normalized_edit[max(0, edit_idx-5):edit_idx+5]
            print(f"   編集テキストのコンテキスト: '{context}'")
    
    # 「い」を探す
    print("\n「い」のマッチを探す:")
    for orig_idx, edit_idx in before_bias:
        if normalized_full[orig_idx] == 'い':
            print(f"元[{orig_idx}]='{normalized_full[orig_idx]}' ↔ 編[{edit_idx}]='{normalized_edit[edit_idx]}'")
            print(f"  元のコンテキスト: '{normalized_full[max(0, orig_idx-10):orig_idx+10]}'")
            break

# 差分検出の完全な結果も確認
print(f"\n=== 差分検出の結果 ===")
diff_result = gateway.find_differences(full_text[:1000], edited_text)  # 最初の1000文字だけ

from domain.entities.text_difference import DifferenceType
for i, (dtype, text, _) in enumerate(diff_result.differences):
    if dtype == DifferenceType.UNCHANGED and len(text) == 1:
        print(f"差分{i+1}: '{text}' (1文字)")
        # 元テキストでの位置を確認
        pos = full_text[:1000].find(text)
        if pos != -1:
            print(f"  位置: {pos}")
            print(f"  コンテキスト: '{full_text[max(0, pos-5):pos+10]}'")