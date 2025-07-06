#!/usr/bin/env python3
"""追加文字削除機能のテスト"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from domain.entities.text_difference import DifferenceType


def test_delete_added_chars():
    """追加文字削除機能のテスト"""
    print("=== 追加文字削除機能のテスト ===\n")
    
    # テスト用の差分データ
    from domain.entities.text_difference import TextDifference
    
    # 差分を作成（2つの句読点が追加されている）
    differences = [
        (DifferenceType.UNCHANGED, "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね", None),
        (DifferenceType.ADDED, "。", None),
        (DifferenceType.UNCHANGED, "その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています", None),
        (DifferenceType.ADDED, "。", None)
    ]
    
    diff = TextDifference(
        id="test",
        original_text="元のテキスト",
        edited_text="編集されたテキスト",
        differences=differences
    )
    
    # 削除機能のシミュレーション（show_red_highlight_modalのロジック）
    print("1. 差分情報の確認")
    print(f"   UNCHANGED: {diff.unchanged_count}個")
    print(f"   ADDED: {diff.added_count}個")
    print(f"   追加された文字: {diff.added_chars}")
    
    # 共通部分（UNCHANGED）のみを結合
    cleaned_text = "".join(
        text for diff_type, text, _ in diff.differences 
        if diff_type == DifferenceType.UNCHANGED
    )
    
    print("\n2. 追加文字を削除")
    print(f"   削除前: お金持ち...ね。その代わり...す。")
    print(f"   削除後: {cleaned_text[:20]}...{cleaned_text[-20:]}")
    print(f"   削除後の長さ: {len(cleaned_text)}文字")
    
    # 検証
    print("\n3. 検証")
    assert "。" not in cleaned_text, "句読点が残っています"
    assert len(cleaned_text) == 119, f"期待される長さは119文字ですが、{len(cleaned_text)}文字です"
    
    print("   ✅ 句読点が正しく削除されました")
    print("   ✅ テキストの長さが正しいです（119文字）")
    
    # SimpleTextProcessorGatewayでの再処理テスト
    print("\n4. 削除後の再処理テスト")
    from adapters.gateways.text_processing.simple_text_processor_gateway import SimpleTextProcessorGateway
    
    gateway = SimpleTextProcessorGateway()
    
    # 元のテキスト（句読点なし）
    original = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますねその代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています"
    
    # 削除後のテキストで差分検出
    new_diff = gateway.find_differences(original, cleaned_text)
    
    print(f"   新しい差分: UNCHANGED={new_diff.unchanged_count}, ADDED={new_diff.added_count}")
    print(f"   変更があるか: {new_diff.has_changes}")
    
    assert not new_diff.has_changes, "削除後も差分が検出されています"
    print("   ✅ 削除後は差分なしと判定されました")
    
    print("\n✅ すべてのテストが成功しました")


if __name__ == "__main__":
    test_delete_added_chars()