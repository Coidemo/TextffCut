#!/usr/bin/env python3
"""テキスト処理のリファクタリングテスト"""

import json
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter
from core.text_processor import TextProcessor


def test_current_implementation():
    """現在の実装をテスト"""
    print("=== 現在の実装のテスト ===\n")

    # テストデータの準備
    json_path = (
        project_root / "videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json"
    )

    with open(json_path) as f:
        data = json.load(f)

    # 全文を結合（現在の実装：スペースで結合）
    full_text = " ".join(seg["text"] for seg in data["segments"])
    print(f"文字起こし結果の長さ: {len(full_text)}")
    print(f"最初の100文字: {full_text[:100]}...")

    # 編集テキスト（ユーザーが入力したもの）
    edited_text = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"
    print(f"\n編集テキストの長さ: {len(edited_text)}")

    # 該当箇所を探す
    start_pos = full_text.find("お金持ちとか外国人とか")
    if start_pos != -1:
        actual_text = full_text[start_pos : start_pos + 200]
        print(f"\n実際のテキスト（位置 {start_pos} から）:")
        print(repr(actual_text))

        # 問題の確認
        print("\n=== 問題の確認 ===")
        print("1. セグメント間にスペースがある（' 平等に' ← スペースあり）")
        print("2. 編集テキストにはスペースがない（'も平等に' ← スペースなし）")
        print("3. 編集テキストには句読点が追加されている（'ね。'、'す。'）")

    # TextProcessorで差分検出
    print("\n=== TextProcessorでの差分検出 ===")
    processor = TextProcessor()

    # 通常の差分検出
    diff = processor.find_differences(full_text, edited_text)
    print(f"差分オブジェクトの型: {type(diff)}")

    # ゲートウェイ経由での差分検出
    print("\n=== ゲートウェイ経由での差分検出 ===")
    gateway = TextProcessorGatewayAdapter()
    domain_diff = gateway.find_differences(full_text, edited_text, skip_normalization=True)

    print(f"ドメイン差分オブジェクトの型: {type(domain_diff)}")
    if hasattr(domain_diff, "differences"):
        print(f"differences数: {len(domain_diff.differences) if domain_diff.differences else 0}")

        from domain.entities.text_difference import DifferenceType

        unchanged_count = 0
        added_count = 0

        for diff_type, text, _ in domain_diff.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_count += 1
                print(f"  UNCHANGED: 長さ={len(text)}, 内容='{text[:30]}...'")
            elif diff_type == DifferenceType.ADDED:
                added_count += 1
                print(f"  ADDED: 長さ={len(text)}, 内容='{text}'")

        print(f"\n集計: UNCHANGED={unchanged_count}個, ADDED={added_count}個")


def test_proper_implementation():
    """あるべき実装のテスト"""
    print("\n\n=== あるべき実装のテスト ===\n")

    # テストデータの準備
    json_path = (
        project_root / "videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json"
    )

    with open(json_path) as f:
        data = json.load(f)

    # あるべき実装：セグメントをスペースなしで結合
    full_text_no_space = "".join(seg["text"] for seg in data["segments"])
    print(f"文字起こし結果の長さ（スペースなし）: {len(full_text_no_space)}")

    # 編集テキスト
    edited_text = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"

    # 該当箇所を探す
    start_pos = full_text_no_space.find("お金持ちとか外国人とか")
    if start_pos != -1:
        actual_text = full_text_no_space[start_pos : start_pos + 200]
        print(f"\n実際のテキスト（位置 {start_pos} から）:")
        print(repr(actual_text))

        print("\n=== 改善点 ===")
        print("1. セグメント間にスペースがない")
        print("2. 編集テキストとの比較が容易")
        print("3. 句読点の追加だけが差分として検出される")

    # 簡易的な差分検出の実装例
    print("\n=== 簡易的な差分検出 ===")
    # 句読点を除去して比較
    edited_no_punct = edited_text.replace("。", "").replace("、", "")

    if edited_no_punct in full_text_no_space:
        pos = full_text_no_space.find(edited_no_punct)
        print(f"✅ 句読点なしで一致！位置: {pos}")

        # 句読点の位置を特定
        print("\n追加された句読点:")
        punct_count = 0
        for i, char in enumerate(edited_text):
            if char in "。、":
                print(f"  位置 {i}: '{char}'")
                punct_count += 1
        print(f"合計: {punct_count}個の句読点が追加")
    else:
        print("❌ 一致しません")


def main():
    """メイン処理"""
    print("テキスト処理のリファクタリングテスト\n")

    # 現在の実装をテスト
    test_current_implementation()

    # あるべき実装をテスト
    test_proper_implementation()

    print("\n\n=== リファクタリングの方針 ===")
    print("1. TranscriptionResult.textプロパティをスペースなしで結合するように修正")
    print("2. または、セグメント境界情報を保持したまま処理する新しい設計")
    print("3. レガシー形式を完全に排除してドメインエンティティで統一")
    print("4. 差分検出ロジックをシンプルで明確に")


if __name__ == "__main__":
    main()
