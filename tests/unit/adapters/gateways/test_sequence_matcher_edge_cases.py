#!/usr/bin/env python3
"""
文脈マーカー処理のエッジケーステスト
"""

import pytest
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType


class TestContextMarkerEdgeCases:
    """文脈マーカーのエッジケーステスト"""
    
    def test_nested_context_markers(self):
        """ネストした文脈マーカーのテスト（非対応）"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あいうえお{かき{く}けこ}さしすせそ"
        
        # ネストしたマーカーは正規表現でマッチしない（最も外側のマーカーのみ）
        result = gateway.find_differences(original, edited)
        
        # 外側のマーカーのみが検出される
        context_markers = gateway.extract_context_markers(edited)
        # 期待: {かき{く}けこ} は検出されない（正規表現が対応していない）
        assert len(context_markers) == 0 or context_markers[0]['content'] != 'かき{く}けこ'
    
    def test_unmatched_braces(self):
        """対応しない括弧のテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        
        # 開き括弧のみ
        edited1 = "あいうえお{かきくけこさしすせそ"
        result1 = gateway.find_differences(original, edited1)
        # 文脈マーカーとして認識されない
        markers1 = gateway.extract_context_markers(edited1)
        assert len(markers1) == 0
        
        # 閉じ括弧のみ
        edited2 = "あいうえおかきくけこ}さしすせそ"
        result2 = gateway.find_differences(original, edited2)
        markers2 = gateway.extract_context_markers(edited2)
        assert len(markers2) == 0
    
    def test_empty_context_marker(self):
        """空の文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あいうえお{}かきくけこさしすせそ"
        
        # 空のマーカーは正規表現でマッチしない
        markers = gateway.extract_context_markers(edited)
        assert len(markers) == 0
        
        # {}は通常のテキストとして扱われる
        result = gateway.find_differences(original, edited)
        has_added = any(d[0] == DifferenceType.ADDED for d in result.differences)
        assert has_added  # {}が追加として検出される
    
    def test_special_characters_in_marker(self):
        """特殊文字を含む文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        
        # 改行を含むマーカー
        edited1 = "あいうえお{かき\nくけこ}さしすせそ"
        result1 = gateway.find_differences(original, edited1)
        unchanged_texts1 = [text for dtype, text, _ in result1.differences if dtype == DifferenceType.UNCHANGED]
        combined1 = ''.join(unchanged_texts1)
        assert "あいうえお" in combined1
        assert "さしすせそ" in combined1
        
        # 記号を含むマーカー
        edited2 = "あいうえお{※注意※}かきくけこさしすせそ"
        result2 = gateway.find_differences(original, edited2)
        unchanged_texts2 = [text for dtype, text, _ in result2.differences if dtype == DifferenceType.UNCHANGED]
        combined2 = ''.join(unchanged_texts2)
        assert "あいうえお" in combined2
        assert "かきくけこさしすせそ" in combined2
    
    def test_consecutive_markers(self):
        """連続する文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "{あい}{うえ}{お}かきくけこさしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # かきくけこさしすせそ のみが残る
        unchanged_texts = [text for dtype, text, _ in result.differences if dtype == DifferenceType.UNCHANGED]
        assert len(unchanged_texts) == 1
        assert unchanged_texts[0] == "かきくけこさしすせそ"
    
    def test_marker_at_boundaries(self):
        """テキストの境界にある文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        
        # 先頭にマーカー
        edited1 = "{あいうえお}かきくけこさしすせそ"
        result1 = gateway.find_differences(original, edited1)
        unchanged_texts1 = [text for dtype, text, _ in result1.differences if dtype == DifferenceType.UNCHANGED]
        assert "かきくけこさしすせそ" in unchanged_texts1
        
        # 末尾にマーカー
        edited2 = "あいうえおかきくけこ{さしすせそ}"
        result2 = gateway.find_differences(original, edited2)
        unchanged_texts2 = [text for dtype, text, _ in result2.differences if dtype == DifferenceType.UNCHANGED]
        assert "あいうえおかきくけこ" in unchanged_texts2
        
        # 全体がマーカー
        edited3 = "{あいうえおかきくけこさしすせそ}"
        result3 = gateway.find_differences(original, edited3)
        unchanged_texts3 = [text for dtype, text, _ in result3.differences if dtype == DifferenceType.UNCHANGED]
        assert len(unchanged_texts3) == 0  # 全て除外される
    
    def test_very_long_marker_content(self):
        """非常に長い内容の文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        long_content = "あ" * 1000
        original = long_content + "終了"
        edited = "{" + long_content + "}終了"
        
        result = gateway.find_differences(original, edited)
        unchanged_texts = [text for dtype, text, _ in result.differences if dtype == DifferenceType.UNCHANGED]
        
        # "終了"のみが残る
        assert len(unchanged_texts) == 1
        assert unchanged_texts[0] == "終了"
    
    def test_marker_with_boundary_adjustment(self):
        """文脈マーカーと境界調整マーカーの組み合わせ"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "[<0.5]あいうえお{かきく}[0.5>]けこさしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # 境界調整マーカーは除去される
        # 文脈マーカー内の"かきく"も除外される
        unchanged_texts = [text for dtype, text, _ in result.differences if dtype == DifferenceType.UNCHANGED]
        combined = ''.join(unchanged_texts)
        
        assert "あいうえお" in combined
        assert "けこさしすせそ" in combined
        assert "かきく" not in combined
        
        # 境界調整マーカー自体は結果に含まれない
        all_texts = [text for _, text, _ in result.differences]
        combined_all = ''.join(all_texts)
        assert "[<0.5]" not in combined_all
        assert "[0.5>]" not in combined_all