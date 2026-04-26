"""BlurOverlayUseCase の cache / sidecar JSON 周りの単体テスト。

実際の OCR (ocrmac) は Apple Silicon Mac でしか動かないため、execute() 自体は
テスト対象外。is_cached() / load_from_cache() / get_sidecar_path() のみ検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from use_cases.auto_blur.blur_overlay_use_case import (
    BlurOverlay,
    BlurOverlayParams,
    BlurOverlayUseCase,
)


class TestBlurOverlayParams:
    def test_defaults(self):
        p = BlurOverlayParams()
        assert p.detect_scale == 0.5
        assert p.base_interval == 1.0
        assert p.languages == ["ja", "en"]

    def test_to_dict_roundtrip(self):
        p = BlurOverlayParams(padding=20)
        d = p.to_dict()
        assert d["padding"] == 20
        assert d["languages"] == ["ja", "en"]


class TestBlurOverlayUseCaseCache:
    @pytest.fixture
    def video_path(self, tmp_path: Path) -> Path:
        v = tmp_path / "source.mp4"
        v.write_bytes(b"fake video content")
        return v

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "blur_overlays"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @pytest.fixture
    def use_case(self) -> BlurOverlayUseCase:
        return BlurOverlayUseCase()

    def test_get_sidecar_path(self, use_case: BlurOverlayUseCase, tmp_path: Path):
        sidecar = use_case.get_sidecar_path(tmp_path, "01_test")
        assert sidecar == tmp_path / "01_test.overlays.json"

    def test_is_cached_false_when_no_sidecar(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        assert not use_case.is_cached(video_path, "01_test", [(0.0, 10.0)], output_dir)

    def _make_sidecar(self, use_case, video_path, time_ranges, overlays_data,
                      version: int | None = None, params_override: dict | None = None):
        """sidecar 生成ヘルパー (version は明示指定可能、None なら現行 version)."""
        stat = video_path.stat()
        return {
            "version": version if version is not None else use_case.SIDECAR_VERSION,
            "params": params_override if params_override is not None else use_case.params.to_dict(),
            "time_ranges": [list(r) for r in time_ranges],
            "source_video": str(video_path),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "overlays": overlays_data,
        }

    def test_is_cached_true_with_matching_sidecar(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        png = output_dir / "01_test.png"
        png.write_bytes(b"\x89PNG\r\n")
        time_ranges = [(5.0, 15.0)]
        sidecar_data = self._make_sidecar(
            use_case, video_path, time_ranges,
            [{"png_path": str(png), "start_sec": 5.0, "end_sec": 15.0,
              "union_x1": 100, "union_y1": 200, "union_x2": 300, "union_y2": 400}],
        )
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        assert use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_is_cached_false_when_old_schema_v1(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        """旧スキーマ (version 不在 = v1 の 1 track = 1 PNG 方式) は無効化される."""
        png = output_dir / "01_test_t00.png"
        png.write_bytes(b"\x89PNG\r\n")
        time_ranges = [(5.0, 15.0)]
        # version フィールド無し = 旧スキーマ
        sidecar_data = self._make_sidecar(
            use_case, video_path, time_ranges,
            [{"png_path": str(png), "start_sec": 5.0, "end_sec": 12.0,
              "union_x1": 100, "union_y1": 200, "union_x2": 300, "union_y2": 400}],
            version=None,  # version キー無しを表現
        )
        del sidecar_data["version"]  # 旧スキーマには version 自体が存在しなかった
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        assert not use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_is_cached_false_when_params_differ(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        time_ranges = [(0.0, 10.0)]
        sidecar_data = self._make_sidecar(
            use_case, video_path, time_ranges, [],
            params_override={"detect_scale": 999},
        )
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        assert not use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_is_cached_false_when_time_ranges_differ(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        sidecar_data = self._make_sidecar(use_case, video_path, [(0.0, 10.0)], [])
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        assert not use_case.is_cached(video_path, "01_test", [(5.0, 15.0)], output_dir)

    def test_is_cached_false_when_png_missing(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        time_ranges = [(0.0, 10.0)]
        sidecar_data = self._make_sidecar(
            use_case, video_path, time_ranges,
            [{"png_path": str(output_dir / "missing.png"), "start_sec": 0.0, "end_sec": 5.0,
              "union_x1": 0, "union_y1": 0, "union_x2": 100, "union_y2": 100}],
        )
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        assert not use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_load_from_cache(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        png = output_dir / "01_test.png"
        png.write_bytes(b"\x89PNG\r\n")
        sidecar_data = self._make_sidecar(
            use_case, video_path, [(0.0, 10.0)],
            [{"png_path": str(png), "start_sec": 1.0, "end_sec": 9.0,
              "union_x1": 100, "union_y1": 200, "union_x2": 300, "union_y2": 400}],
        )
        use_case.get_sidecar_path(output_dir, "01_test").write_text(json.dumps(sidecar_data))
        overlays = use_case.load_from_cache(output_dir, "01_test")
        assert len(overlays) == 1
        ov = overlays[0]
        assert isinstance(ov, BlurOverlay)
        assert ov.start_sec == 1.0
        assert ov.end_sec == 9.0


class TestBlurOverlaySidecarVersion:
    """SIDECAR_VERSION 定数の存在と整合性確認."""

    def test_version_is_v2(self):
        """v2 = 1 clip = 1 合成 PNG 方式. 旧 v1 は無効化される必要がある."""
        assert BlurOverlayUseCase.SIDECAR_VERSION == 2


class TestRenderCompositeOverlayPng:
    """合成 PNG 描画のテスト (cv2.VideoCapture をモック)."""

    def test_multiple_bboxes_painted_with_individual_colors(self, tmp_path, monkeypatch):
        """複数 bbox + 各色で塗られて 1 枚に合成されることを確認."""
        from unittest.mock import MagicMock

        import cv2

        from use_cases.auto_blur import blur_overlay_use_case as mod

        # cv2.VideoCapture をモック (1920x1080)
        def fake_get(prop):
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return 1920
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return 1080
            return 0

        mock_cap = MagicMock()
        mock_cap.get.side_effect = fake_get
        monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **kw: mock_cap)

        png_path = tmp_path / "composite.png"
        bboxes = [
            (100, 200, 300, 400, (10, 20, 30)),  # 左上 area
            (500, 600, 700, 800, (40, 50, 60)),  # 右下 area
            (800, 100, 1900, 200, (70, 80, 90)),  # 横長 area
        ]
        mod._render_composite_overlay_png(png_path, tmp_path / "fake.mp4", bboxes)
        assert png_path.exists()
        img = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
        assert img is not None
        assert img.shape == (1080, 1920, 4)
        for x1, y1, x2, y2, (b, g, r) in bboxes:
            cy = (y1 + y2) // 2
            cx = (x1 + x2) // 2
            pixel = img[cy, cx]
            assert pixel[0] == b and pixel[1] == g and pixel[2] == r and pixel[3] == 255, (
                f"bbox 中央 ({cx},{cy}) 期待色 BGR=({b},{g},{r}) 実際={pixel.tolist()}"
            )
        # bbox 外は透明
        outside_pixel = img[10, 10]
        assert outside_pixel[3] == 0
