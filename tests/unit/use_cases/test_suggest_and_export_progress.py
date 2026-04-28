"""SuggestAndExportUseCase の progress_reporter callback テスト。

GUI/CLI 統合 (PR refactor/integrate-gui-cli-pipeline) で導入した
progress_reporter フィールドが Phase 境界で呼び出されることを検証する。

外部 API/ffmpeg 依存を避けるため、GenerateClipSuggestionsUseCase.execute と
SuggestAndExportResult 生成に必要な部分のみ mock する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from domain.entities.clip_suggestion import TopicDetectionResult
from domain.entities.transcription import (
    TranscriptionResult,
    TranscriptionSegment,
    Word,
)
from use_cases.ai.suggest_and_export import (
    SuggestAndExportRequest,
    SuggestAndExportUseCase,
)


def _make_transcription() -> TranscriptionResult:
    """ダミーの TranscriptionResult を作る (segments 1 件、words 数件)。"""
    words = [
        Word(word="テスト", start=0.0, end=1.0, confidence=1.0),
        Word(word="です", start=1.0, end=2.0, confidence=1.0),
    ]
    seg = TranscriptionSegment(
        id="seg1",
        text="テストです",
        start=0.0,
        end=2.0,
        words=words,
    )
    return TranscriptionResult(
        id="t1",
        video_id="dummy.mp4",
        language="ja",
        segments=[seg],
        duration=2.0,
        original_audio_path="",
        model_size="dummy",
        processing_time=0.0,
    )


def _make_detection_result() -> TopicDetectionResult:
    return TopicDetectionResult(
        topics=[],
        model_used="gpt-4.1-mini",
        processing_time=0.1,
        token_usage={},
        estimated_cost_usd=0.0,
    )


@pytest.fixture
def stub_gateway() -> MagicMock:
    return MagicMock()


def _build_request(
    tmp_path,
    progress_reporter=None,
    **overrides,
) -> SuggestAndExportRequest:
    """重い Phase はすべて off にしたミニマル Request。"""
    video_path = tmp_path / "dummy.mp4"
    video_path.write_bytes(b"")  # 空ファイル (実 ffmpeg は呼ばれない)
    defaults = {
        "video_path": video_path,
        "transcription": _make_transcription(),
        "remove_silence": False,
        "generate_srt": False,
        "enable_frame": False,
        "enable_bgm": False,
        "enable_se": False,
        "speed": 1.0,
        "enable_title_image": False,
        "auto_anchor": False,
        "enable_blur_overlay": False,
        "progress_reporter": progress_reporter,
    }
    defaults.update(overrides)
    return SuggestAndExportRequest(**defaults)


def _patch_pipeline_internals(use_case: SuggestAndExportUseCase, suggestions: list):
    """GenerateClipSuggestionsUseCase を suggestions 返すモックに差し替え、
    重い後段 (FCPXML 出力 / メディア検出) を no-op にする。
    """
    detection = _make_detection_result()

    class _StubGen:
        def __init__(self, _gw):
            self.last_detection_result = detection

        def execute(self, **_kwargs):
            return suggestions

    return [
        patch(
            "use_cases.ai.suggest_and_export.GenerateClipSuggestionsUseCase",
            _StubGen,
        ),
        patch(
            "utils.media_asset_detector.detect_media_assets",
            return_value=MagicMock(
                has_any=False,
                summary=lambda: "",
                overlay_settings=None,
                additional_audio_settings=None,
            ),
        ),
        patch.object(use_case, "_save_cache", return_value=None),
        patch.object(use_case, "_export_fcpxml", return_value=True),
    ]


def test_progress_reporter_called_at_each_phase(stub_gateway, tmp_path):
    """progress_reporter が Phase 境界で複数回呼ばれることを検証。

    suggestions=0 (= 後段 Phase の loop が回らない) でも、
    最低限 Phase1-3 と完了通知の 2 回は callback される。
    """
    use_case = SuggestAndExportUseCase(gateway=stub_gateway)
    reporter = MagicMock()
    request = _build_request(tmp_path, progress_reporter=reporter)

    patches = _patch_pipeline_internals(use_case, suggestions=[])
    for p in patches:
        p.start()
    try:
        use_case.execute(request)
    finally:
        for p in patches:
            p.stop()

    # 最低限の Phase 境界 (話題検出開始 + 完了通知)
    assert reporter.call_count >= 2, f"想定 >=2 callback、実際 {reporter.call_count}"

    # 進捗 pct は 0.0 〜 1.0 の範囲
    pcts = [call.args[0] for call in reporter.call_args_list]
    assert all(0.0 <= p <= 1.0 for p in pcts), f"pct 範囲外: {pcts}"

    # 最初は 0.0、最後は 1.0
    assert pcts[0] == 0.0
    assert pcts[-1] == 1.0

    # メッセージは str
    msgs = [call.args[1] for call in reporter.call_args_list]
    assert all(isinstance(m, str) and m for m in msgs)


def test_progress_reporter_optional(stub_gateway, tmp_path):
    """progress_reporter=None でも例外なく実行完了する。"""
    use_case = SuggestAndExportUseCase(gateway=stub_gateway)
    request = _build_request(tmp_path, progress_reporter=None)

    patches = _patch_pipeline_internals(use_case, suggestions=[])
    for p in patches:
        p.start()
    try:
        result = use_case.execute(request)
    finally:
        for p in patches:
            p.stop()

    assert result is not None
    assert result.suggestions == []


def test_progress_reporter_exception_swallowed(stub_gateway, tmp_path, caplog):
    """progress_reporter が raise しても本処理は継続する。"""
    use_case = SuggestAndExportUseCase(gateway=stub_gateway)

    def failing_reporter(_pct, _msg):
        raise RuntimeError("UI が壊れた想定")

    request = _build_request(tmp_path, progress_reporter=failing_reporter)

    patches = _patch_pipeline_internals(use_case, suggestions=[])
    for p in patches:
        p.start()
    try:
        result = use_case.execute(request)
    finally:
        for p in patches:
            p.stop()

    # 本処理は完走する
    assert result is not None
    # 例外は warning として log される
    assert any(
        "progress_reporter callback で例外" in rec.message for rec in caplog.records
    ), f"warning log がない: {[r.message for r in caplog.records]}"
