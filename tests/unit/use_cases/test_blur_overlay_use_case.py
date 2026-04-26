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

    def test_is_cached_true_with_matching_sidecar(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        # Make a fake PNG and sidecar
        png = output_dir / "01_test_t00.png"
        png.write_bytes(b"\x89PNG\r\n")
        time_ranges = [(5.0, 15.0)]
        stat = video_path.stat()
        sidecar_data = {
            "params": use_case.params.to_dict(),
            "time_ranges": [list(r) for r in time_ranges],
            "source_video": str(video_path),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "overlays": [
                {
                    "png_path": str(png),
                    "start_sec": 5.0,
                    "end_sec": 12.0,
                    "union_x1": 100,
                    "union_y1": 200,
                    "union_x2": 300,
                    "union_y2": 400,
                }
            ],
        }
        use_case.get_sidecar_path(output_dir, "01_test").write_text(
            json.dumps(sidecar_data)
        )
        assert use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_is_cached_false_when_params_differ(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        time_ranges = [(0.0, 10.0)]
        stat = video_path.stat()
        sidecar_data = {
            "params": {"detect_scale": 999},  # 異常な値
            "time_ranges": [list(r) for r in time_ranges],
            "source_video": str(video_path),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "overlays": [],
        }
        use_case.get_sidecar_path(output_dir, "01_test").write_text(
            json.dumps(sidecar_data)
        )
        assert not use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_is_cached_false_when_time_ranges_differ(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        stat = video_path.stat()
        sidecar_data = {
            "params": use_case.params.to_dict(),
            "time_ranges": [[0.0, 10.0]],
            "source_video": str(video_path),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "overlays": [],
        }
        use_case.get_sidecar_path(output_dir, "01_test").write_text(
            json.dumps(sidecar_data)
        )
        # different time_ranges
        assert not use_case.is_cached(video_path, "01_test", [(5.0, 15.0)], output_dir)

    def test_is_cached_false_when_png_missing(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        time_ranges = [(0.0, 10.0)]
        stat = video_path.stat()
        sidecar_data = {
            "params": use_case.params.to_dict(),
            "time_ranges": [list(r) for r in time_ranges],
            "source_video": str(video_path),
            "source_size": stat.st_size,
            "source_mtime": stat.st_mtime,
            "overlays": [
                {
                    "png_path": str(output_dir / "missing.png"),
                    "start_sec": 0.0,
                    "end_sec": 5.0,
                    "union_x1": 0,
                    "union_y1": 0,
                    "union_x2": 100,
                    "union_y2": 100,
                }
            ],
        }
        use_case.get_sidecar_path(output_dir, "01_test").write_text(
            json.dumps(sidecar_data)
        )
        assert not use_case.is_cached(video_path, "01_test", time_ranges, output_dir)

    def test_load_from_cache(
        self, use_case: BlurOverlayUseCase, video_path: Path, output_dir: Path
    ):
        png = output_dir / "01_test_t00.png"
        png.write_bytes(b"\x89PNG\r\n")
        sidecar_data = {
            "params": use_case.params.to_dict(),
            "time_ranges": [[0.0, 10.0]],
            "source_video": str(video_path),
            "source_size": 0,
            "source_mtime": 0,
            "overlays": [
                {
                    "png_path": str(png),
                    "start_sec": 1.0,
                    "end_sec": 9.0,
                    "union_x1": 100,
                    "union_y1": 200,
                    "union_x2": 300,
                    "union_y2": 400,
                }
            ],
        }
        use_case.get_sidecar_path(output_dir, "01_test").write_text(
            json.dumps(sidecar_data)
        )
        overlays = use_case.load_from_cache(output_dir, "01_test")
        assert len(overlays) == 1
        ov = overlays[0]
        assert isinstance(ov, BlurOverlay)
        assert ov.start_sec == 1.0
        assert ov.end_sec == 9.0
        assert ov.union_x1 == 100
        assert ov.union_x2 == 300
