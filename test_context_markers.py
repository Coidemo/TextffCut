#!/usr/bin/env python3
"""
文脈マーカー {} 機能のテストスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


def test_context_marker_extraction():
    """文脈マーカーの抽出テスト"""
    gateway = SequenceMatcherTextProcessorGateway()
    
    # テストテキスト
    test_text = "クリエイターが何言っててもいいじゃんって僕は思ってます{ミクロなんですよね}自分深いだと思うからやめてください"
    
    # 文脈マーカーを抽出
    markers = gateway.extract_context_markers(test_text)
    
    print("=== 文脈マーカー抽出テスト ===")
    print(f"テキスト: {test_text}")
    print(f"検出されたマーカー数: {len(markers)}")
    
    for i, marker in enumerate(markers):
        print(f"マーカー{i+1}:")
        print(f"  内容: {marker['content']}")
        print(f"  全体: {marker['full_match']}")
        print(f"  位置: {marker['start']}-{marker['end']}")
    
    # 文脈マーカーを削除
    cleaned = gateway.remove_context_markers(test_text)
    print(f"\n文脈マーカー削除後: {cleaned}")
    
    # 位置を保持して削除
    preserved = gateway.remove_context_markers_preserve_positions(test_text)
    print(f"位置保持削除後: {preserved}")
    print(f"長さ比較: 元={len(test_text)}, 削除={len(cleaned)}, 保持={len(preserved)}")


def test_find_differences_with_context_markers():
    """文脈マーカーを含む差分検出テスト"""
    gateway = SequenceMatcherTextProcessorGateway()
    
    # テストデータ
    original = "アーティストの人が政治的な話をすると作品の雰囲気が壊れるからやめてという人が多いです例えばアニメの声優さんがアニメのキャラになりきって政治的な発言をしているとかだったらやめてほしいなっていうのはわかるんですけどクリエイターと作品は別物なのでクリエイターが何言っててもいいじゃんって僕は思ってますミクロなんですよね自分深いだと思うからやめてくださいみたいなこと言うと極論電車の中で男性が隣に座ると狭いからやめてください女性も香水の匂い深いだからやめてくださいとかそういった応酬があったらもう本当に社会が窮屈で仕方ないのでお互い様だよねっていう方がいいかなと思ってる派です"
    
    edited = "クリエイターが何言っててもいいじゃんって僕は思ってます{ミクロなんですよね}自分深いだと思うからやめてください"
    
    print("\n=== 文脈マーカーを含む差分検出テスト ===")
    print(f"元のテキスト長: {len(original)}")
    print(f"編集テキスト長: {len(edited)}")
    
    # 差分検出
    diff = gateway.find_differences(original, edited)
    
    if diff and hasattr(diff, 'differences'):
        from domain.entities.text_difference import DifferenceType
        
        unchanged_count = sum(1 for d in diff.differences if d[0] == DifferenceType.UNCHANGED)
        added_count = sum(1 for d in diff.differences if d[0] == DifferenceType.ADDED)
        deleted_count = sum(1 for d in diff.differences if d[0] == DifferenceType.DELETED)
        
        print(f"差分検出結果: UNCHANGED={unchanged_count}, ADDED={added_count}, DELETED={deleted_count}")
        
        for i, (diff_type, text, positions) in enumerate(diff.differences):
            print(f"\n差分{i+1}: {diff_type.value}")
            print(f"  テキスト: {text[:50]}..." if len(text) > 50 else f"  テキスト: {text}")
            if positions:
                print(f"  位置: {positions}")


def test_remove_context_markers_from_edited():
    """編集テキストから文脈マーカーを除去するテスト"""
    gateway = SequenceMatcherTextProcessorGateway()
    
    # 境界調整マーカーと文脈マーカーを含むテキスト
    test_text = "[<1.0]クリエイターが何言っててもいいじゃんって僕は思ってます{ミクロなんですよね}自分深いだと思うからやめてください[0.5>]"
    
    print("\n=== マーカー除去テスト ===")
    print(f"元のテキスト: {test_text}")
    
    # 境界調整マーカーのみ除去
    boundary_removed = gateway.remove_boundary_markers(test_text)
    print(f"境界調整マーカー除去後: {boundary_removed}")
    
    # 文脈マーカーも除去
    all_removed = gateway.remove_context_markers(boundary_removed)
    print(f"文脈マーカーも除去後: {all_removed}")


if __name__ == "__main__":
    test_context_marker_extraction()
    test_find_differences_with_context_markers()
    test_remove_context_markers_from_edited()