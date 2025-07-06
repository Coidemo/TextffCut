#!/usr/bin/env python3
"""SimpleTextProcessorGatewayの統合テスト"""

import json
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from adapters.gateways.text_processing.simple_text_processor_gateway import SimpleTextProcessorGateway
from domain.entities.transcription import TranscriptionResult


def test_simple_gateway():
    """SimpleTextProcessorGatewayのテスト"""
    print("=== SimpleTextProcessorGatewayの統合テスト ===\n")
    
    # テストデータの準備
    json_path = (
        project_root / "videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json"
    )
    
    with open(json_path) as f:
        data = json.load(f)
    
    # TranscriptionResultを作成
    transcription = TranscriptionResult.from_legacy_format(data)
    
    # 全文を取得（スペースなしで結合）
    full_text = transcription.text
    print(f"文字起こし結果の長さ: {len(full_text)}")
    print(f"最初の100文字: {full_text[:100]}...")
    
    # 編集テキスト（ユーザーが入力したもの）
    edited_text = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"
    print(f"\n編集テキストの長さ: {len(edited_text)}")
    
    # SimpleTextProcessorGatewayを使用
    gateway = SimpleTextProcessorGateway()
    
    # 差分検出
    print("\n=== 差分検出 ===")
    diff = gateway.find_differences(full_text, edited_text)
    print(f"差分オブジェクトの型: {type(diff)}")
    print(f"差分数: {len(diff.differences)}")
    print(f"追加された文字: {diff.added_chars}")
    print(f"UNCHANGED: {diff.unchanged_count}個, ADDED: {diff.added_count}個")
    
    # 時間範囲の計算
    print("\n=== 時間範囲の計算 ===")
    time_ranges = gateway.get_time_ranges(diff, transcription)
    print(f"時間範囲数: {len(time_ranges)}")
    for i, tr in enumerate(time_ranges[:3]):  # 最初の3つを表示
        print(f"  範囲{i+1}: {tr.start:.2f}秒 - {tr.end:.2f}秒 (長さ: {tr.duration:.2f}秒)")
    
    # テキスト検索
    print("\n=== テキスト検索 ===")
    search_results = gateway.search_text("消費税", transcription)
    print(f"「消費税」の検索結果: {len(search_results)}件")
    for i, (text, time_range) in enumerate(search_results[:3]):
        print(f"  結果{i+1}: '{text}' @ {time_range.start:.2f}秒")
    
    # 正規化
    print("\n=== テキスト正規化 ===")
    test_text = "ＡＢＣ１２３"
    normalized = gateway.normalize_text(test_text)
    print(f"元: '{test_text}' → 正規化後: '{normalized}'")
    
    # 境界マーカー処理
    print("\n=== 境界マーカー処理 ===")
    marked_text = "[<0.5]これはテスト[1.5>]です"
    markers = gateway.extract_existing_markers(marked_text)
    print(f"マーカー抽出: {markers}")
    cleaned = gateway.remove_boundary_markers(marked_text)
    print(f"マーカー削除後: '{cleaned}'")
    
    print("\n✅ すべてのテストが完了しました")


if __name__ == "__main__":
    test_simple_gateway()