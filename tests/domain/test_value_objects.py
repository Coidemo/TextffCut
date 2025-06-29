"""
値オブジェクトのテスト
"""

import pytest
import os
from pathlib import Path

from domain.value_objects import TimeRange, FilePath, Duration


class TestTimeRange:
    """TimeRange値オブジェクトのテスト"""
    
    def test_create_valid_range(self):
        """正常な時間範囲の作成"""
        tr = TimeRange(start=0.0, end=5.0)
        assert tr.start == 0.0
        assert tr.end == 5.0
        assert tr.duration == 5.0
        assert not tr.is_empty
    
    def test_invalid_negative_start(self):
        """負の開始時間でエラー"""
        with pytest.raises(ValueError, match="Start time cannot be negative"):
            TimeRange(start=-1.0, end=5.0)
    
    def test_invalid_end_before_start(self):
        """終了時間が開始時間より前でエラー"""
        with pytest.raises(ValueError, match="End time must be greater than or equal to start time"):
            TimeRange(start=5.0, end=3.0)
    
    def test_empty_range(self):
        """空の範囲"""
        tr = TimeRange(start=5.0, end=5.0)
        assert tr.is_empty
        assert tr.duration == 0.0
    
    def test_contains(self):
        """時刻の包含チェック"""
        tr = TimeRange(start=1.0, end=5.0)
        assert tr.contains(3.0)
        assert tr.contains(1.0)  # 境界を含む
        assert tr.contains(5.0)  # 境界を含む
        assert not tr.contains(0.5)
        assert not tr.contains(5.5)
    
    def test_overlaps(self):
        """重なりチェック"""
        tr1 = TimeRange(start=1.0, end=5.0)
        tr2 = TimeRange(start=3.0, end=7.0)
        tr3 = TimeRange(start=6.0, end=8.0)
        
        assert tr1.overlaps(tr2)
        assert tr2.overlaps(tr1)  # 対称性
        assert not tr1.overlaps(tr3)
    
    def test_intersection(self):
        """交差部分の取得"""
        tr1 = TimeRange(start=1.0, end=5.0)
        tr2 = TimeRange(start=3.0, end=7.0)
        
        intersection = tr1.intersection(tr2)
        assert intersection is not None
        assert intersection.start == 3.0
        assert intersection.end == 5.0
        
        # 重ならない場合
        tr3 = TimeRange(start=6.0, end=8.0)
        assert tr1.intersection(tr3) is None
    
    def test_merge_ranges(self):
        """範囲のマージ"""
        ranges = [
            TimeRange(start=0.0, end=2.0),
            TimeRange(start=1.5, end=3.0),  # 重なり
            TimeRange(start=3.1, end=4.0),  # 隣接（閾値内）
            TimeRange(start=5.0, end=6.0)   # 離れている
        ]
        
        merged = TimeRange.merge_ranges(ranges, gap_threshold=0.2)
        assert len(merged) == 2
        assert merged[0].start == 0.0
        assert merged[0].end == 4.0
        assert merged[1].start == 5.0
        assert merged[1].end == 6.0
    
    def test_immutability(self):
        """不変性のテスト"""
        tr = TimeRange(start=0.0, end=5.0)
        with pytest.raises(AttributeError):
            tr.start = 1.0


class TestFilePath:
    """FilePath値オブジェクトのテスト"""
    
    def test_create_valid_path(self):
        """正常なパスの作成"""
        fp = FilePath("/path/to/file.txt")
        assert fp.path == os.path.normpath("/path/to/file.txt")
        assert fp.name == "file.txt"
        assert fp.stem == "file"
        assert fp.extension == ".txt"
    
    def test_empty_path_error(self):
        """空のパスでエラー"""
        with pytest.raises(ValueError, match="File path cannot be empty"):
            FilePath("")
    
    def test_path_operations(self):
        """パス操作"""
        fp = FilePath("/path/to/file.txt")
        
        # 拡張子変更
        new_fp = fp.with_suffix(".mp4")
        assert new_fp.extension == ".mp4"
        assert new_fp.name == "file.mp4"
        
        # ファイル名変更
        new_fp2 = fp.with_name("newfile.txt")
        assert new_fp2.name == "newfile.txt"
        
        # パス結合
        fp_dir = FilePath("/path/to")
        joined = fp_dir.join("subdir", "file.txt")
        assert joined.name == "file.txt"
    
    def test_validate_extension(self):
        """拡張子の検証"""
        fp = FilePath("/path/to/video.mp4")
        
        assert fp.validate_extension([".mp4", ".avi", ".mov"])
        assert fp.validate_extension(["mp4", "avi", "mov"])  # ドットなしでも可
        assert not fp.validate_extension([".txt", ".doc"])
    
    def test_immutability(self):
        """不変性のテスト"""
        fp = FilePath("/path/to/file.txt")
        with pytest.raises(AttributeError):
            fp.path = "/new/path"


class TestDuration:
    """Duration値オブジェクトのテスト"""
    
    def test_create_valid_duration(self):
        """正常な時間長の作成"""
        d = Duration(seconds=90.5)
        assert d.seconds == 90.5
        assert d.minutes == pytest.approx(1.508333, rel=1e-5)
        assert d.hours == pytest.approx(0.025139, rel=1e-5)
        assert d.milliseconds == 90500
    
    def test_negative_duration_error(self):
        """負の時間長でエラー"""
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            Duration(seconds=-1.0)
    
    def test_arithmetic_operations(self):
        """算術演算"""
        d1 = Duration(seconds=10.0)
        d2 = Duration(seconds=5.0)
        
        # 加算
        d3 = d1 + d2
        assert d3.seconds == 15.0
        
        # 減算
        d4 = d1 - d2
        assert d4.seconds == 5.0
        
        # 負の結果は0になる
        d5 = d2 - d1
        assert d5.seconds == 0.0
        
        # 乗算
        d6 = d1 * 2
        assert d6.seconds == 20.0
        
        # 除算
        d7 = d1 / 2
        assert d7.seconds == 5.0
    
    def test_comparisons(self):
        """比較演算"""
        d1 = Duration(seconds=10.0)
        d2 = Duration(seconds=5.0)
        d3 = Duration(seconds=10.0)
        
        assert d1 > d2
        assert d2 < d1
        assert d1 >= d3
        assert d1 <= d3
        assert d1 == d3
        assert d1 != d2
    
    def test_to_timecode(self):
        """タイムコードへの変換"""
        d = Duration(seconds=3661.5)  # 1時間1分1.5秒
        
        # 通常のタイムコード（30fps）
        tc = d.to_timecode(fps=30.0)
        assert tc == "01:01:01:15"
        
        # SRTタイムコード
        srt_tc = d.to_srt_timecode()
        assert srt_tc == "01:01:01,500"
    
    def test_to_human_readable(self):
        """人間が読みやすい形式への変換"""
        assert Duration(seconds=0.5).to_human_readable() == "500ms"
        assert Duration(seconds=45.2).to_human_readable() == "45.2s"
        assert Duration(seconds=125.7).to_human_readable() == "2m 5.7s"
        assert Duration(seconds=3725.3).to_human_readable() == "1h 2m 5.3s"
    
    def test_from_various_units(self):
        """様々な単位からの作成"""
        assert Duration.from_milliseconds(1500).seconds == 1.5
        assert Duration.from_minutes(2.5).seconds == 150.0
        assert Duration.from_hours(0.5).seconds == 1800.0
    
    def test_immutability(self):
        """不変性のテスト"""
        d = Duration(seconds=10.0)
        with pytest.raises(AttributeError):
            d.seconds = 20.0