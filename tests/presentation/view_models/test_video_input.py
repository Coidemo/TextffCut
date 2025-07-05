"""
VideoInputViewModelのテスト
"""

from unittest.mock import Mock

import pytest

from presentation.view_models.video_input import VideoInfo, VideoInputViewModel


class TestVideoInfo:
    """VideoInfoのテスト"""

    def test_to_dict(self):
        """辞書変換のテスト"""
        info = VideoInfo(
            duration=120.5, fps=30.0, width=1920, height=1080, codec="h264", file_size=1024 * 1024 * 100  # 100MB
        )

        result = info.to_dict()

        assert result["duration"] == 120.5
        assert result["fps"] == 30.0
        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["codec"] == "h264"
        assert result["file_size"] == 1024 * 1024 * 100

    def test_from_dict(self):
        """辞書からの作成テスト"""
        data = {
            "duration": 60.0,
            "fps": 24.0,
            "width": 1280,
            "height": 720,
            "codec": "h265",
            "file_size": 1024 * 1024 * 50,
        }

        info = VideoInfo.from_dict(data)

        assert info.duration == 60.0
        assert info.fps == 24.0
        assert info.width == 1280
        assert info.height == 720
        assert info.codec == "h265"
        assert info.file_size == 1024 * 1024 * 50


class TestVideoInputViewModel:
    """VideoInputViewModelのテスト"""

    @pytest.fixture
    def view_model(self):
        """テスト用のViewModel"""
        return VideoInputViewModel()

    def test_initial_state(self, view_model):
        """初期状態のテスト"""
        assert view_model.selected_file is None
        assert view_model.video_files == []
        assert view_model.video_info is None
        assert not view_model.is_loading
        assert not view_model.is_refreshing
        assert view_model.error_message is None

    def test_to_dict(self, view_model):
        """辞書変換のテスト"""
        view_model.selected_file = "test.mp4"
        view_model.video_files = ["test.mp4", "sample.avi"]
        view_model.is_loading = True

        result = view_model.to_dict()

        assert result["selected_file"] == "test.mp4"
        assert result["video_files"] == ["test.mp4", "sample.avi"]
        assert result["is_loading"] is True
        assert result["video_info"] is None

    def test_validate_success(self, view_model):
        """検証成功のテスト"""
        view_model.video_files = ["test.mp4"]
        view_model.selected_file = "test.mp4"
        view_model.video_info = VideoInfo(
            duration=60.0, fps=30.0, width=1920, height=1080, codec="h264", file_size=1024 * 1024
        )

        assert view_model.validate() is None

    def test_validate_file_not_in_list(self, view_model):
        """選択ファイルがリストにない場合の検証テスト"""
        view_model.video_files = ["test.mp4"]
        view_model.selected_file = "missing.mp4"

        error = view_model.validate()
        assert error is not None
        assert "missing.mp4" in error

    def test_validate_invalid_duration(self, view_model):
        """無効な動画長の検証テスト"""
        view_model.video_files = ["test.mp4"]
        view_model.selected_file = "test.mp4"
        view_model.video_info = VideoInfo(
            duration=0.0, fps=30.0, width=1920, height=1080, codec="h264", file_size=1024 * 1024
        )

        error = view_model.validate()
        assert error is not None
        assert "動画の長さ" in error

    def test_clear_selection(self, view_model):
        """選択クリアのテスト"""
        # 選択状態を設定
        view_model.selected_file = "test.mp4"
        view_model.video_info = VideoInfo(
            duration=60.0, fps=30.0, width=1920, height=1080, codec="h264", file_size=1024 * 1024
        )
        view_model.error_message = "Some error"

        # オブザーバーを設定
        observer = Mock()
        view_model.subscribe(observer)

        # クリア
        view_model.clear_selection()

        # 状態確認
        assert view_model.selected_file is None
        assert view_model.video_info is None
        assert view_model.error_message is None

        # 通知確認
        observer.update.assert_called_once_with(view_model)

    def test_set_error(self, view_model):
        """エラー設定のテスト"""
        view_model.is_loading = True

        observer = Mock()
        view_model.subscribe(observer)

        view_model.set_error("Test error", {"code": 123})

        assert view_model.error_message == "Test error"
        assert view_model.error_details == {"code": 123}
        assert not view_model.is_loading
        observer.update.assert_called_once()

    def test_duration_text(self, view_model):
        """動画長テキストのテスト"""
        # 時間なし
        assert view_model.duration_text == "不明"

        # 秒のみ
        view_model.video_info = VideoInfo(duration=45, fps=30, width=1920, height=1080, codec="h264", file_size=1024)
        assert view_model.duration_text == "45秒"

        # 分秒
        view_model.video_info.duration = 125
        assert view_model.duration_text == "2分5秒"

        # 時分秒
        view_model.video_info.duration = 3665
        assert view_model.duration_text == "1時間1分5秒"

    def test_file_size_text(self, view_model):
        """ファイルサイズテキストのテスト"""
        # サイズなし
        assert view_model.file_size_text == "不明"

        # バイト
        view_model.video_info = VideoInfo(duration=60, fps=30, width=1920, height=1080, codec="h264", file_size=500)
        assert view_model.file_size_text == "500 B"

        # KB
        view_model.video_info.file_size = 1024 * 5
        assert view_model.file_size_text == "5.0 KB"

        # MB
        view_model.video_info.file_size = 1024 * 1024 * 10
        assert view_model.file_size_text == "10.0 MB"

        # GB
        view_model.video_info.file_size = 1024 * 1024 * 1024 * 2
        assert view_model.file_size_text == "2.0 GB"

    def test_properties(self, view_model):
        """プロパティのテスト"""
        # 初期状態
        assert not view_model.has_selection
        assert not view_model.is_ready

        # ファイル選択のみ
        view_model.selected_file = "test.mp4"
        assert view_model.has_selection
        assert not view_model.is_ready

        # 情報も設定
        view_model.video_info = VideoInfo(duration=60, fps=30, width=1920, height=1080, codec="h264", file_size=1024)
        assert view_model.has_selection
        assert view_model.is_ready

        # ローディング中
        view_model.is_loading = True
        assert not view_model.is_ready
