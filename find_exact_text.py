"""
正確なテキストを見つける
"""

import json

# 実際の文字起こし結果を読み込む
with open(
    "/Users/naoki/myProject/TextffCut/videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json",
) as f:
    data = json.load(f)

# segmentsからテキストを結合
full_text = "".join(seg["text"] for seg in data["segments"])

# 「お金持ちとか」から「思っています」までを探す
start_marker = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも"
end_marker = "ガンガンやった方がいいと思っています"

start_pos = full_text.find(start_marker)
if start_pos != -1:
    # end_markerを探す（start_posから）
    end_pos = full_text.find(end_marker, start_pos)
    if end_pos != -1:
        # end_markerの終わりまで含める
        end_pos += len(end_marker)

        actual_text = full_text[start_pos:end_pos]
        print("=== 実際の該当テキスト ===")
        print(f"開始位置: {start_pos}")
        print(f"終了位置: {end_pos}")
        print(f"長さ: {len(actual_text)}文字")
        print(f"内容: '{actual_text}'")

        # ユーザーのテキストと比較
        user_text = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"

        print("\n=== ユーザーのテキストとの差異 ===")
        print(f"ユーザーの長さ: {len(user_text)}文字")
        print("実際: ...いますね その代わり...")  # 句読点なし
        print("ユーザー: ...いますね。その代わり...")  # 句読点あり

        # 実際のテキストに「。」を追加してみる
        modified_actual = actual_text.replace("いますねその", "いますね。その").replace("ていますお", "ています。")
        print("\n=== 修正案 ===")
        print(f"修正後: '{modified_actual}'")
