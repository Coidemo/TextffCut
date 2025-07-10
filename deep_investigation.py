"""
「ありますか」が断片化する原因を深く調査
"""

import json
from pathlib import Path
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from adapters.gateways.text_processing.normalized_lcs_gateway import NormalizedLCSTextProcessorGateway

# キャッシュファイルを読み込み
cache_path = Path("/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json")

with open(cache_path, encoding="utf-8") as f:
    data = json.load(f)

legacy_result = LegacyTranscriptionResult.from_dict(data)
full_text = "".join(seg.text for seg in legacy_result.segments)

# 編集テキスト
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# 正規化
gateway = NormalizedLCSTextProcessorGateway()
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_edit = gateway.normalize_for_comparison(edited_text)

print("=== 正規化後のテキスト ===")
print(f"元: {len(normalized_full)}文字")
print(f"編: {len(normalized_edit)}文字")

# 「ありますか」周辺を詳しく見る
# まず元テキストで「ありますか」を探す
arimas_positions = []
search_text = "ありますか"
start = 0
while True:
    pos = normalized_full.find(search_text, start)
    if pos == -1:
        break
    arimas_positions.append(pos)
    start = pos + 1

print(f"\n=== 元テキストの「ありますか」の位置 ===")
print(f"見つかった数: {len(arimas_positions)}")
for i, pos in enumerate(arimas_positions[:5]):  # 最初の5個
    context = normalized_full[max(0, pos-10):pos+15]
    print(f"{i+1}. 位置{pos}: '...{context}...'")

# 編集テキストでも確認
edit_arimas_pos = normalized_edit.find("ありますか")
print(f"\n=== 編集テキストの「ありますか」 ===")
if edit_arimas_pos != -1:
    context = normalized_edit[max(0, edit_arimas_pos-10):edit_arimas_pos+15]
    print(f"位置{edit_arimas_pos}: '...{context}...'")

# LCSアルゴリズムを直接実行
print(f"\n=== LCSアルゴリズムの詳細実行 ===")
detector = TextDifferenceDetectorLCS()

# 問題の箇所だけ抜き出して確認
# 「ありますか」を含む部分
test_start = arimas_positions[0] - 20 if arimas_positions else 0
test_end = test_start + 100
test_original = normalized_full[test_start:test_end]
test_edited = "ありますか"

print(f"\nテスト範囲:")
print(f"元: '{test_original}'")
print(f"編: '{test_edited}'")

# LCSを実行
positions = detector._compute_lcs_positions(test_original, test_edited)
print(f"\nLCSマッチ: {len(positions)}個")

# マッチした文字を表示
for i, (orig_idx, edit_idx) in enumerate(positions):
    orig_char = test_original[orig_idx] if orig_idx < len(test_original) else '?'
    edit_char = test_edited[edit_idx] if edit_idx < len(test_edited) else '?'
    print(f"  {orig_char} (元[{orig_idx}]) ↔ {edit_char} (編[{edit_idx}])")

# フルテキストでLCSを実行して「ありますか」部分を確認
print(f"\n=== フルテキストでのLCS実行（一部） ===")
full_positions = detector._compute_lcs_positions(normalized_full, normalized_edit)

# 編集テキストの「ありますか」部分（位置30-34と仮定）に対応するマッチを探す
arimas_matches = []
for orig_idx, edit_idx in full_positions:
    if 30 <= edit_idx <= 34:  # 「ありますか」の範囲
        arimas_matches.append((orig_idx, edit_idx))

print(f"\n「ありますか」部分のマッチ:")
prev_orig = -2
prev_edit = -2
for orig_idx, edit_idx in arimas_matches:
    char = normalized_full[orig_idx] if orig_idx < len(normalized_full) else '?'
    # 連続性をチェック
    is_continuous = (orig_idx == prev_orig + 1 and edit_idx == prev_edit + 1)
    mark = "→" if is_continuous else "×"
    print(f"{mark} 元[{orig_idx}]='{char}' ↔ 編[{edit_idx}]='{normalized_edit[edit_idx]}'")
    prev_orig = orig_idx
    prev_edit = edit_idx

# 実際のグループ化ロジックも確認
print(f"\n=== グループ化の確認 ===")
from domain.use_cases.difference_grouper import DifferenceGrouper
grouper = DifferenceGrouper()

# 簡単なテストケース
test_matches = [
    (0, 0),  # あ
    (1, 1),  # り
    (10, 2), # ま（位置が飛んでいる！）
    (11, 3), # す
    (12, 4), # か
]

print("テストケース（位置が飛んでいる場合）:")
for orig, edit in test_matches:
    print(f"  元[{orig}] ↔ 編[{edit}]")

# 実際にグループ化がどう判定するか手動で確認
print("\n連続性判定:")
for i in range(1, len(test_matches)):
    prev_orig, prev_edit = test_matches[i-1]
    curr_orig, curr_edit = test_matches[i]
    is_continuous = (curr_orig == prev_orig + 1 and curr_edit == prev_edit + 1)
    print(f"  [{prev_orig},{prev_edit}] → [{curr_orig},{curr_edit}]: {is_continuous}")