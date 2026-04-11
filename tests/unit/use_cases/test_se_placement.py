"""
SE配置モジュール (use_cases/ai/se_placement.py) のユニットテスト

外部API (OpenAI) は mock で差し替え、純粋にロジックを検証する。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from use_cases.ai.se_placement import (
    SEPlacement,
    _format_se_files,
    _format_subtitles,
    plan_se_placements,
)
from use_cases.ai.subtitle_image_renderer import SubtitleEntry


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_entry(index: int, start: float, end: float, text: str) -> SubtitleEntry:
    return SubtitleEntry(index=index, start_time=start, end_time=end, text=text)


def _make_se_files(names: list[str], base: Path | None = None) -> list[Path]:
    """テスト用 SEファイルパスリストを生成する。"""
    if base is None:
        base = Path("/fake/se")
    return [base / name for name in names]


def _make_client(response_json: dict | str | None = None, raise_error: Exception | None = None):
    """OpenAI クライアントのモックを返す。"""
    client = MagicMock()
    if raise_error is not None:
        client.chat.completions.create.side_effect = raise_error
    else:
        content = json.dumps(response_json) if isinstance(response_json, dict) else (response_json or "")
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        client.chat.completions.create.return_value = resp
    return client


# ---------------------------------------------------------------------------
# SEPlacement データクラス
# ---------------------------------------------------------------------------


class TestSEPlacementDataclass:
    """SEPlacement データクラス自体の検証。"""

    def test_basic_creation(self):
        p = SEPlacement(se_file="/se/effect.mp3", timestamp=1.5, reason="盛り上がり")
        assert p.se_file == "/se/effect.mp3"
        assert p.timestamp == pytest.approx(1.5)
        assert p.reason == "盛り上がり"

    def test_default_reason_is_empty(self):
        p = SEPlacement(se_file="a.mp3", timestamp=0.0)
        assert p.reason == ""

    def test_zero_timestamp_allowed(self):
        p = SEPlacement(se_file="a.mp3", timestamp=0.0)
        assert p.timestamp == pytest.approx(0.0)

    def test_fields_are_mutable(self):
        p = SEPlacement(se_file="a.mp3", timestamp=1.0)
        p.timestamp = 2.0
        assert p.timestamp == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _format_subtitles
# ---------------------------------------------------------------------------


class TestFormatSubtitles:
    """_format_subtitles のフォーマット検証。"""

    def test_single_entry(self):
        entries = [_make_entry(1, 0.0, 3.5, "こんにちは")]
        result = _format_subtitles(entries)
        assert result == "#1 [0.0s - 3.5s] こんにちは"

    def test_multiple_entries_order_preserved(self):
        entries = [
            _make_entry(1, 0.0, 2.0, "最初"),
            _make_entry(2, 2.5, 5.0, "次"),
            _make_entry(3, 5.5, 8.0, "最後"),
        ]
        result = _format_subtitles(entries)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "#1 [0.0s - 2.0s] 最初"
        assert lines[1] == "#2 [2.5s - 5.0s] 次"
        assert lines[2] == "#3 [5.5s - 8.0s] 最後"

    def test_decimal_formatting_one_digit(self):
        """小数点以下1桁でフォーマットされる。"""
        entries = [_make_entry(10, 1.234, 9.876, "テキスト")]
        result = _format_subtitles(entries)
        assert "[1.2s - 9.9s]" in result

    def test_empty_entries_returns_empty_string(self):
        result = _format_subtitles([])
        assert result == ""

    def test_index_prefix(self):
        """# + index の形式で始まる。"""
        entries = [_make_entry(42, 0.0, 1.0, "あ")]
        result = _format_subtitles(entries)
        assert result.startswith("#42 ")


# ---------------------------------------------------------------------------
# _format_se_files
# ---------------------------------------------------------------------------


class TestFormatSeFiles:
    """_format_se_files のフォーマット検証。"""

    def test_single_file(self):
        files = _make_se_files(["キュピーン1.mp3"])
        result = _format_se_files(files)
        assert result == "- キュピーン1.mp3"

    def test_multiple_files(self):
        files = _make_se_files(["a.mp3", "b.wav", "c.mp3"])
        result = _format_se_files(files)
        lines = result.split("\n")
        assert lines == ["- a.mp3", "- b.wav", "- c.mp3"]

    def test_empty_list_returns_empty_string(self):
        result = _format_se_files([])
        assert result == ""

    def test_uses_filename_not_full_path(self):
        """フルパスではなくファイル名だけ出力される。"""
        files = [Path("/some/deep/directory/effect.mp3")]
        result = _format_se_files(files)
        assert result == "- effect.mp3"
        assert "/some/deep" not in result


# ---------------------------------------------------------------------------
# plan_se_placements — 正常系
# ---------------------------------------------------------------------------


class TestPlanSePlacementsNormal:
    """plan_se_placements の正常動作を検証する。"""

    def _run(
        self,
        placements_json: list[dict],
        entries: list[SubtitleEntry] | None = None,
        se_names: list[str] | None = None,
    ) -> list[SEPlacement]:
        if entries is None:
            entries = [_make_entry(1, 0.0, 3.0, "テスト")]
        if se_names is None:
            se_names = ["effect.mp3"]
        se_files = _make_se_files(se_names)
        client = _make_client({"placements": placements_json})
        return plan_se_placements(client, entries, se_files)

    def test_single_valid_placement(self):
        result = self._run(
            placements_json=[{"se_file": "effect.mp3", "timestamp": 1.5, "reason": "盛り上がり"}],
            se_names=["effect.mp3"],
        )
        assert len(result) == 1
        assert result[0].timestamp == pytest.approx(1.5)
        assert result[0].reason == "盛り上がり"

    def test_se_file_resolved_to_full_path(self):
        """se_file フィールドがフルパスに解決される。"""
        se_files = [Path("/fake/se/キュピーン1.mp3")]
        client = _make_client({"placements": [{"se_file": "キュピーン1.mp3", "timestamp": 2.0}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert len(result) == 1
        assert result[0].se_file == "/fake/se/キュピーン1.mp3"

    def test_multiple_placements_returned(self):
        result = self._run(
            placements_json=[
                {"se_file": "effect.mp3", "timestamp": 0.5},
                {"se_file": "effect.mp3", "timestamp": 3.0},
            ],
        )
        assert len(result) == 2

    def test_reason_defaults_to_empty_string_when_absent(self):
        result = self._run(
            placements_json=[{"se_file": "effect.mp3", "timestamp": 1.0}],
        )
        assert result[0].reason == ""

    def test_model_parameter_passed_to_api(self):
        """指定したモデル名が API に渡される。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": []})
        plan_se_placements(
            client,
            [_make_entry(1, 0.0, 3.0, "テスト")],
            se_files,
            model="gpt-4o",
        )
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"

    def test_response_format_json_object(self):
        """response_format=json_object が渡される。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": []})
        plan_se_placements(client, [_make_entry(1, 0.0, 1.0, "x")], se_files)
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs["response_format"] == {"type": "json_object"}

    def test_json_in_code_fence_parsed(self):
        """```json ... ``` 形式のレスポンスも正しく解析される。"""
        se_files = _make_se_files(["e.mp3"])
        raw = "```json\n" + json.dumps({"placements": [{"se_file": "e.mp3", "timestamp": 2.0}]}) + "\n```"
        client = _make_client(response_json=raw)
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert len(result) == 1
        assert result[0].timestamp == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# plan_se_placements — 空入力で空リストを返す
# ---------------------------------------------------------------------------


class TestPlanSePlacementsEmptyInputs:
    """空の入力が与えられた場合は [] を返す（API 呼び出しなし）。"""

    def test_empty_subtitle_entries_returns_empty(self):
        se_files = _make_se_files(["e.mp3"])
        client = MagicMock()
        result = plan_se_placements(client, [], se_files)
        assert result == []
        client.chat.completions.create.assert_not_called()

    def test_empty_se_files_returns_empty(self):
        entries = [_make_entry(1, 0.0, 3.0, "テスト")]
        client = MagicMock()
        result = plan_se_placements(client, entries, [])
        assert result == []
        client.chat.completions.create.assert_not_called()

    def test_both_empty_returns_empty(self):
        client = MagicMock()
        result = plan_se_placements(client, [], [])
        assert result == []
        client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# plan_se_placements — API エラー時は空リストを返す
# ---------------------------------------------------------------------------


class TestPlanSePlacementsApiError:
    """API 呼び出し失敗時は例外を伝播せず [] を返す。"""

    def _entries_and_files(self):
        return (
            [_make_entry(1, 0.0, 3.0, "テスト")],
            _make_se_files(["e.mp3"]),
        )

    def test_api_raises_exception_returns_empty(self):
        entries, se_files = self._entries_and_files()
        client = _make_client(raise_error=RuntimeError("Connection error"))
        result = plan_se_placements(client, entries, se_files)
        assert result == []

    def test_api_timeout_returns_empty(self):
        entries, se_files = self._entries_and_files()
        client = _make_client(raise_error=TimeoutError("timeout"))
        result = plan_se_placements(client, entries, se_files)
        assert result == []

    def test_api_value_error_returns_empty(self):
        entries, se_files = self._entries_and_files()
        client = _make_client(raise_error=ValueError("bad request"))
        result = plan_se_placements(client, entries, se_files)
        assert result == []


# ---------------------------------------------------------------------------
# 不明な SE ファイル名のスキップ
# ---------------------------------------------------------------------------


class TestUnknownSeFileName:
    """valid_se_names に含まれない se_file はスキップされる。"""

    def test_unknown_name_skipped(self):
        se_files = _make_se_files(["valid.mp3"])
        client = _make_client({"placements": [{"se_file": "unknown.mp3", "timestamp": 1.0, "reason": "?"}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "テスト")], se_files)
        assert result == []

    def test_empty_se_name_skipped(self):
        se_files = _make_se_files(["valid.mp3"])
        client = _make_client({"placements": [{"se_file": "", "timestamp": 1.0}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "テスト")], se_files)
        assert result == []

    def test_mixed_valid_and_unknown(self):
        """有効な SE と無効な SE が混在しているとき、有効分だけ返る。"""
        se_files = _make_se_files(["good.mp3", "also_good.mp3"])
        client = _make_client(
            {
                "placements": [
                    {"se_file": "good.mp3", "timestamp": 1.0},
                    {"se_file": "bad.mp3", "timestamp": 2.0},
                    {"se_file": "also_good.mp3", "timestamp": 3.0},
                ]
            }
        )
        result = plan_se_placements(client, [_make_entry(1, 0.0, 10.0, "テスト")], se_files)
        assert len(result) == 2
        names = {Path(p.se_file).name for p in result}
        assert names == {"good.mp3", "also_good.mp3"}


# ---------------------------------------------------------------------------
# 不正・負のタイムスタンプのスキップ
# ---------------------------------------------------------------------------


class TestInvalidTimestamp:
    """timestamp が負、変換不能な値のエントリはスキップされる。"""

    def test_negative_timestamp_skipped(self):
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": [{"se_file": "e.mp3", "timestamp": -0.1}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_string_timestamp_not_castable_skipped(self):
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": [{"se_file": "e.mp3", "timestamp": "abc"}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_none_timestamp_skipped(self):
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": [{"se_file": "e.mp3", "timestamp": None}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_zero_timestamp_allowed(self):
        """timestamp=0.0 は有効として受け入れられる。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": [{"se_file": "e.mp3", "timestamp": 0.0}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert len(result) == 1
        assert result[0].timestamp == pytest.approx(0.0)

    def test_string_numeric_timestamp_cast_and_accepted(self):
        """'1.5' のように数値文字列は float に変換されて受け入れられる。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": [{"se_file": "e.mp3", "timestamp": "1.5"}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert len(result) == 1
        assert result[0].timestamp == pytest.approx(1.5)

    def test_mixed_valid_and_invalid_timestamps(self):
        """有効なタイムスタンプのエントリだけ返される。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(
            {
                "placements": [
                    {"se_file": "e.mp3", "timestamp": -1.0},
                    {"se_file": "e.mp3", "timestamp": 2.0},
                    {"se_file": "e.mp3", "timestamp": "bad"},
                    {"se_file": "e.mp3", "timestamp": 5.0},
                ]
            }
        )
        result = plan_se_placements(client, [_make_entry(1, 0.0, 10.0, "あ")], se_files)
        assert len(result) == 2
        timestamps = [p.timestamp for p in result]
        assert pytest.approx(2.0) in timestamps
        assert pytest.approx(5.0) in timestamps


# ---------------------------------------------------------------------------
# タイムスタンプ順ソート
# ---------------------------------------------------------------------------


class TestTimestampSorting:
    """返される SEPlacement リストはタイムスタンプ昇順でソートされる。"""

    def test_placements_sorted_ascending(self):
        se_files = _make_se_files(["a.mp3", "b.mp3", "c.mp3"])
        client = _make_client(
            {
                "placements": [
                    {"se_file": "c.mp3", "timestamp": 9.0},
                    {"se_file": "a.mp3", "timestamp": 1.0},
                    {"se_file": "b.mp3", "timestamp": 5.0},
                ]
            }
        )
        result = plan_se_placements(client, [_make_entry(1, 0.0, 20.0, "テスト")], se_files)
        timestamps = [p.timestamp for p in result]
        assert timestamps == sorted(timestamps)

    def test_already_sorted_remains_sorted(self):
        se_files = _make_se_files(["a.mp3"])
        client = _make_client(
            {
                "placements": [
                    {"se_file": "a.mp3", "timestamp": 1.0},
                    {"se_file": "a.mp3", "timestamp": 3.0},
                    {"se_file": "a.mp3", "timestamp": 7.0},
                ]
            }
        )
        result = plan_se_placements(client, [_make_entry(1, 0.0, 20.0, "テスト")], se_files)
        assert [p.timestamp for p in result] == pytest.approx([1.0, 3.0, 7.0])

    def test_single_placement_is_trivially_sorted(self):
        se_files = _make_se_files(["a.mp3"])
        client = _make_client({"placements": [{"se_file": "a.mp3", "timestamp": 4.2}]})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 10.0, "テスト")], se_files)
        assert len(result) == 1
        assert result[0].timestamp == pytest.approx(4.2)


# ---------------------------------------------------------------------------
# isinstance(data, dict) チェック — 非 dict AIレスポンスの処理
# ---------------------------------------------------------------------------


class TestNonDictAiResponse:
    """AI が dict 以外のトップレベル JSON を返したとき [] が返る。"""

    def test_list_response_returns_empty(self):
        """トップレベルがリストのとき空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        # JSON トップレベルをリストにした文字列をそのまま渡す
        client = _make_client(response_json='[{"se_file": "e.mp3", "timestamp": 1.0}]')
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_string_response_returns_empty(self):
        """有効な JSON でも文字列型なら空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        # JSON ではなく生文字列を直接返す
        client = _make_client(response_json='"just a string"')
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_null_response_returns_empty(self):
        """JSON null が返ってきた場合も空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(response_json="null")
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_number_response_returns_empty(self):
        """数値がトップレベルのとき空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(response_json="42")
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_dict_without_placements_key_returns_empty(self):
        """dict だが placements キーが存在しない場合は空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"other_key": "value"})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_placements_is_non_list_returns_empty(self):
        """placements が dict のとき空リスト（リストを期待する）。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": {"se_file": "e.mp3", "timestamp": 1.0}})
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        # dict は list ではないので item の処理で se_name = "" になりスキップ
        assert result == []


# ---------------------------------------------------------------------------
# JSON 解析失敗
# ---------------------------------------------------------------------------


class TestJsonParseFailure:
    """壊れた JSON や JSON が見つからない場合は [] を返す。"""

    def test_invalid_json_returns_empty(self):
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(response_json="not json at all {{{")
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_empty_response_content_returns_empty(self):
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(response_json="")
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []

    def test_no_json_structure_returns_empty(self):
        """中括弧が見つからない場合は空リスト。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client(response_json="配置なし")
        result = plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)
        assert result == []


# ---------------------------------------------------------------------------
# プロンプトロード — ファイルが存在/不存在のケース
# ---------------------------------------------------------------------------


class TestPromptLoading:
    """_load_prompt のファイル有無による切り替えを確認する。"""

    def test_uses_default_prompt_when_file_missing(self, tmp_path):
        """プロンプトファイルが存在しない場合はデフォルトプロンプトが使われる。"""
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": []})

        with patch(
            "use_cases.ai.se_placement.PROMPT_FILE",
            tmp_path / "nonexistent_prompt.md",
        ):
            plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)

        call_args = client.chat.completions.create.call_args
        prompt_used = call_args.kwargs["messages"][0]["content"]
        assert "{SUBTITLES}" not in prompt_used
        assert "{SE_FILES}" not in prompt_used

    def test_uses_file_prompt_when_file_exists(self, tmp_path):
        """プロンプトファイルが存在する場合はファイル内容が使われる。"""
        prompt_file = tmp_path / "se_placement.md"
        prompt_file.write_text("カスタムプロンプト\n{SUBTITLES}\n{SE_FILES}", encoding="utf-8")
        se_files = _make_se_files(["e.mp3"])
        client = _make_client({"placements": []})

        with patch(
            "use_cases.ai.se_placement.PROMPT_FILE",
            prompt_file,
        ):
            plan_se_placements(client, [_make_entry(1, 0.0, 5.0, "あ")], se_files)

        call_args = client.chat.completions.create.call_args
        prompt_used = call_args.kwargs["messages"][0]["content"]
        assert "カスタムプロンプト" in prompt_used
