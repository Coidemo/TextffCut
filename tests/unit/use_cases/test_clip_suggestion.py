"""
AI切り抜き候補生成のユニットテスト

エンティティと品質チェックロジックの動作を検証する。
core依存のテスト（スコープ限定差分検出）はintegrationテストで行う。
"""

import pytest

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    ClipSuggestionRequest,
    ClipSuggestionResult,
    ValidationResult,
)
from use_cases.ai.generate_clip_suggestions import _is_subsequence


class TestClipSuggestionEntity:
    """ClipSuggestionエンティティのテスト"""

    def test_create(self):
        s = ClipSuggestion.create(
            title="テスト",
            segment_start_index=0,
            segment_end_index=5,
            edited_text="テストテキスト",
            score=15,
            category="仕事術",
            reasoning="理由",
            keywords=["kw1"],
        )
        assert s.title == "テスト"
        assert s.segment_start_index == 0
        assert s.segment_end_index == 5
        assert s.id is not None

    def test_to_dict_and_from_dict(self):
        s = ClipSuggestion.create(
            title="タイトル",
            segment_start_index=1,
            segment_end_index=3,
            edited_text="編集済み",
            score=10,
            category="ライフハック",
            reasoning="いい内容",
            keywords=["a", "b"],
        )
        s.time_ranges = [(1.0, 5.0), (7.0, 10.0)]
        s.validation_result = ValidationResult(is_valid=True, total_duration=7.0, issues=[])

        d = s.to_dict()
        restored = ClipSuggestion.from_dict(d)
        assert restored.title == "タイトル"
        assert restored.time_ranges == [(1.0, 5.0), (7.0, 10.0)]
        assert restored.validation_result.is_valid is True

    def test_to_dict_without_optional_fields(self):
        s = ClipSuggestion.create(
            title="最小",
            segment_start_index=0,
            segment_end_index=0,
            edited_text="テスト",
            score=5,
            category="",
            reasoning="",
        )
        d = s.to_dict()
        assert "time_ranges" not in d
        assert "validation" not in d


class TestIsSubsequence:
    """_is_subsequence関数のテスト"""

    def test_exact_match(self):
        assert _is_subsequence("abc", "abc") is True

    def test_subsequence(self):
        assert _is_subsequence("ac", "abc") is True

    def test_not_subsequence(self):
        assert _is_subsequence("xyz", "abc") is False

    def test_empty_edited(self):
        assert _is_subsequence("", "abc") is False

    def test_japanese_subsequence(self):
        original = "今日はAIの活用法について話します"
        edited = "今日はAIの活用法について話します"
        assert _is_subsequence(edited, original) is True

    def test_japanese_with_deletions(self):
        original = "まずAIを使うと仕事が10倍速くなります"
        edited = "AIを使うと仕事が10倍速くなります"
        assert _is_subsequence(edited, original) is True

    def test_too_much_added_content(self):
        # 元テキストにない文字が半分以上
        assert _is_subsequence("完全に新しいテキスト", "abc") is False


class TestValidationResult:
    """ValidationResultのテスト"""

    def test_valid(self):
        v = ValidationResult(is_valid=True, total_duration=35.0, issues=[])
        assert v.is_valid is True
        assert v.total_duration == 35.0
        assert len(v.issues) == 0

    def test_invalid_with_issues(self):
        v = ValidationResult(
            is_valid=False,
            total_duration=65.0,
            issues=["合計65.0秒（最大60秒超過）"],
        )
        assert v.is_valid is False
        assert len(v.issues) == 1


class TestClipSuggestionRequest:
    """ClipSuggestionRequestのテスト"""

    def test_defaults(self):
        r = ClipSuggestionRequest(
            transcription_text="テスト",
            transcription_segments=[],
        )
        assert r.num_candidates == 5
        assert r.min_duration == 30
        assert r.max_duration == 60
        assert r.prompt_path is None

    def test_custom_values(self):
        r = ClipSuggestionRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "a", "start": 0, "end": 1}],
            num_candidates=10,
            min_duration=15,
            max_duration=45,
            prompt_path="/custom/prompt.md",
        )
        assert r.num_candidates == 10
        assert r.min_duration == 15
