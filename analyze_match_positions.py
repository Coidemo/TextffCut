"""
マッチ位置の詳細分析
"""

import json
from pathlib import Path
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from adapters.gateways.text_processing.search_based_lcs_gateway import SearchBasedLCSTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# キャッシュファイルを読み込み
cache_path = Path("/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json")

with open(cache_path, encoding="utf-8") as f:
    data = json.load(f)

legacy_result = LegacyTranscriptionResult.from_dict(data)
full_text = "".join(seg.text for seg in legacy_result.segments)

# 編集テキスト
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# ハイブリッド検索ゲートウェイ
gateway = SearchBasedLCSTextProcessorGateway()
diff = gateway.find_differences(full_text, edited_text)

print("=== マッチ位置の詳細分析 ===")
print(f"元テキスト長: {len(full_text)}文字")
print(f"編集テキスト長: {len(edited_text)}文字")

# UNCHANGEDブロックの詳細を分析
unchanged_blocks = []
for diff_type, text, positions in diff.differences:
    if diff_type == DifferenceType.UNCHANGED:
        unchanged_blocks.append((text, positions))

print(f"\n=== UNCHANGEDブロックの詳細 ({len(unchanged_blocks)}個) ===")
for i, (text, positions) in enumerate(unchanged_blocks):
    print(f"\n{i+1}. テキスト: '{text}'")
    print(f"   長さ: {len(text)}文字")
    if positions:
        # 最初の位置を確認
        first_pos = positions[0][0] if positions[0] else None
        if first_pos is not None:
            print(f"   元テキストでの位置: {first_pos}")
            # 前後のコンテキストを表示
            context_start = max(0, first_pos - 20)
            context_end = min(len(full_text), first_pos + len(text) + 20)
            context = full_text[context_start:context_end]
            # マッチ部分を【】で囲む
            match_start = first_pos - context_start
            match_end = match_start + len(text)
            marked_context = context[:match_start] + "【" + context[match_start:match_end] + "】" + context[match_end:]
            print(f"   コンテキスト: ...{marked_context}...")

# 実際のマッチ箇所を確認
print("\n=== 実際のマッチ位置の確認 ===")
# 「バイアスがかかってしまわない」の位置を探す
search_text = "バイアスがかかってしまわない"
pos = full_text.find(search_text)
if pos >= 0:
    print(f"「{search_text}」の実際の位置: {pos}")
    context = full_text[max(0, pos-50):pos+100]
    print(f"実際のコンテキスト:\n{context}")

# 時間情報も確認（セグメントから）
print("\n=== 時間情報の確認 ===")
# 位置14688付近のセグメントを探す
target_pos = 14688
char_count = 0
for seg in legacy_result.segments:
    seg_len = len(seg.text)
    if char_count <= target_pos < char_count + seg_len:
        print(f"該当セグメント:")
        print(f"  開始時間: {seg.start:.2f}秒")
        print(f"  終了時間: {seg.end:.2f}秒")
        print(f"  テキスト: {seg.text}")
        # ワードレベルの情報も表示
        if hasattr(seg, 'words') and seg.words:
            print(f"  ワード数: {len(seg.words)}")
            # 「バイアス」を含むワードを探す
            for word in seg.words:
                if 'バイアス' in word.get('word', ''):
                    print(f"  「バイアス」のワード時間: {word.get('start', 0):.2f}秒 - {word.get('end', 0):.2f}秒")
        break
    char_count += seg_len

# クラスタの詳細も確認
print("\n=== クラスタ情報の詳細 ===")
# 特徴語を再抽出して確認
feature_words = gateway._extract_feature_words(edited_text)
print(f"特徴語トップ10:")
for i, fw in enumerate(feature_words[:10]):
    print(f"  {i+1}. {fw.word} (品詞: {fw.pos}, スコア: {fw.score})")