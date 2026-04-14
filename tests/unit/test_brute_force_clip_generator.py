"""
力任せ探索クリップ候補生成のテスト

ノイズペナルティのスコアリングをテストする。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from domain.entities.transcription import TranscriptionSegment
from use_cases.ai.brute_force_clip_generator import ClipCandidate, _calculate_score


def _make_segment(text: str, start: float = 0.0, end: float = 5.0) -> TranscriptionSegment:
    """テスト用セグメントを作成"""
    return TranscriptionSegment(id="test", text=text, start=start, end=end)


def _make_candidate(texts: list[str], total_duration: float = 45.0) -> ClipCandidate:
    """テスト用候補を作成"""
    segments = [_make_segment(t) for t in texts]
    return ClipCandidate(
        segments=segments,
        segment_indices=list(range(len(segments))),
        text="".join(texts),
        time_ranges=[(0.0, total_duration)],
        total_duration=total_duration,
    )


class TestNoiseKeywordPenalty:
    """冒頭/末尾ノイズキーワードペナルティのテスト"""

    def test_first_segment_noise_penalty(self):
        """冒頭にノイズキーワードがある候補はスコアが低くなる"""
        clean = _make_candidate(["人生を変える方法について", "具体的に解説します"])
        noisy = _make_candidate(["すいません マイクを直しました", "具体的に解説します"])

        score_clean = _calculate_score(clean, 30.0, 60.0)
        score_noisy = _calculate_score(noisy, 30.0, 60.0)

        assert (
            score_noisy < score_clean
        ), f"冒頭ノイズ候補({score_noisy})はクリーン候補({score_clean})より低スコアであるべき"

    def test_last_segment_noise_penalty(self):
        """末尾にノイズキーワードがある候補はスコアが低くなる"""
        # total_duration=25.0（範囲外）にしてスコア上限100への到達を回避
        clean = _make_candidate(["人生を変える方法について", "以上が結論です"], total_duration=25.0)
        noisy = _make_candidate(["人生を変える方法について", "すみません音声が途切れました"], total_duration=25.0)

        score_clean = _calculate_score(clean, 30.0, 60.0)
        score_noisy = _calculate_score(noisy, 30.0, 60.0)

        assert (
            score_noisy < score_clean
        ), f"末尾ノイズ候補({score_noisy})はクリーン候補({score_clean})より低スコアであるべき"

    def test_first_noise_penalty_larger_than_last(self):
        """冒頭ノイズのペナルティは末尾ノイズより大きい"""
        # GiNZA POS判定の影響を排除するため、両方の末尾を「です」で統一
        first_noisy = _make_candidate(["すいませんマイクの確認です", "普通の話", "まとめです"])
        last_noisy = _make_candidate(["普通の話", "まとめです", "すいませんマイクの確認です"])

        score_first = _calculate_score(first_noisy, 30.0, 60.0)
        score_last = _calculate_score(last_noisy, 30.0, 60.0)

        assert score_first < score_last, f"冒頭ノイズ({score_first})は末尾ノイズ({score_last})より低スコアであるべき"

    def test_no_penalty_without_noise_keywords(self):
        """ノイズキーワードがない場合はペナルティなし"""
        candidate = _make_candidate(["普通の話をしています", "結論はこうです"])
        score = _calculate_score(candidate, 30.0, 60.0)
        # ペナルティなしの基本スコアが得られる
        assert score > 0

    def test_microphone_keyword_detected(self):
        """「マイク」キーワードが冒頭で検出される"""
        clean = _make_candidate(["今日のテーマについて", "解説します"])
        noisy = _make_candidate(["マイクのテストです", "解説します"])

        score_clean = _calculate_score(clean, 30.0, 60.0)
        score_noisy = _calculate_score(noisy, 30.0, 60.0)

        assert score_noisy < score_clean

    def test_audio_keyword_detected(self):
        """「音声」キーワードが末尾で検出される"""
        clean = _make_candidate(["テーマについて", "まとめです"])
        noisy = _make_candidate(["テーマについて", "音声が乱れてすみません"])

        score_clean = _calculate_score(clean, 30.0, 60.0)
        score_noisy = _calculate_score(noisy, 30.0, 60.0)

        assert score_noisy < score_clean
