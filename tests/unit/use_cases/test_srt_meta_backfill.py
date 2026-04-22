"""srt_meta_backfill のテスト (title matching, speed persistence)."""

from __future__ import annotations

import json
from pathlib import Path

from use_cases.ai.srt_meta_backfill import _load_suggestion_cache


def _write_suggestions(cache_dir: Path, filename: str, suggestions: list[dict], speed: float | None = None) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {"suggestions": suggestions}
    if speed is not None:
        data["speed"] = speed
    (cache_dir / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestLoadSuggestionCache:
    def test_matching_title_returns_suggestion_and_speed(self, tmp_path: Path):
        base_dir = tmp_path
        _write_suggestions(
            base_dir / "clip_suggestions",
            "gpt-4.1.json",
            [
                {"title": "first title", "time_ranges": [[0, 10]]},
                {"title": "AIで情報収集格差が爆増中!", "time_ranges": [[10, 20]]},
            ],
            speed=1.2,
        )
        result = _load_suggestion_cache(base_dir, "02_AIで情報収集格差が爆増中!")
        assert result is not None
        suggestion, speed = result
        assert suggestion["time_ranges"] == [[10, 20]]
        assert speed == 1.2

    def test_mismatched_title_returns_none(self, tmp_path: Path):
        """docstring 通り: title 照合しない場合は None を返す (wrong clip の timing 使用回避)."""
        base_dir = tmp_path
        _write_suggestions(
            base_dir / "clip_suggestions",
            "gpt-4.1.json",
            [
                {"title": "完全に別のクリップ", "time_ranges": [[100, 200]]},
            ],
        )
        result = _load_suggestion_cache(base_dir, "01_期待するタイトル")
        assert result is None

    def test_missing_speed_defaults_to_1(self, tmp_path: Path):
        """古いキャッシュ (speed なし) は 1.0 にフォールバック."""
        base_dir = tmp_path
        _write_suggestions(
            base_dir / "clip_suggestions",
            "gpt-4.1.json",
            [{"title": "test", "time_ranges": [[0, 5]]}],
            speed=None,  # speed 欄なし
        )
        result = _load_suggestion_cache(base_dir, "01_test")
        assert result is not None
        _, speed = result
        assert speed == 1.0

    def test_prefers_newest_cache_on_multiple_files(self, tmp_path: Path):
        """複数 JSON がある場合、新しい mtime が優先される."""
        import time

        base_dir = tmp_path
        cache_dir = base_dir / "clip_suggestions"
        _write_suggestions(
            cache_dir,
            "old.json",
            [{"title": "test", "time_ranges": [[0, 5]]}],
            speed=1.0,
        )
        time.sleep(0.05)  # mtime 差を確保
        _write_suggestions(
            cache_dir,
            "new.json",
            [{"title": "test", "time_ranges": [[100, 200]]}],
            speed=1.5,
        )
        result = _load_suggestion_cache(base_dir, "01_test")
        assert result is not None
        suggestion, speed = result
        # new.json の方が選ばれる
        assert suggestion["time_ranges"] == [[100, 200]]
        assert speed == 1.5

    def test_no_cache_dir(self, tmp_path: Path):
        assert _load_suggestion_cache(tmp_path, "01_anything") is None

    def test_no_digit_prefix(self, tmp_path: Path):
        _write_suggestions(
            tmp_path / "clip_suggestions",
            "x.json",
            [{"title": "a", "time_ranges": [[0, 1]]}],
        )
        assert _load_suggestion_cache(tmp_path, "no_digit_prefix") is None
