"""
文脈マーカーのエッジケーステスト
"""

import pytest
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.entities.character_timestamp import CharacterWithTimestamp as CharacterInfo


class TestContextMarkerEdgeCases:
    """文脈マーカーのエッジケースをテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.gateway = SequenceMatcherTextProcessorGateway()
        
    def create_transcription_result(self, text: str) -> TranscriptionResult:
        """テスト用のTranscriptionResultを作成"""
        segments = [
            TranscriptionSegment(
                id='1',
                start=0.0,
                end=10.0,
                text=text
            )
        ]
        return TranscriptionResult(
            id='test',
            video_id='test-video',
            segments=segments,
            language='ja',
            duration=10.0
        )
    
    def test_large_text_with_context_markers(self):
        """巨大なテキストでの文脈マーカー処理"""
        # 1MBのテキストを生成（実際の10MBは時間がかかるため）
        base_text = "これはテストです。" * 10000  # 約180KB
        large_text = base_text + "重要な部分" + base_text
        
        transcription = self.create_transcription_result(large_text)
        self.gateway.set_transcription_result(transcription)
        
        # 文脈マーカーを含む編集テキスト
        edited_text = base_text + "{ヒント}重要な部分" + base_text
        
        # 差分検出
        result = self.gateway.find_differences(
            original_text=transcription.text,
            edited_text=edited_text
        )
        
        # 結果を確認
        assert result is not None
        assert len(result.differences) > 0
        
        # 文脈マーカー内のテキストが追加として扱われることを確認
        from domain.entities.text_difference import DifferenceType
        added_count = sum(1 for d in result.differences if d[0] == DifferenceType.ADDED)
        assert added_count >= 1  # "ヒント"が追加として検出される
    
    def test_nested_context_markers(self):
        """ネストした文脈マーカーのテスト"""
        transcription = self.create_transcription_result("これは外側と内側のテストです")
        self.gateway.set_transcription_result(transcription)
        
        # ネストした文脈マーカー
        edited_text = "これは{外側{内側}と内側}のテストです"
        
        # 差分検出
        result = self.gateway.find_differences(
            original_text=transcription.text,
            edited_text=edited_text
        )
        
        # ネストは正しく処理されないが、エラーにならないことを確認
        assert result is not None
        assert len(result.differences) > 0
    
    def test_context_marker_with_special_characters(self):
        """特殊文字を含む文脈マーカーのテスト"""
        transcription = self.create_transcription_result("これは特殊文字のテストです")
        self.gateway.set_transcription_result(transcription)
        
        # 特殊文字を含む文脈マーカー
        special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', 
                        '[', ']', '+', '=', '|', '\\', '/', '?', '<', '>']
        
        for char in special_chars:
            edited_text = f"これは{{特殊{char}文字}}のテストです"
            
            # 差分検出（エラーにならないことを確認）
            try:
                result = self.gateway.find_differences(
                    original_text=transcription.text,
                    edited_text=edited_text
                )
                assert result is not None
            except Exception as e:
                pytest.fail(f"特殊文字 '{char}' でエラーが発生: {e}")
    
    def test_multiple_context_markers_performance(self):
        """多数の文脈マーカーでのパフォーマンステスト"""
        # 100個の文脈マーカーを含むテキスト
        base_parts = []
        for i in range(100):
            base_parts.append(f"セクション{i}")
        
        original_text = "".join(base_parts)
        
        # 各セクションに文脈マーカーを追加
        edited_parts = []
        for i in range(100):
            edited_parts.append(f"{{ヒント{i}}}セクション{i}")
        edited_text = "".join(edited_parts)
        
        transcription = self.create_transcription_result(original_text)
        self.gateway.set_transcription_result(transcription)
        
        import time
        start_time = time.time()
        
        # 差分検出
        result = self.gateway.find_differences(
            original_text=transcription.text,
            edited_text=edited_text
        )
        
        elapsed_time = time.time() - start_time
        
        # 結果を確認
        assert result is not None
        assert len(result.differences) > 0
        
        # パフォーマンスチェック（1秒以内に完了すること）
        assert elapsed_time < 1.0, f"処理時間が長すぎます: {elapsed_time:.3f}秒"
    
    def test_empty_context_marker_variations(self):
        """空の文脈マーカーのバリエーションテスト"""
        transcription = self.create_transcription_result("これはテストです")
        self.gateway.set_transcription_result(transcription)
        
        # 様々な空の文脈マーカー
        test_cases = [
            "これは{}テストです",  # 完全に空
            "これは{ }テストです",  # スペースのみ
            "これは{　}テストです",  # 全角スペースのみ
            "これは{\n}テストです",  # 改行のみ
            "これは{\t}テストです",  # タブのみ
        ]
        
        for edited_text in test_cases:
            # 差分検出（エラーにならないことを確認）
            result = self.gateway.find_differences(
                original_text=transcription.text,
                edited_text=edited_text
            )
            assert result is not None
            assert len(result.differences) > 0
    
    def test_context_marker_at_boundaries(self):
        """文章の境界での文脈マーカーテスト"""
        transcription = self.create_transcription_result("これはテストです")
        self.gateway.set_transcription_result(transcription)
        
        # 境界ケース
        test_cases = [
            "{開始}これはテストです",  # 文頭
            "これはテストです{終了}",  # 文末
            "{全体}",  # 全体を囲む
            "これは{テスト}です",  # 単語を囲む
        ]
        
        for edited_text in test_cases:
            # 差分検出
            result = self.gateway.find_differences(
                original_text=transcription.text,
                edited_text=edited_text
            )
            assert result is not None
            assert len(result.differences) > 0
    
    def test_unmatched_braces(self):
        """対応しない括弧のテスト"""
        transcription = self.create_transcription_result("これはテストです")
        self.gateway.set_transcription_result(transcription)
        
        # 対応しない括弧
        test_cases = [
            "これは{テストです",  # 閉じ括弧なし
            "これはテスト}です",  # 開き括弧なし
            "これは{{テストです",  # 二重開き括弧
            "これはテスト}}です",  # 二重閉じ括弧
            "これは}テスト{です",  # 逆順
        ]
        
        for edited_text in test_cases:
            # エラーにならないことを確認
            try:
                result = self.gateway.find_differences(
                    original_text=transcription.text,
                    edited_text=edited_text
                )
                assert result is not None
            except Exception as e:
                pytest.fail(f"対応しない括弧でエラーが発生: '{edited_text}' - {e}")