"""auto_blur ユースケースの単体テスト.

ハッシュキー決定性 / cache invalidation / 周辺ユーティリティを検証する.
heavy 依存 (ocrmac, opencv) を使う実検出系は別途 integration test 側で扱う.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from core.text_blur.detector import Box, merge_boxes, sample_edge_color
from use_cases.auto_blur import AutoBlurParams, AutoBlurUseCase


# ────────────────────────────────────────────────────────────────────
# AutoBlurParams.hash_key
# ────────────────────────────────────────────────────────────────────


class TestAutoBlurParamsHashKey:
    def test_hash_is_deterministic(self):
        """同一 params なら同一 hash."""
        p1 = AutoBlurParams()
        p2 = AutoBlurParams()
        assert p1.hash_key() == p2.hash_key()

    def test_hash_changes_when_param_changes(self):
        """blur_sigma を変えれば hash も変わる."""
        p1 = AutoBlurParams()
        p2 = AutoBlurParams(blur_sigma=50.0)
        assert p1.hash_key() != p2.hash_key()

    def test_hash_independent_of_field_order(self):
        """sort_keys=True なので field 順は影響しない."""
        p1 = AutoBlurParams(blur_sigma=40.0, padding=12)
        p2 = AutoBlurParams(padding=12, blur_sigma=40.0)
        assert p1.hash_key() == p2.hash_key()

    def test_hash_length_16(self):
        """16 桁に切り詰められる."""
        assert len(AutoBlurParams().hash_key()) == 16

    def test_languages_list_change_affects_hash(self):
        p1 = AutoBlurParams(languages=["ja"])
        p2 = AutoBlurParams(languages=["ja", "en"])
        assert p1.hash_key() != p2.hash_key()


# ────────────────────────────────────────────────────────────────────
# AutoBlurUseCase.is_cached / get_cache_paths
# ────────────────────────────────────────────────────────────────────


class TestAutoBlurUseCaseCache:
    @pytest.fixture
    def video_path(self, tmp_path: Path) -> Path:
        """ダミー動画ファイル (中身は空 mp4 ヘッダだが is_cached の判定には十分)."""
        v = tmp_path / "sample.mp4"
        v.write_bytes(b"\x00" * 1024)  # 1KB ダミー
        return v

    @pytest.fixture
    def use_case(self) -> AutoBlurUseCase:
        return AutoBlurUseCase(AutoBlurParams())

    def test_get_cache_paths_layout(self, use_case: AutoBlurUseCase, tmp_path: Path):
        """cache パスは {video}_TextffCut/source_blurred.mp4 + sidecar."""
        video = tmp_path / "myvid.mp4"
        out, sidecar = use_case.get_cache_paths(video)
        assert out == tmp_path / "myvid_TextffCut" / "source_blurred.mp4"
        assert sidecar == tmp_path / "myvid_TextffCut" / "source_blurred.params.json"

    def test_is_cached_false_when_no_files(self, use_case: AutoBlurUseCase, video_path: Path):
        assert use_case.is_cached(video_path) is False

    def test_is_cached_false_when_only_video_exists(
        self, use_case: AutoBlurUseCase, video_path: Path
    ):
        out, _ = use_case.get_cache_paths(video_path)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        # sidecar 不在 → False
        assert use_case.is_cached(video_path) is False

    def test_is_cached_true_when_both_files_match(
        self, use_case: AutoBlurUseCase, video_path: Path
    ):
        out, sidecar = use_case.get_cache_paths(video_path)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        stat = video_path.stat()
        sidecar.write_text(
            json.dumps(
                {
                    "hash_key": use_case.params.hash_key(),
                    "params": use_case.params.to_dict(),
                    "source_size": stat.st_size,
                    "source_mtime": stat.st_mtime,
                }
            )
        )
        assert use_case.is_cached(video_path) is True

    def test_is_cached_false_when_hash_mismatch(
        self, use_case: AutoBlurUseCase, video_path: Path
    ):
        out, sidecar = use_case.get_cache_paths(video_path)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        stat = video_path.stat()
        sidecar.write_text(
            json.dumps(
                {
                    "hash_key": "different_hash",
                    "source_size": stat.st_size,
                    "source_mtime": stat.st_mtime,
                }
            )
        )
        assert use_case.is_cached(video_path) is False

    def test_is_cached_false_when_size_mismatch(
        self, use_case: AutoBlurUseCase, video_path: Path
    ):
        """元動画 size が cache 記録と違えば invalidate."""
        out, sidecar = use_case.get_cache_paths(video_path)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        sidecar.write_text(
            json.dumps(
                {
                    "hash_key": use_case.params.hash_key(),
                    "source_size": 999999,  # 違うサイズ
                    "source_mtime": video_path.stat().st_mtime,
                }
            )
        )
        assert use_case.is_cached(video_path) is False

    def test_is_cached_false_when_sidecar_corrupt(
        self, use_case: AutoBlurUseCase, video_path: Path
    ):
        """壊れた sidecar は False (例外を吐かず)."""
        out, sidecar = use_case.get_cache_paths(video_path)
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x")
        sidecar.write_text("{ this is not valid json")
        assert use_case.is_cached(video_path) is False


# ────────────────────────────────────────────────────────────────────
# Box / merge_boxes
# ────────────────────────────────────────────────────────────────────


class TestBoxOps:
    def test_iou_disjoint_returns_zero(self):
        a = Box(0, 0, 10, 10)
        b = Box(20, 20, 30, 30)
        assert a.iou(b) == 0.0

    def test_iou_identical_returns_one(self):
        a = Box(0, 0, 10, 10)
        b = Box(0, 0, 10, 10)
        assert a.iou(b) == 1.0

    def test_iou_half_overlap(self):
        # 10x10 が 5x10 重なる → IoU = 50 / (100+100-50) = 50/150 ≈ 0.333
        a = Box(0, 0, 10, 10)
        b = Box(5, 0, 15, 10)
        assert pytest.approx(a.iou(b), rel=0.01) == 50 / 150

    def test_expand_clamps_to_bounds(self):
        a = Box(5, 5, 10, 10)
        e = a.expand(10, max_w=15, max_h=15)
        assert (e.x1, e.y1, e.x2, e.y2) == (0, 0, 15, 15)

    def test_as_xywh(self):
        b = Box(10, 20, 50, 60)
        assert b.as_xywh() == (10, 20, 40, 40)


class TestMergeBoxes:
    def test_empty_input(self):
        assert merge_boxes([]) == []

    def test_no_overlap_no_merge(self):
        boxes = [Box(0, 0, 10, 10), Box(100, 100, 110, 110)]
        merged = merge_boxes(boxes, gap_x=5, gap_y=5)
        assert len(merged) == 2

    def test_close_boxes_merge(self):
        boxes = [Box(0, 0, 10, 10), Box(15, 0, 25, 10)]
        merged = merge_boxes(boxes, gap_x=10, gap_y=0)
        assert len(merged) == 1
        m = merged[0]
        assert (m.x1, m.y1, m.x2, m.y2) == (0, 0, 25, 10)

    def test_chain_merge(self):
        """ 3 個並んだ box が 1 個にまとまる."""
        boxes = [Box(0, 0, 10, 10), Box(15, 0, 25, 10), Box(30, 0, 40, 10)]
        merged = merge_boxes(boxes, gap_x=10, gap_y=0)
        assert len(merged) == 1
        assert merged[0].x2 == 40


# ────────────────────────────────────────────────────────────────────
# sample_edge_color
# ────────────────────────────────────────────────────────────────────


class TestSampleEdgeColor:
    def _solid_frame(self, color_bgr: tuple[int, int, int], h: int = 100, w: int = 100):
        """numpy が無い環境では skip."""
        np = pytest.importorskip("numpy")
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = color_bgr
        return frame

    def test_uniform_color_returns_that_color(self):
        frame = self._solid_frame((50, 100, 200))  # BGR
        box = Box(40, 40, 60, 60)
        result = sample_edge_color(frame, box, border_width=5)
        assert result == (50, 100, 200)

    def test_box_at_image_edge_no_crash(self):
        """画像端の bbox でも例外を吐かず median を返す."""
        frame = self._solid_frame((100, 100, 100))
        box = Box(0, 0, 10, 10)
        result = sample_edge_color(frame, box, border_width=5)
        # 上端・左端の strip が取れないが、下端・右端で取れるので gray が返る
        assert result == (100, 100, 100)

    def test_bbox_completely_at_image_corner(self):
        """画像の四隅すべて outside で fallback gray を返す."""
        np = pytest.importorskip("numpy")
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        # 全画面に近い bbox なので border 取れない
        box = Box(0, 0, 10, 10)
        result = sample_edge_color(frame, box, border_width=5)
        # samples は空 → fallback (128,128,128)
        assert result == (128, 128, 128)
