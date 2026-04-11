"""
auto_anchor_detector のユニットテスト

対象モジュール: use_cases/ai/auto_anchor_detector.py
外部依存（subprocess、OpenAI クライアント）はすべてモックする。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from use_cases.ai.auto_anchor_detector import (
    AnchorResult,
    DEFAULT_PROMPT,
    PROMPT_FILE,
    _extract_frame,
    _extract_json,
    _load_prompt,
    anchor_to_fcpxml,
    detect_anchor,
)


# ---------------------------------------------------------------------------
# AnchorResult データクラス
# ---------------------------------------------------------------------------


class TestAnchorResult:
    def test_basic_creation(self):
        result = AnchorResult(anchor_x=0.5, anchor_y=0.3, description="テスト")
        assert result.anchor_x == 0.5
        assert result.anchor_y == 0.3
        assert result.description == "テスト"

    def test_zero_coordinates(self):
        result = AnchorResult(anchor_x=0.0, anchor_y=0.0, description="左上")
        assert result.anchor_x == 0.0
        assert result.anchor_y == 0.0

    def test_boundary_coordinates(self):
        result = AnchorResult(anchor_x=1.0, anchor_y=1.0, description="右下")
        assert result.anchor_x == 1.0
        assert result.anchor_y == 1.0

    def test_empty_description(self):
        result = AnchorResult(anchor_x=0.5, anchor_y=0.5, description="")
        assert result.description == ""

    def test_equality(self):
        r1 = AnchorResult(anchor_x=0.5, anchor_y=0.3, description="同じ")
        r2 = AnchorResult(anchor_x=0.5, anchor_y=0.3, description="同じ")
        assert r1 == r2

    def test_inequality(self):
        r1 = AnchorResult(anchor_x=0.5, anchor_y=0.3, description="A")
        r2 = AnchorResult(anchor_x=0.6, anchor_y=0.3, description="A")
        assert r1 != r2


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        """プレーンな JSON 文字列（コードブロックなし）を抽出できること"""
        text = '{"anchor_x": 0.5, "anchor_y": 0.3, "description": "顔の中心"}'
        result = _extract_json(text)
        data = json.loads(result)
        assert data["anchor_x"] == 0.5

    def test_json_code_block(self):
        """```json ... ``` ブロックから JSON を抽出できること"""
        text = (
            "以下が結果です。\n"
            "```json\n"
            '{"anchor_x": 0.4, "anchor_y": 0.2, "description": "話者の顔"}\n'
            "```\n"
            "以上です。"
        )
        result = _extract_json(text)
        data = json.loads(result)
        assert data["anchor_x"] == pytest.approx(0.4)
        assert data["description"] == "話者の顔"

    def test_generic_code_block(self):
        """``` ... ``` （json 指定なし）ブロックから JSON を抽出できること"""
        text = (
            "結果:\n"
            "```\n"
            '{"anchor_x": 0.6, "anchor_y": 0.5, "description": "中央"}\n'
            "```"
        )
        result = _extract_json(text)
        data = json.loads(result)
        assert data["anchor_x"] == pytest.approx(0.6)

    def test_json_embedded_in_prose(self):
        """散文の中に埋め込まれた JSON を抽出できること"""
        text = 'アンカーは {"anchor_x": 0.5, "anchor_y": 0.3, "description": "test"} です'
        result = _extract_json(text)
        data = json.loads(result)
        assert data["anchor_x"] == 0.5

    def test_whitespace_stripped_from_code_block(self):
        """コードブロック内の前後の空白が除去されること"""
        text = "```json\n\n  {\"anchor_x\": 0.5}\n\n```"
        result = _extract_json(text)
        assert result.startswith("{")
        assert result.endswith("}")

    def test_no_json_raises_value_error(self):
        """JSON が見つからない場合に ValueError を送出すること"""
        with pytest.raises(ValueError, match="JSONを抽出できません"):
            _extract_json("JSON がまったくないテキストです")

    def test_empty_string_raises_value_error(self):
        """空文字列で ValueError を送出すること"""
        with pytest.raises(ValueError):
            _extract_json("")

    def test_only_open_brace_raises(self):
        """'{' だけあって '}' がない場合は ValueError を送出すること"""
        with pytest.raises(ValueError):
            _extract_json("{ 閉じ括弧がない")

    def test_code_block_takes_precedence_over_bare_json(self):
        """コードブロックが優先して抽出されること（外のプレーン JSON より先）"""
        text = (
            '外の {"anchor_x": 0.9} はダミー\n'
            '```json\n{"anchor_x": 0.1, "anchor_y": 0.2, "description": "正解"}\n```'
        )
        result = _extract_json(text)
        data = json.loads(result)
        # コードブロック内の値が返る
        assert data["anchor_x"] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _extract_frame
# ---------------------------------------------------------------------------


class TestExtractFrame:
    def test_success(self, tmp_path):
        """subprocess が成功し JPEG バイト列を返すこと"""
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # 非空バイト列

        def fake_run(cmd, capture_output, check):
            # 一時ファイルに偽の JPEG データを書き込む
            out_path = Path(cmd[-1])
            out_path.write_bytes(fake_jpeg)

        video_path = tmp_path / "sample.mp4"
        video_path.touch()

        with patch("use_cases.ai.auto_anchor_detector.subprocess.run", side_effect=fake_run):
            data = _extract_frame(video_path, time_sec=3.0)

        assert data == fake_jpeg

    def test_ffmpeg_called_with_correct_args(self, tmp_path):
        """ffmpeg が正しい引数で呼び出されること"""
        fake_jpeg = b"\xff\xd8" + b"\x00" * 50

        captured_cmd: list = []

        def fake_run(cmd, capture_output, check):
            captured_cmd.extend(cmd)
            Path(cmd[-1]).write_bytes(fake_jpeg)

        video_path = tmp_path / "video.mp4"
        video_path.touch()

        with patch("use_cases.ai.auto_anchor_detector.subprocess.run", side_effect=fake_run):
            _extract_frame(video_path, time_sec=7.5)

        assert captured_cmd[0] == "ffmpeg"
        assert "-ss" in captured_cmd
        assert "7.5" in captured_cmd
        assert "-i" in captured_cmd
        assert str(video_path) in captured_cmd
        assert "-frames:v" in captured_cmd

    def test_subprocess_error_propagates(self, tmp_path):
        """subprocess.CalledProcessError がそのまま伝播すること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        with patch(
            "use_cases.ai.auto_anchor_detector.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                _extract_frame(video_path, time_sec=5.0)

    def test_empty_output_raises_runtime_error(self, tmp_path):
        """ffmpeg が空ファイルを出力した場合に RuntimeError を送出すること"""
        def fake_run(cmd, capture_output, check):
            # 一時ファイルを空のまま残す（write_bytes 不要）
            Path(cmd[-1]).write_bytes(b"")

        video_path = tmp_path / "video.mp4"
        video_path.touch()

        with patch("use_cases.ai.auto_anchor_detector.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="フレーム抽出に失敗"):
                _extract_frame(video_path, time_sec=5.0)

    def test_temp_file_cleaned_up_on_success(self, tmp_path):
        """正常終了時に一時ファイルが削除されること"""
        fake_jpeg = b"\xff\xd8" + b"\x00" * 10

        created_paths: list[Path] = []

        def fake_run(cmd, capture_output, check):
            p = Path(cmd[-1])
            created_paths.append(p)
            p.write_bytes(fake_jpeg)

        video_path = tmp_path / "video.mp4"
        video_path.touch()

        with patch("use_cases.ai.auto_anchor_detector.subprocess.run", side_effect=fake_run):
            _extract_frame(video_path, time_sec=5.0)

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "一時ファイルが残っている"

    def test_temp_file_cleaned_up_on_error(self, tmp_path):
        """エラー時にも一時ファイルが削除されること"""
        created_paths: list[Path] = []

        def fake_run(cmd, capture_output, check):
            p = Path(cmd[-1])
            created_paths.append(p)
            raise subprocess.CalledProcessError(1, "ffmpeg")

        video_path = tmp_path / "video.mp4"
        video_path.touch()

        with patch("use_cases.ai.auto_anchor_detector.subprocess.run", side_effect=fake_run):
            with pytest.raises(subprocess.CalledProcessError):
                _extract_frame(video_path, time_sec=5.0)

        if created_paths:
            assert not created_paths[0].exists(), "エラー時にも一時ファイルが残っている"


# ---------------------------------------------------------------------------
# _load_prompt
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def test_returns_default_when_file_missing(self, tmp_path):
        """プロンプトファイルが存在しない場合は DEFAULT_PROMPT を返すこと"""
        missing_path = tmp_path / "nonexistent.md"
        with patch("use_cases.ai.auto_anchor_detector.PROMPT_FILE", missing_path):
            result = _load_prompt()
        assert result == DEFAULT_PROMPT

    def test_returns_file_content_when_exists(self, tmp_path):
        """プロンプトファイルが存在する場合はその内容を返すこと"""
        custom_prompt = "カスタムプロンプト内容\nanchor_x と anchor_y を返してください。"
        prompt_file = tmp_path / "anchor_detection.md"
        prompt_file.write_text(custom_prompt, encoding="utf-8")

        with patch("use_cases.ai.auto_anchor_detector.PROMPT_FILE", prompt_file):
            result = _load_prompt()

        assert result == custom_prompt

    def test_file_content_differs_from_default(self, tmp_path):
        """ファイルの内容がデフォルトと異なること（上書きが有効なこと）"""
        custom_content = "# 独自プロンプト\nJSON を返せ。"
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(custom_content, encoding="utf-8")

        with patch("use_cases.ai.auto_anchor_detector.PROMPT_FILE", prompt_file):
            result = _load_prompt()

        assert result != DEFAULT_PROMPT
        assert "独自プロンプト" in result

    def test_default_prompt_contains_required_keys(self):
        """DEFAULT_PROMPT に必須キー（anchor_x, anchor_y）が含まれること"""
        assert "anchor_x" in DEFAULT_PROMPT
        assert "anchor_y" in DEFAULT_PROMPT

    def test_actual_prompt_file_loaded_when_present(self):
        """実際のプロンプトファイルが存在する場合はそれが読み込まれること"""
        if PROMPT_FILE.exists():
            result = _load_prompt()
            assert len(result) > 0
        else:
            pytest.skip("プロンプトファイルが存在しないためスキップ")


# ---------------------------------------------------------------------------
# detect_anchor
# ---------------------------------------------------------------------------


def _make_mock_client(content: str) -> MagicMock:
    """指定したコンテンツを返す OpenAI クライアントのモックを作成する。"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def _make_valid_response_json(
    anchor_x: float = 0.5,
    anchor_y: float = 0.3,
    description: str = "話者の顔の中心",
) -> str:
    return json.dumps(
        {"anchor_x": anchor_x, "anchor_y": anchor_y, "description": description},
        ensure_ascii=False,
    )


class TestDetectAnchor:
    """detect_anchor 関数の総合テスト"""

    FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

    def _patch_extract_frame(self):
        """_extract_frame を FAKE_JPEG を返すモックに差し替えるパッチ"""
        return patch(
            "use_cases.ai.auto_anchor_detector._extract_frame",
            return_value=self.FAKE_JPEG,
        )

    # --- 正常系 ---

    def test_normal_response(self, tmp_path):
        """正常な API レスポンスで AnchorResult が返ること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json(0.4, 0.25, "顔の中心"))

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert isinstance(result, AnchorResult)
        assert result.anchor_x == pytest.approx(0.4)
        assert result.anchor_y == pytest.approx(0.25)
        assert result.description == "顔の中心"

    def test_client_called_with_model_and_tokens(self, tmp_path):
        """API クライアントが正しいモデルとパラメータで呼び出されること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json())

        with self._patch_extract_frame():
            detect_anchor(video_path, client, model="gpt-4o", frame_time=10.0)

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["max_tokens"] == 256
        assert call_kwargs["temperature"] == pytest.approx(0.2)

    def test_response_format_not_set(self, tmp_path):
        """response_format が設定されないこと（Vision+json_objectの互換性問題を回避）"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json())

        with self._patch_extract_frame():
            detect_anchor(video_path, client)

        call_kwargs = client.chat.completions.create.call_args[1]
        assert "response_format" not in call_kwargs

    def test_frame_base64_included_in_message(self, tmp_path):
        """フレーム画像が base64 エンコードされてメッセージに含まれること"""
        import base64

        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json())

        with self._patch_extract_frame():
            detect_anchor(video_path, client)

        messages = client.chat.completions.create.call_args[1]["messages"]
        content_parts = messages[0]["content"]
        # image_url パートを探す
        image_parts = [p for p in content_parts if p.get("type") == "image_url"]
        assert len(image_parts) == 1
        url = image_parts[0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        # デコードしてオリジナルと一致するか確認
        b64_part = url.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded == self.FAKE_JPEG

    # --- JSON がコードブロック内に返される場合 ---

    def test_response_in_code_block(self, tmp_path):
        """```json ... ``` ブロック内の JSON を正しく解析すること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        content = (
            "分析結果:\n"
            "```json\n"
            '{"anchor_x": 0.55, "anchor_y": 0.35, "description": "コードブロック"}\n'
            "```"
        )
        client = _make_mock_client(content)

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(0.55)
        assert result.anchor_y == pytest.approx(0.35)
        assert result.description == "コードブロック"

    # --- 座標クランプ ---

    def test_anchor_x_clamped_when_exceeds_1(self, tmp_path):
        """anchor_x が 1.0 を超える場合に 1.0 にクランプされること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=1.5, anchor_y=0.5)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(1.0)

    def test_anchor_y_clamped_when_exceeds_1(self, tmp_path):
        """anchor_y が 1.0 を超える場合に 1.0 にクランプされること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=0.5, anchor_y=2.0)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_y == pytest.approx(1.0)

    def test_anchor_x_clamped_when_below_0(self, tmp_path):
        """anchor_x が 0.0 未満の場合に 0.0 にクランプされること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=-0.5, anchor_y=0.5)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(0.0)

    def test_anchor_y_clamped_when_below_0(self, tmp_path):
        """anchor_y が 0.0 未満の場合に 0.0 にクランプされること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=0.5, anchor_y=-1.0)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_y == pytest.approx(0.0)

    def test_both_coordinates_clamped(self, tmp_path):
        """両座標が同時に範囲外の場合に両方クランプされること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=99.0, anchor_y=-99.0)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(1.0)
        assert result.anchor_y == pytest.approx(0.0)

    def test_boundary_values_not_clamped(self, tmp_path):
        """境界値（0.0、1.0）はクランプされないこと"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(
            _make_valid_response_json(anchor_x=0.0, anchor_y=1.0)
        )

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(0.0)
        assert result.anchor_y == pytest.approx(1.0)

    # --- JSON 解析失敗フォールバック ---

    def test_json_parse_failure_returns_default(self, tmp_path):
        """API が不正な JSON を返した場合にデフォルト値でフォールバックすること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client("これは JSON ではありません。申し訳ございません。")

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert isinstance(result, AnchorResult)
        assert result.anchor_x == pytest.approx(0.5)
        assert result.anchor_y == pytest.approx(0.5)
        assert "デフォルト" in result.description

    def test_malformed_json_returns_default(self, tmp_path):
        """構文エラーの JSON を返した場合にフォールバックすること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client('{"anchor_x": 0.5, "anchor_y": INVALID}')

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(0.5)
        assert result.anchor_y == pytest.approx(0.5)

    def test_empty_response_returns_default(self, tmp_path):
        """API が空文字列を返した場合にフォールバックすること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with self._patch_extract_frame():
            result = detect_anchor(video_path, mock_client)

        assert isinstance(result, AnchorResult)
        assert result.anchor_x == pytest.approx(0.5)
        assert result.anchor_y == pytest.approx(0.5)

    def test_none_response_returns_default(self, tmp_path):
        """API が None コンテンツを返した場合にフォールバックすること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        mock_response = MagicMock()
        mock_response.choices[0].message.content = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with self._patch_extract_frame():
            result = detect_anchor(video_path, mock_client)

        assert isinstance(result, AnchorResult)
        assert result.anchor_x == pytest.approx(0.5)

    # --- API エラーとフォールバック ---

    def test_api_error_propagates(self, tmp_path):
        """API 呼び出し自体が例外を送出した場合はそのまま伝播すること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("接続エラー")

        with self._patch_extract_frame():
            with pytest.raises(RuntimeError, match="接続エラー"):
                detect_anchor(video_path, mock_client)

    def test_frame_extraction_error_propagates(self, tmp_path):
        """フレーム抽出が失敗した場合はそのまま伝播すること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        mock_client = MagicMock()

        with patch(
            "use_cases.ai.auto_anchor_detector._extract_frame",
            side_effect=RuntimeError("フレーム抽出失敗"),
        ):
            with pytest.raises(RuntimeError, match="フレーム抽出失敗"):
                detect_anchor(video_path, mock_client)

    # --- プロンプトの使用 ---

    def test_custom_prompt_used_in_message(self, tmp_path):
        """_load_prompt の返す内容がメッセージに含まれること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        custom_prompt = "# カスタムプロンプト\nJSON を返せ。"
        client = _make_mock_client(_make_valid_response_json())

        with self._patch_extract_frame():
            with patch(
                "use_cases.ai.auto_anchor_detector._load_prompt",
                return_value=custom_prompt,
            ):
                detect_anchor(video_path, client)

        messages = client.chat.completions.create.call_args[1]["messages"]
        content_parts = messages[0]["content"]
        text_parts = [p for p in content_parts if p.get("type") == "text"]
        assert len(text_parts) == 1
        assert text_parts[0]["text"] == custom_prompt

    # --- 欠損フィールドのデフォルト値 ---

    def test_missing_anchor_x_uses_default(self, tmp_path):
        """JSON に anchor_x がない場合にデフォルト 0.5 が使われること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        content = json.dumps({"anchor_y": 0.4, "description": "anchor_x なし"})
        client = _make_mock_client(content)

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_x == pytest.approx(0.5)

    def test_missing_anchor_y_uses_default(self, tmp_path):
        """JSON に anchor_y がない場合にデフォルト 0.5 が使われること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        content = json.dumps({"anchor_x": 0.6, "description": "anchor_y なし"})
        client = _make_mock_client(content)

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.anchor_y == pytest.approx(0.5)

    def test_missing_description_uses_empty_string(self, tmp_path):
        """JSON に description がない場合に空文字列が使われること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        content = json.dumps({"anchor_x": 0.5, "anchor_y": 0.3})
        client = _make_mock_client(content)

        with self._patch_extract_frame():
            result = detect_anchor(video_path, client)

        assert result.description == ""

    # --- カスタムモデルと frame_time ---

    def test_custom_model_passed_to_api(self, tmp_path):
        """カスタムモデル名が API に渡されること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json())

        with self._patch_extract_frame():
            detect_anchor(video_path, client, model="gpt-4o-mini")

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_custom_frame_time_passed_to_extract(self, tmp_path):
        """カスタム frame_time が _extract_frame に渡されること"""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        client = _make_mock_client(_make_valid_response_json())

        with patch(
            "use_cases.ai.auto_anchor_detector._extract_frame",
            return_value=self.FAKE_JPEG,
        ) as mock_extract:
            detect_anchor(video_path, client, frame_time=12.5)

        mock_extract.assert_called_once_with(video_path, 12.5)


# ---------------------------------------------------------------------------
# anchor_to_fcpxml 変換関数
# ---------------------------------------------------------------------------


class TestAnchorToFcpxml:
    """正規化座標→FCPXML座標系の変換テスト"""

    def test_center_returns_zero(self):
        """中央(0.5, 0.5)はFCPXML(0, 0)になる"""
        x, y = anchor_to_fcpxml(0.5, 0.5, 1920, 1080, (2.4, 2.4))
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.0)

    def test_left_of_center(self):
        """左寄り(0.4, 0.5)は負のXになる"""
        x, y = anchor_to_fcpxml(0.4, 0.5, 1920, 1080, (2.4, 2.4))
        assert x == pytest.approx(-10.0 / 2.4)
        assert y == pytest.approx(0.0)

    def test_right_of_center(self):
        """右寄り(0.7, 0.5)は正のXになる"""
        x, y = anchor_to_fcpxml(0.7, 0.5, 1920, 1080, (2.4, 2.4))
        assert x == pytest.approx(20.0 / 2.4)
        assert y == pytest.approx(0.0)

    def test_top_of_center(self):
        """上寄り(0.5, 0.3)は正のYになる（FCPXML座標系はY反転）"""
        x, y = anchor_to_fcpxml(0.5, 0.3, 1920, 1080, (2.4, 2.4))
        assert x == pytest.approx(0.0)
        assert y > 0  # 上方向は正

    def test_bottom_of_center(self):
        """下寄り(0.5, 0.7)は負のYになる"""
        x, y = anchor_to_fcpxml(0.5, 0.7, 1920, 1080, (2.4, 2.4))
        assert x == pytest.approx(0.0)
        assert y < 0  # 下方向は負

    def test_scale_affects_result(self):
        """スケールが大きいほどFCPXML値は小さくなる"""
        x1, _ = anchor_to_fcpxml(0.4, 0.5, 1920, 1080, (1.0, 1.0))
        x2, _ = anchor_to_fcpxml(0.4, 0.5, 1920, 1080, (2.0, 2.0))
        assert abs(x1) > abs(x2)

    def test_scale_one(self):
        """スケール1.0のとき、元の式と一致する"""
        x, y = anchor_to_fcpxml(0.4, 0.3, 1920, 1080, (1.0, 1.0))
        assert x == pytest.approx(-10.0)
        assert y == pytest.approx(20.0 * 1920 / 1080)

    def test_zero_scale_uses_fallback(self):
        """スケール0はゼロ除算せず、1.0にフォールバックする"""
        x, y = anchor_to_fcpxml(0.4, 0.5, 1920, 1080, (0.0, 0.0))
        assert x == pytest.approx(-10.0)
        assert y == pytest.approx(0.0)

    def test_negative_scale_uses_fallback(self):
        """負のスケールもフォールバックする"""
        x, y = anchor_to_fcpxml(0.4, 0.5, 1920, 1080, (-1.0, -1.0))
        assert x == pytest.approx(-10.0)
        assert y == pytest.approx(0.0)

    def test_aspect_ratio_4_3(self):
        """4:3アスペクト比でも正しく計算される"""
        x, y = anchor_to_fcpxml(0.5, 0.3, 1440, 1080, (2.0, 2.0))
        expected_y = 20.0 * 1440 / 1080 / 2.0
        assert y == pytest.approx(expected_y)

    def test_aspect_ratio_1_1(self):
        """1:1アスペクト比"""
        x, y = anchor_to_fcpxml(0.5, 0.3, 1080, 1080, (2.0, 2.0))
        expected_y = 20.0 * 1080 / 1080 / 2.0
        assert y == pytest.approx(expected_y)

    def test_extreme_corner_top_left(self):
        """左上端(0.0, 0.0)"""
        x, y = anchor_to_fcpxml(0.0, 0.0, 1920, 1080, (2.0, 2.0))
        assert x == pytest.approx(-50.0 / 2.0)
        assert y == pytest.approx(50.0 * 1920 / 1080 / 2.0)

    def test_extreme_corner_bottom_right(self):
        """右下端(1.0, 1.0)"""
        x, y = anchor_to_fcpxml(1.0, 1.0, 1920, 1080, (2.0, 2.0))
        assert x == pytest.approx(50.0 / 2.0)
        assert y == pytest.approx(-50.0 * 1920 / 1080 / 2.0)

    def test_asymmetric_scale(self):
        """X/Yで異なるスケール"""
        x, y = anchor_to_fcpxml(0.3, 0.3, 1920, 1080, (2.0, 3.0))
        assert x == pytest.approx(-20.0 / 2.0)
        expected_y = 20.0 * 1920 / 1080 / 3.0
        assert y == pytest.approx(expected_y)
