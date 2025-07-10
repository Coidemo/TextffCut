"""
実際のテキストでSequenceMatcherとLCSを比較
"""

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from adapters.gateways.text_processing.search_based_lcs_gateway import SearchBasedLCSTextProcessorGateway
from domain.entities.text_difference import DifferenceType

# 原文（ユーザー提供）
original_text = """多角的に情報を得ていく際に自分では気づかない間にバイアスがかかってしまわないために一定の指針となる考え方などありますか何か情報を得てみて考えたことがあったらその考えをチャットgptとかに行ってここに存在するバイアスとか足りてない視点とかありますかというのを聞いてますねこれ僕毎日ブログ書いてるからあると思うんですけど毎日ブログ書いて自分の考えがまとまっているとそれを聞けるんですよ聞いた上であなたここバイアスかかってますよとかこれ結構結論ありきですよとかこの視点足りてないですよという指摘してもらえるので指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものをレビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章とかで表現していないのでバイアスに気づくどころか自分で何考えているかもわからないという状態になっているというのがあるので地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# 編集テキスト（ユーザー提供）
edited_text = """バイアスがかかってしまわないために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

print("="*80)
print("実際のテキストでの比較テスト")
print("="*80)
print(f"原文の長さ: {len(original_text)}文字")
print(f"編集テキストの長さ: {len(edited_text)}文字")
print(f"比率: {len(edited_text)/len(original_text)*100:.1f}%")
print()

# SequenceMatcherでテスト
print("【SequenceMatcherの結果】")
sm_gateway = SequenceMatcherTextProcessorGateway()
sm_diff = sm_gateway.find_differences(original_text, edited_text)

if sm_diff.differences:
    total_matched = 0
    match_count = 0
    deleted_count = 0
    added_count = 0
    
    print("\n検出された差分:")
    for i, (diff_type, text, positions) in enumerate(sm_diff.differences):
        if diff_type == DifferenceType.UNCHANGED:
            match_count += 1
            matched_len = len(text)
            total_matched += matched_len
            print(f"\n  [UNCHANGED {match_count}] 長さ{matched_len}文字")
            if positions and positions[0]:
                print(f"    位置: {positions[0]}")
            print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
        elif diff_type == DifferenceType.DELETED:
            deleted_count += 1
            print(f"\n  [DELETED {deleted_count}] 長さ{len(text)}文字")
            if positions and positions[0]:
                print(f"    位置: {positions[0]}")
            print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
        elif diff_type == DifferenceType.ADDED:
            added_count += 1
            print(f"\n  [ADDED {added_count}] 長さ{len(text)}文字")
            print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
    
    normalized_edited = sm_gateway.normalize_for_comparison(edited_text)
    coverage = (total_matched / len(normalized_edited)) * 100 if normalized_edited else 0
    print(f"\n統計:")
    print(f"  合計マッチブロック数: {match_count}個")
    print(f"  合計マッチ文字数: {total_matched}文字")
    print(f"  削除ブロック数: {deleted_count}個")
    print(f"  追加ブロック数: {added_count}個")
    print(f"  カバー率: {coverage:.1f}%")

print("\n" + "-"*40 + "\n")

# LCS（SearchBasedLCS）でテスト
print("【LCS（SearchBasedLCS）の結果】")
lcs_gateway = SearchBasedLCSTextProcessorGateway()
lcs_diff = lcs_gateway.find_differences(original_text, edited_text)

if lcs_diff.differences:
    total_matched = 0
    match_count = 0
    deleted_count = 0
    added_count = 0
    
    print("\n検出された差分:")
    for i, (diff_type, text, positions) in enumerate(lcs_diff.differences):
        if diff_type == DifferenceType.UNCHANGED:
            match_count += 1
            matched_len = len(text)
            total_matched += matched_len
            print(f"\n  [UNCHANGED {match_count}] 長さ{matched_len}文字")
            if positions and positions[0]:
                print(f"    位置: {positions[0]}")
            print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
    
    normalized_edited = lcs_gateway.normalize_for_comparison(edited_text)
    coverage = (total_matched / len(normalized_edited)) * 100 if normalized_edited else 0
    print(f"\n統計:")
    print(f"  合計マッチブロック数: {match_count}個")
    print(f"  合計マッチ文字数: {total_matched}文字")
    print(f"  カバー率: {coverage:.1f}%")

print("\n" + "="*80)

# 詳細な分析
print("\n【詳細分析】")
print("\n編集テキストで削除された部分:")
# 原文の最初の部分で編集テキストに含まれない部分を表示
start_of_edited = edited_text[:30]
pos_in_original = original_text.find(start_of_edited[:10])
if pos_in_original > 0:
    print(f"  削除された前半部分: \"{original_text[:pos_in_original]}\"")
    
# 原文と編集テキストの差異を確認
print("\n原文での「バイアスがかかってしまわない」周辺:")
bias_pos = original_text.find("バイアスがかかってしまわない")
if bias_pos != -1:
    print(f"  \"{original_text[bias_pos-20:bias_pos+50]}...\"")
    
print("\n編集テキストでの「バイアスがかかってしまわない」周辺:")
print(f"  \"{edited_text[:50]}...\"")