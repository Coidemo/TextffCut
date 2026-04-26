"""
core/export.py のユニットテスト
"""

import math

import pytest

from core.export import _safe_volume_db


class TestSafeVolumeDb:
    """_safe_volume_db() のテスト

    adjust-volume amount用の安全な文字列を返す関数。
    dB範囲 [-96, 12] にクランプし、不正入力は "0" にフォールバックする。
    """

    # --- 正常な数値入力 ---

    def test_normal_negative_value(self):
        assert _safe_volume_db(-20.0) == "-20"

    def test_normal_positive_value(self):
        assert _safe_volume_db(5) == "5"

    # --- 範囲クランプ ---

    def test_clamp_below_minimum(self):
        """下限 -96 未満の値は -96 にクランプ"""
        assert _safe_volume_db(-200) == "-96"

    def test_clamp_above_maximum(self):
        """上限 12 超の値は 12 にクランプ"""
        assert _safe_volume_db(100) == "12"

    # --- 境界値 ---

    def test_boundary_minimum(self):
        assert _safe_volume_db(-96) == "-96"

    def test_boundary_maximum(self):
        assert _safe_volume_db(12) == "12"

    def test_boundary_just_inside_min(self):
        assert _safe_volume_db(-95.9) == "-95.9"

    def test_boundary_just_inside_max(self):
        assert _safe_volume_db(11.9) == "11.9"

    # --- ゼロ ---

    def test_zero(self):
        assert _safe_volume_db(0) == "0"

    def test_zero_float(self):
        assert _safe_volume_db(0.0) == "0"

    # --- 小数値 ---

    def test_decimal_value(self):
        assert _safe_volume_db(-3.5) == "-3.5"

    def test_decimal_positive(self):
        assert _safe_volume_db(1.5) == "1.5"

    # --- 不正入力のフォールバック ---

    def test_string_input_returns_zero(self):
        assert _safe_volume_db("abc") == "0"

    def test_none_input_returns_zero(self):
        assert _safe_volume_db(None) == "0"

    # --- 特殊な浮動小数点値 ---

    def test_positive_inf_clamped_to_max(self):
        """float('inf') は上限 12 にクランプ"""
        assert _safe_volume_db(float("inf")) == "12"

    def test_negative_inf_clamped_to_min(self):
        """float('-inf') は下限 -96 にクランプ"""
        assert _safe_volume_db(float("-inf")) == "-96"

    def test_nan_does_not_crash(self):
        """float('nan') でクラッシュせず、有効な文字列を返す"""
        result = _safe_volume_db(float("nan"))
        # NaN は比較が特殊だが、クラッシュせず文字列を返すことを確認
        assert isinstance(result, str)
        # 結果が有効なdB範囲内の数値であることを確認
        assert float(result) <= 12
        assert float(result) >= -96

    # --- 文字列で渡された数値 ---

    def test_numeric_string(self):
        """数値文字列は正常に変換される"""
        assert _safe_volume_db("-10") == "-10"

    def test_numeric_string_float(self):
        assert _safe_volume_db("3.5") == "3.5"


# --- blur_overlays 統合 (V2.5.0+) ---

class TestBlurOverlayFCPXML:
    """blur_overlays が FCPXML に正しく組み込まれるか検証する。

    実 ffprobe を避けるため VideoInfo.from_file をモックする。
    """

    @pytest.fixture
    def mock_video(self, tmp_path, monkeypatch):
        """source.mp4 と blur PNG を準備し、VideoInfo.from_file をモック。"""
        from unittest.mock import MagicMock

        from core import export as export_mod

        video_path = tmp_path / "source.mp4"
        video_path.write_bytes(b"fake")
        png_path = tmp_path / "01_test_t00.png"
        png_path.write_bytes(b"\x89PNG\r\n")

        fake_info = MagicMock()
        fake_info.duration = 60.0
        fake_info.fps = 30
        fake_info.width = 1920
        fake_info.height = 1080
        monkeypatch.setattr(export_mod.VideoInfo, "from_file", lambda *a, **kw: fake_info)
        return {"video": video_path, "png": png_path}

    def test_blur_overlay_emits_v2_lane(self, mock_video, tmp_path):
        """blur_overlays を渡すと lane=1 で <video> 要素が出力される。"""
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=10.0,
                end_time=30.0,
                timeline_start=0.0,
            ),
        ]
        blur_overlays = [
            {"png_path": str(mock_video["png"]), "start_sec": 12.0, "end_sec": 25.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # blur PNG の asset 登録
        assert mock_video["png"].name in xml
        # lane=1 で video 要素
        assert 'lane="1"' in xml
        # offset は (12.0 - 10.0) = 2 秒 = 60/30s
        assert 'offset="2/1s"' in xml or 'offset="60/30s"' in xml
        # duration は (25.0 - 12.0) = 13 秒 = 13/1s or 390/30s
        assert 'duration="13/1s"' in xml or 'duration="390/30s"' in xml

    def test_blur_overlay_shifts_frame_to_lane2(self, mock_video, tmp_path):
        """blur_overlays + frame の場合、frame は lane=2 にシフトされる。"""
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        frame_path = tmp_path / "frame.png"
        frame_path.write_bytes(b"\x89PNG\r\n")

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=10.0,
                timeline_start=0.0,
            ),
        ]
        blur_overlays = [
            {"png_path": str(mock_video["png"]), "start_sec": 0.0, "end_sec": 10.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            blur_overlays=blur_overlays,
            overlay_settings={"frame_path": str(frame_path)},
        )
        assert ok
        xml = out.read_text()
        # frame は lane=2 (blur が lane=1 を取るため)
        assert 'lane="2"' in xml
        assert frame_path.name in xml

    def test_no_blur_keeps_frame_at_lane1(self, mock_video, tmp_path):
        """blur_overlays なしなら frame は従来通り lane=1。"""
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        frame_path = tmp_path / "frame.png"
        frame_path.write_bytes(b"\x89PNG\r\n")

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=10.0,
                timeline_start=0.0,
            ),
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            overlay_settings={"frame_path": str(frame_path)},
        )
        assert ok
        xml = out.read_text()
        assert 'lane="1"' in xml
        # title はないので lane=2 は出ない
        assert 'lane="2"' not in xml

    def test_blur_overlay_uses_video_scale_anchor(self, mock_video, tmp_path):
        """blur PNG には動画と同じ scale/anchor が適用される (アンカー/ズーム追従)。"""
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=5.0,
                timeline_start=0.0,
            ),
        ]
        blur_overlays = [
            {"png_path": str(mock_video["png"]), "start_sec": 0.0, "end_sec": 5.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            scale=(1.5, 1.5),
            anchor=(0.2, 0.3),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # blur PNG video 要素に scale="1.5 1.5" anchor="0.2 0.3" が含まれる
        # (動画 asset-clip と同じ値が適用されているはず)
        assert 'scale="1.5 1.5"' in xml
        assert 'anchor="0.2 0.3"' in xml
        # 少なくとも 2 箇所 (動画と blur) で出現するはず
        assert xml.count('scale="1.5 1.5"') >= 2
        assert xml.count('anchor="0.2 0.3"') >= 2

    def test_blur_overlay_spans_multiple_segments(self, mock_video, tmp_path):
        """time_ranges を跨ぐ blur overlay が segment ごとに分割される。"""
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        # 2 segments: [0-10] と [20-30]
        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=10.0,
                timeline_start=0.0,
            ),
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=20.0,
                end_time=30.0,
                timeline_start=10.0,
            ),
        ]
        # blur が両 segment を跨ぐ (5-25)
        blur_overlays = [
            {"png_path": str(mock_video["png"]), "start_sec": 5.0, "end_sec": 25.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # blur PNG が 2 つの video 要素として出現するはず
        # seg1 の overlap: source [5-10] → timeline [5-10] (5秒)
        # seg2 の overlap: source [20-25] → timeline [10-15] (5秒)
        assert xml.count('lane="1"') == 2

    def test_blur_overlay_uses_fit_conform(self, mock_video, tmp_path):
        """blur PNG は <adjust-conform type="fit"/> を使う (video と同じ).

        type="none" だと source ≠ timeline 解像度 (4K source / 縦動画) で
        アライメントがズレるため、video と同じ "fit" でなければならない.
        """
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=5.0,
                timeline_start=0.0,
            ),
        ]
        blur_overlays = [
            {"png_path": str(mock_video["png"]), "start_sec": 0.0, "end_sec": 5.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # blur PNG の <video> ブロックを抽出して conform を確認
        png_name = mock_video["png"].name
        # name=blur PNG name の <video> 要素 → 直後の <adjust-conform> は "fit"
        png_block_start = xml.find(f'name="{png_name}"')
        assert png_block_start > 0, "blur PNG video 要素が見つからない"
        # <video> の閉じ位置までを切り出して conform 種別を検証
        png_block_end = xml.find("</video>", png_block_start)
        block = xml[png_block_start:png_block_end]
        assert '<adjust-conform type="fit"/>' in block, (
            f"blur PNG は type='fit' であるべき (video と同じ). 実際の block:\n{block}"
        )
        assert '<adjust-conform type="none"/>' not in block

    def test_blur_overlay_outside_segments_not_registered(self, mock_video, tmp_path):
        """どの segment にも overlap しない blur overlay は asset として登録されない.

        無音削除で消えた範囲の blur overlay などは orphan asset になる前に除外する.
        """
        from config import Config
        from core.export import ExportSegment, FCPXMLExporter

        segments = [
            ExportSegment(
                source_path=str(mock_video["video"]),
                start_time=0.0,
                end_time=10.0,
                timeline_start=0.0,
            ),
        ]
        # blur が segment と全く重ならない (50-60s)
        orphan_png = tmp_path / "orphan.png"
        orphan_png.write_bytes(b"\x89PNG\r\n")
        valid_png = mock_video["png"]
        blur_overlays = [
            {"png_path": str(orphan_png), "start_sec": 50.0, "end_sec": 60.0},
            {"png_path": str(valid_png), "start_sec": 2.0, "end_sec": 8.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # orphan PNG は asset として登録されない
        assert "orphan.png" not in xml
        # 有効な PNG は登録されている
        assert valid_png.name in xml
        # video 要素は 1 つだけ
        assert xml.count('lane="1"') == 1

    def test_blur_overlay_with_nonstandard_resolution(self, tmp_path, monkeypatch):
        """source 解像度 ≠ timeline (例: 4K source on 1080p timeline) でも
        video と同じ conform="fit" + scale/anchor が適用されるため、
        blur PNG が timeline 上で video と同じ位置に配置される.
        """
        from unittest.mock import MagicMock

        from config import Config
        from core import export as export_mod
        from core.export import ExportSegment, FCPXMLExporter

        video_path = tmp_path / "source_4k.mp4"
        video_path.write_bytes(b"fake")
        png_path = tmp_path / "blur.png"
        png_path.write_bytes(b"\x89PNG\r\n")

        # 4K source を mock
        fake_info = MagicMock()
        fake_info.duration = 30.0
        fake_info.fps = 30
        fake_info.width = 3840
        fake_info.height = 2160
        monkeypatch.setattr(export_mod.VideoInfo, "from_file", lambda *a, **kw: fake_info)

        segments = [
            ExportSegment(
                source_path=str(video_path),
                start_time=0.0,
                end_time=10.0,
                timeline_start=0.0,
            ),
        ]
        blur_overlays = [
            {"png_path": str(png_path), "start_sec": 0.0, "end_sec": 10.0},
        ]
        out = tmp_path / "out.fcpxml"
        exporter = FCPXMLExporter(Config())
        ok = exporter.export(
            segments=segments,
            output_path=str(out),
            scale=(1.2, 1.2),
            anchor=(0.1, 0.2),
            blur_overlays=blur_overlays,
        )
        assert ok
        xml = out.read_text()
        # video asset-clip と blur PNG の両方で同じ scale/anchor + conform="fit"
        assert xml.count('scale="1.2 1.2"') >= 2
        assert xml.count('anchor="0.1 0.2"') >= 2
        # blur PNG ブロック内の conform は "fit"
        png_block_start = xml.find(f'name="{png_path.name}" ref=')
        png_block_end = xml.find("</video>", png_block_start)
        block = xml[png_block_start:png_block_end]
        assert '<adjust-conform type="fit"/>' in block
