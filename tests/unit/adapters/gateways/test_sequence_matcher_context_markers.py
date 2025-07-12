#!/usr/bin/env python3
"""
文脈マーカー処理のユニットテスト
"""

import pytest
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType


class TestContextMarkerProcessing:
    """文脈マーカー処理のテストクラス"""
    
    def test_single_context_marker(self):
        """単一の文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あいうえお{かきく}けこさしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分を収集
        unchanged_parts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_parts.append(text)
        
        # 期待される結果
        assert len(unchanged_parts) == 2
        assert "あいうえお" in unchanged_parts
        assert "けこさしすせそ" in unchanged_parts
        assert "かきく" not in unchanged_parts  # 文脈マーカー内の内容は除外される
    
    def test_multiple_context_markers(self):
        """複数の文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "{あいうえお}かきく{けこ}さしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分を収集
        unchanged_parts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_parts.append(text)
        
        # 期待される結果
        assert len(unchanged_parts) == 2
        assert "かきく" in unchanged_parts
        assert "さしすせそ" in unchanged_parts
        assert "あいうえお" not in unchanged_parts
        assert "けこ" not in unchanged_parts
    
    def test_adjacent_context_markers(self):
        """隣接する文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あいうえお{かきく}{けこ}さしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分を収集
        unchanged_parts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_parts.append(text)
        
        # 期待される結果
        assert len(unchanged_parts) == 2
        assert "あいうえお" in unchanged_parts
        assert "さしすせそ" in unchanged_parts
        assert "かきく" not in unchanged_parts
        assert "けこ" not in unchanged_parts
    
    def test_context_marker_with_spaces(self):
        """スペースを含む文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あい うえお{か き く}けこ さしすせそ"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分を収集
        unchanged_parts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_parts.append(text)
        
        # 期待される結果
        assert len(unchanged_parts) == 2
        assert "あいうえお" in unchanged_parts
        assert "けこさしすせそ" in unchanged_parts
    
    def test_empty_context_marker(self):
        """空の文脈マーカーのテスト"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "あいうえおかきくけこさしすせそ"
        edited = "あいうえお{}かきくけこさしすせそ"
        
        # 空の文脈マーカーは正規表現でマッチしないので、通常の処理として扱われる
        result = gateway.find_differences(original, edited)
        
        # 差分があるはず（{}が追加されている）
        has_added = any(d[0] == DifferenceType.ADDED for d in result.differences)
        assert has_added
    
    def test_no_fragmentation(self):
        """断片化が発生しないことを確認"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "一番ミクロなんですよね自分の深いって自分が深いだと思うからやめてくださいみたいなこと言うと本当極論電車の中で男性が隣に座ると狭いからやめてくださいみたいな話"
        edited = "{一番ミクロなんですよね自分の深いって}自分が深いだと思うからやめてくださいみたいなこと言うと{本当}極論電車の中で男性が隣に座ると狭いからやめてください{みたいな話}"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分を収集
        unchanged_texts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_texts.append(text)
        
        # 結合して確認
        combined = ''.join(unchanged_texts)
        
        # 期待される部分が含まれていることを確認
        assert "自分が深いだと思うからやめてくださいみたいなこと言うと" in combined
        assert "極論電車の中で男性が隣に座ると狭いからやめてください" in combined
        
        # 断片化していないことを確認（短い断片が単独で存在しない）
        for text in unchanged_texts:
            # 2文字以下の断片が単独で存在しないことを確認
            if len(text) <= 2:
                # ただし、「と」などの助詞は許容される場合がある
                assert text in ["と", "の", "が", "を", "に", "で", "は", "も", "や", "か"]
    
    def test_context_marker_positions(self):
        """文脈マーカーの位置が正しく処理されることを確認"""
        gateway = SequenceMatcherTextProcessorGateway()
        
        original = "0123456789"
        edited = "012{345}6789"
        
        result = gateway.find_differences(original, edited)
        
        # UNCHANGED部分の位置を確認
        unchanged_positions = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED and positions:
                unchanged_positions.extend(positions)
        
        # 期待される位置範囲
        expected_positions = [(0, 3), (6, 10)]
        
        assert len(unchanged_positions) == 2
        assert (0, 3) in unchanged_positions  # "012"
        assert (6, 10) in unchanged_positions  # "6789"
        
        # 文脈マーカー部分（345）は含まれない
        assert not any(start <= 3 < end or start <= 4 < end or start <= 5 < end 
                      for start, end in unchanged_positions)