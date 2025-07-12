#!/usr/bin/env python3
"""
文脈マーカー処理の統合テスト
実際の文字起こしデータを使用したエンドツーエンドテスト
"""

import pytest
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.entities.character_timestamp import CharacterWithTimestamp as CharacterInfo
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.entities.text_difference import DifferenceType


def create_mock_transcription_result():
    """テスト用の文字起こし結果を作成"""
    segments = [
        TranscriptionSegment(
            id="seg1",
            start=0.0,
            end=3.0,
            text="一番ミクロなんですよね",
            words=None,
            chars=[
                CharacterInfo(
                    char="一", start=0.0, end=0.2, 
                    segment_id="seg1", word_index=0, original_position=0, confidence=0.9
                ),
                CharacterInfo(
                    char="番", start=0.2, end=0.4,
                    segment_id="seg1", word_index=1, original_position=1, confidence=0.9
                ),
                CharacterInfo(
                    char="ミ", start=0.4, end=0.6,
                    segment_id="seg1", word_index=2, original_position=2, confidence=0.9
                ),
                CharacterInfo(
                    char="ク", start=0.6, end=0.8,
                    segment_id="seg1", word_index=3, original_position=3, confidence=0.9
                ),
                CharacterInfo(
                    char="ロ", start=0.8, end=1.0,
                    segment_id="seg1", word_index=4, original_position=4, confidence=0.9
                ),
                CharacterInfo(
                    char="な", start=1.0, end=1.2,
                    segment_id="seg1", word_index=5, original_position=5, confidence=0.9
                ),
                CharacterInfo(
                    char="ん", start=1.2, end=1.4,
                    segment_id="seg1", word_index=6, original_position=6, confidence=0.9
                ),
                CharacterInfo(
                    char="で", start=1.4, end=1.6,
                    segment_id="seg1", word_index=7, original_position=7, confidence=0.9
                ),
                CharacterInfo(
                    char="す", start=1.6, end=1.8,
                    segment_id="seg1", word_index=8, original_position=8, confidence=0.9
                ),
                CharacterInfo(
                    char="よ", start=1.8, end=2.0,
                    segment_id="seg1", word_index=9, original_position=9, confidence=0.9
                ),
                CharacterInfo(
                    char="ね", start=2.0, end=2.2,
                    segment_id="seg1", word_index=10, original_position=10, confidence=0.9
                ),
            ]
        ),
        TranscriptionSegment(
            id="seg2",
            start=3.0,
            end=6.0,
            text="自分の深いって",
            words=None,
            chars=[
                CharacterInfo(
                    char="自", start=3.0, end=3.3,
                    segment_id="seg2", word_index=0, original_position=0, confidence=0.9
                ),
                CharacterInfo(
                    char="分", start=3.3, end=3.6,
                    segment_id="seg2", word_index=1, original_position=1, confidence=0.9
                ),
                CharacterInfo(
                    char="の", start=3.6, end=3.9,
                    segment_id="seg2", word_index=2, original_position=2, confidence=0.9
                ),
                CharacterInfo(
                    char="深", start=3.9, end=4.2,
                    segment_id="seg2", word_index=3, original_position=3, confidence=0.9
                ),
                CharacterInfo(
                    char="い", start=4.2, end=4.5,
                    segment_id="seg2", word_index=4, original_position=4, confidence=0.9
                ),
                CharacterInfo(
                    char="っ", start=4.5, end=4.8,
                    segment_id="seg2", word_index=5, original_position=5, confidence=0.9
                ),
                CharacterInfo(
                    char="て", start=4.8, end=5.1,
                    segment_id="seg2", word_index=6, original_position=6, confidence=0.9
                ),
            ]
        ),
        TranscriptionSegment(
            id="seg3",
            start=6.0,
            end=12.0,
            text="自分が深いだと思うからやめてください",
            words=None,
            chars=[
                CharacterInfo(
                    char=c, start=6.0 + i*0.3, end=6.0 + (i+1)*0.3,
                    segment_id="seg3", word_index=i, original_position=i, confidence=0.9
                )
                for i, c in enumerate("自分が深いだと思うからやめてください")
            ]
        ),
        TranscriptionSegment(
            id="seg4",
            start=12.0,
            end=15.0,
            text="みたいなこと言うと",
            words=None,
            chars=[
                CharacterInfo(
                    char=c, start=12.0 + i*0.3, end=12.0 + (i+1)*0.3,
                    segment_id="seg4", word_index=i, original_position=i, confidence=0.9
                )
                for i, c in enumerate("みたいなこと言うと")
            ]
        ),
        TranscriptionSegment(
            id="seg5",
            start=15.0,
            end=16.0,
            text="本当",
            words=None,
            chars=[
                CharacterInfo(
                    char="本", start=15.0, end=15.5,
                    segment_id="seg5", word_index=0, original_position=0, confidence=0.9
                ),
                CharacterInfo(
                    char="当", start=15.5, end=16.0,
                    segment_id="seg5", word_index=1, original_position=1, confidence=0.9
                ),
            ]
        ),
        TranscriptionSegment(
            id="seg6",
            start=16.0,
            end=25.0,
            text="極論電車の中で男性が隣に座ると狭いからやめてください",
            words=None,
            chars=[
                CharacterInfo(
                    char=c, start=16.0 + i*0.3, end=16.0 + (i+1)*0.3,
                    segment_id="seg6", word_index=i, original_position=i, confidence=0.9
                )
                for i, c in enumerate("極論電車の中で男性が隣に座ると狭いからやめてください")
            ]
        ),
        TranscriptionSegment(
            id="seg7",
            start=25.0,
            end=28.0,
            text="みたいな話",
            words=None,
            chars=[
                CharacterInfo(
                    char=c, start=25.0 + i*0.6, end=25.0 + (i+1)*0.6,
                    segment_id="seg7", word_index=i, original_position=i, confidence=0.9
                )
                for i, c in enumerate("みたいな話")
            ]
        ),
    ]
    
    return TranscriptionResult(
        id="test_result_1",
        video_id="test_video_1",
        language="ja",
        segments=segments,
        duration=28.0
    )


class TestContextMarkerIntegration:
    """文脈マーカー統合テストクラス"""
    
    def test_real_world_scenario(self):
        """実際のシナリオでのテスト"""
        # 文字起こし結果を作成
        transcription_result = create_mock_transcription_result()
        
        # ゲートウェイを初期化
        gateway = SequenceMatcherTextProcessorGateway()
        gateway.set_transcription_result(transcription_result)
        
        # 編集テキスト（文脈マーカー付き）
        edited = "{一番ミクロなんですよね自分の深いって}自分が深いだと思うからやめてくださいみたいなこと言うと{本当}極論電車の中で男性が隣に座ると狭いからやめてください{みたいな話}"
        
        # 差分検出
        result = gateway.find_differences(transcription_result.text, edited)
        
        # 結果を検証
        unchanged_texts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_texts.append(text)
        
        # 期待される部分が含まれていることを確認
        combined = ''.join(unchanged_texts)
        assert "自分が深いだと思うからやめてくださいみたいなこと言うと" in combined
        assert "極論電車の中で男性が隣に座ると狭いからやめてください" in combined
        
        # 文脈マーカー内の内容が除外されていることを確認
        assert "一番ミクロなんですよね自分の深いって" not in combined
        assert "本当" not in combined
        assert "みたいな話" not in combined
    
    def test_time_range_calculation(self):
        """時間範囲計算のテスト"""
        # 文字起こし結果を作成
        transcription_result = create_mock_transcription_result()
        
        # ゲートウェイを初期化
        gateway = SequenceMatcherTextProcessorGateway()
        gateway.set_transcription_result(transcription_result)
        
        # 編集テキスト（文脈マーカー付き）
        edited = "{一番ミクロなんですよね自分の深いって}自分が深いだと思うからやめてください{みたいなこと言うと本当極論電車の中で男性が隣に座ると狭いからやめてくださいみたいな話}"
        
        # 差分検出
        result = gateway.find_differences(transcription_result.text, edited)
        
        # 時間範囲を計算
        time_ranges = gateway.get_time_ranges(result, transcription_result)
        
        # 時間範囲が正しく計算されていることを確認
        assert len(time_ranges) > 0
        
        # 最初の範囲は「自分が深いだと思うからやめてください」の部分
        # 6.0秒から始まるはず
        assert time_ranges[0].start >= 6.0
        assert time_ranges[0].end <= 12.0
    
    def test_with_boundary_adjustment_markers(self):
        """境界調整マーカーとの組み合わせテスト"""
        # 文字起こし結果を作成
        transcription_result = create_mock_transcription_result()
        
        # ゲートウェイを初期化
        gateway = SequenceMatcherTextProcessorGateway()
        gateway.set_transcription_result(transcription_result)
        
        # 編集テキスト（文脈マーカーと境界調整マーカー）
        edited = "[<0.5]{一番ミクロなんですよね自分の深いって}自分が深いだと思うからやめてください[0.5>]みたいなこと言うと{本当}極論電車の中で男性が隣に座ると狭いからやめてください{みたいな話}"
        
        # 差分検出
        result = gateway.find_differences(transcription_result.text, edited)
        
        # 結果を検証
        unchanged_texts = []
        for diff_type, text, positions in result.differences:
            if diff_type == DifferenceType.UNCHANGED:
                unchanged_texts.append(text)
        
        # 境界調整マーカーが除去されていることを確認
        combined = ''.join(unchanged_texts)
        assert "[<0.5]" not in combined
        assert "[0.5>]" not in combined
        
        # 期待される部分が含まれていることを確認
        assert "自分が深いだと思うからやめてください" in combined
        assert "みたいなこと言うと" in combined
        assert "極論電車の中で男性が隣に座ると狭いからやめてください" in combined
    
    def test_performance_with_long_text(self):
        """長いテキストでのパフォーマンステスト"""
        import time
        
        # 長いテキストを生成
        segments = []
        
        for i in range(100):
            segments.append(
                TranscriptionSegment(
                    id=f"seg{i}",
                    start=i * 1.0,
                    end=(i + 1) * 1.0,
                    text=f"これはテスト用の長いテキストです。",
                    words=None,
                    chars=[
                        CharacterInfo(
                            char=c, start=i + j*0.05, end=i + (j+1)*0.05,
                            segment_id=f"seg{i}", word_index=j, original_position=j, confidence=0.9
                        )
                        for j, c in enumerate("これはテスト用の長いテキストです。")
                    ]
                )
            )
        
        transcription_result = TranscriptionResult(
            id="test_result_long",
            video_id="test_video_long",
            language="ja",
            segments=segments,
            duration=100.0
        )
        
        # ゲートウェイを初期化
        gateway = SequenceMatcherTextProcessorGateway()
        gateway.set_transcription_result(transcription_result)
        
        # 編集テキスト（複数の文脈マーカー）
        base_text = transcription_result.text
        edited = base_text
        # 10箇所に文脈マーカーを追加
        for i in range(10):
            pos = i * 300
            edited = edited[:pos] + "{マーカー" + str(i) + "}" + edited[pos:]
        
        # 処理時間を測定
        start_time = time.time()
        result = gateway.find_differences(transcription_result.text, edited)
        end_time = time.time()
        
        # 処理時間が妥当な範囲内であることを確認（5秒以内）
        assert end_time - start_time < 5.0
        
        # 結果が正しく取得できていることを確認
        assert len(result.differences) > 0