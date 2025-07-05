"""
BuzzClipエンティティのテスト
"""

import pytest
from datetime import datetime

from domain.entities.buzz_clip import (
    BuzzClipCandidate,
    BuzzClipGenerationRequest,
    BuzzClipGenerationResult,
)


class TestBuzzClipCandidate:
    """BuzzClipCandidateのテスト"""
    
    def test_create_factory_method(self):
        """ファクトリメソッドでの作成テスト"""
        candidate = BuzzClipCandidate.create(
            title="驚きの瞬間",
            text="これは本当に驚きました",
            start_time=10.5,
            end_time=45.5,
            score=18,
            category="驚き系",
            reasoning="視聴者の興味を引く内容",
            keywords=["驚き", "衝撃"]
        )
        
        assert candidate.title == "驚きの瞬間"
        assert candidate.text == "これは本当に驚きました"
        assert candidate.start_time == 10.5
        assert candidate.end_time == 45.5
        assert candidate.duration == 35.0
        assert candidate.score == 18
        assert candidate.category == "驚き系"
        assert candidate.reasoning == "視聴者の興味を引く内容"
        assert candidate.keywords == ["驚き", "衝撃"]
        assert candidate.id is not None
        assert isinstance(candidate.created_at, datetime)
    
    def test_duration_calculation(self):
        """duration計算のテスト"""
        candidate = BuzzClipCandidate.create(
            title="テスト",
            text="テスト",
            start_time=100.0,
            end_time=130.0,
            score=10,
            category="その他",
            reasoning="テスト",
            keywords=[]
        )
        
        assert candidate.duration == 30.0
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        candidate = BuzzClipCandidate.create(
            title="テストタイトル",
            text="テストテキスト",
            start_time=0.0,
            end_time=40.0,
            score=15,
            category="お役立ち系",
            reasoning="理由",
            keywords=["キーワード1", "キーワード2"]
        )
        
        result = candidate.to_dict()
        
        assert result["title"] == "テストタイトル"
        assert result["text"] == "テストテキスト"
        assert result["start_time"] == 0.0
        assert result["end_time"] == 40.0
        assert result["duration"] == 40.0
        assert result["score"] == 15
        assert result["category"] == "お役立ち系"
        assert result["reasoning"] == "理由"
        assert result["keywords"] == ["キーワード1", "キーワード2"]
        assert "id" in result
        assert "created_at" in result
    
    def test_invalid_time_range(self):
        """無効な時間範囲のテスト"""
        # end_timeがstart_timeより小さい場合でも、エンティティ自体は作成される
        # （検証はユースケース層で行う）
        candidate = BuzzClipCandidate.create(
            title="テスト",
            text="テスト",
            start_time=50.0,
            end_time=30.0,
            score=10,
            category="その他",
            reasoning="テスト",
            keywords=[]
        )
        
        assert candidate.duration == -20.0  # 負の値になる


class TestBuzzClipGenerationRequest:
    """BuzzClipGenerationRequestのテスト"""
    
    def test_default_values(self):
        """デフォルト値のテスト"""
        segments = [{"text": "テスト", "start": 0, "end": 10}]
        request = BuzzClipGenerationRequest(
            transcription_text="テスト",
            transcription_segments=segments
        )
        
        assert request.num_candidates == 5
        assert request.min_duration == 30
        assert request.max_duration == 40
        assert request.categories is None
    
    def test_custom_values(self):
        """カスタム値のテスト"""
        segments = [{"text": "テスト", "start": 0, "end": 10}]
        request = BuzzClipGenerationRequest(
            transcription_text="テスト",
            transcription_segments=segments,
            num_candidates=3,
            min_duration=20,
            max_duration=50,
            categories=["感動系", "驚き系"]
        )
        
        assert request.num_candidates == 3
        assert request.min_duration == 20
        assert request.max_duration == 50
        assert request.categories == ["感動系", "驚き系"]


class TestBuzzClipGenerationResult:
    """BuzzClipGenerationResultのテスト"""
    
    def test_creation(self):
        """作成テスト"""
        candidates = [
            BuzzClipCandidate.create(
                title=f"候補{i}",
                text=f"テキスト{i}",
                start_time=i * 10.0,
                end_time=(i + 1) * 10.0,
                score=15 - i,
                category="テスト",
                reasoning=f"理由{i}",
                keywords=[f"キーワード{i}"]
            )
            for i in range(3)
        ]
        
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500
        }
        
        result = BuzzClipGenerationResult(
            candidates=candidates,
            total_processing_time=3.5,
            model_used="gpt-4-turbo-preview",
            usage=usage
        )
        
        assert len(result.candidates) == 3
        assert result.total_processing_time == 3.5
        assert result.model_used == "gpt-4-turbo-preview"
        assert result.usage["total_tokens"] == 1500