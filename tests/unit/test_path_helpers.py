"""
パスヘルパー関数のユニットテスト
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.path_helpers import get_display_path, get_relative_path, ensure_absolute_path


class TestGetDisplayPath:
    """get_display_path関数のテスト"""
    
    @patch('utils.path_helpers.IS_DOCKER', False)
    def test_local_environment(self):
        """ローカル環境では入力パスがそのまま返される"""
        test_path = "/Users/test/project/videos/sample.mp4"
        result = get_display_path(test_path)
        assert result == test_path
    
    @patch('utils.path_helpers.IS_DOCKER', True)
    @patch('utils.path_helpers.VIDEOS_DIR', '/app/videos')
    @patch.dict(os.environ, {'HOST_VIDEOS_PATH': '/Users/test/project/videos'})
    def test_docker_environment_with_videos_path(self):
        """Docker環境でVIDEOS_DIR内のパスはホストパスに変換される"""
        test_path = "/app/videos/sample.mp4"
        result = get_display_path(test_path)
        assert result == "/Users/test/project/videos/sample.mp4"
    
    @patch('utils.path_helpers.IS_DOCKER', True)
    @patch('utils.path_helpers.VIDEOS_DIR', '/app/videos')
    def test_docker_environment_outside_videos_dir(self):
        """Docker環境でVIDEOS_DIR外のパスはそのまま返される"""
        test_path = "/app/other/sample.mp4"
        result = get_display_path(test_path)
        assert result == test_path
    
    @patch('utils.path_helpers.IS_DOCKER', True)
    @patch('utils.path_helpers.VIDEOS_DIR', '/app/videos')
    @patch.dict(os.environ, {}, clear=True)
    def test_docker_environment_without_host_path(self):
        """Docker環境でHOST_VIDEOS_PATHが未設定の場合のフォールバック"""
        with patch.dict(os.environ, {'PWD': '/home/user/project'}):
            test_path = "/app/videos/sample.mp4"
            result = get_display_path(test_path)
            assert result == "/home/user/project/videos/sample.mp4"


class TestGetRelativePath:
    """get_relative_path関数のテスト"""
    
    def test_relative_path_within_base(self):
        """基準ディレクトリ内のパスは相対パスに変換される"""
        file_path = "/app/videos/subfolder/sample.mp4"
        base_path = "/app/videos"
        result = get_relative_path(file_path, base_path)
        assert result == "subfolder/sample.mp4"
    
    def test_relative_path_outside_base(self):
        """基準ディレクトリ外のパスは元のパスが返される"""
        file_path = "/other/folder/sample.mp4"
        base_path = "/app/videos"
        result = get_relative_path(file_path, base_path)
        assert result == "/other/folder/sample.mp4"
    
    @patch('utils.path_helpers.VIDEOS_DIR', '/default/videos')
    def test_default_base_path(self):
        """base_pathが指定されない場合はVIDEOS_DIRが使用される"""
        file_path = "/default/videos/sample.mp4"
        result = get_relative_path(file_path)
        assert result == "sample.mp4"


class TestEnsureAbsolutePath:
    """ensure_absolute_path関数のテスト"""
    
    @patch('utils.path_helpers.IS_DOCKER', False)
    def test_absolute_path_unchanged(self):
        """絶対パスはそのまま返される"""
        test_path = "/Users/test/file.mp4"
        result = ensure_absolute_path(test_path)
        assert result == Path(test_path)
    
    @patch('utils.path_helpers.IS_DOCKER', True)
    def test_relative_path_docker(self):
        """Docker環境での相対パスは/appを基準に変換される"""
        test_path = "videos/file.mp4"
        result = ensure_absolute_path(test_path)
        assert result == Path("/app/videos/file.mp4")
    
    @patch('utils.path_helpers.IS_DOCKER', False)
    def test_relative_path_local(self):
        """ローカル環境での相対パスは現在のディレクトリを基準に変換される"""
        test_path = "videos/file.mp4"
        result = ensure_absolute_path(test_path)
        # resolve()の結果は環境依存なので、絶対パスであることだけを確認
        assert result.is_absolute()