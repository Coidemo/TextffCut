"""
バズクリップキャッシュ機能のテスト
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.presenters.buzz_clip import BuzzClipPresenter
from presentation.view_models.buzz_clip import BuzzClipViewModel


class TestBuzzClipCache:
    """バズクリップキャッシュ機能のテスト"""

    @pytest.fixture
    def presenter(self):
        """テスト用のPresenterを作成"""
        view_model = BuzzClipViewModel()
        use_case = MagicMock()
        return BuzzClipPresenter(view_model, use_case)

    def test_get_cache_path_structure(self, presenter):
        """キャッシュパスの構造をテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test_video.mp4"
            transcription_model = "medium"

            cache_path = presenter.get_cache_path(video_path, transcription_model)

            # 期待されるパス構造
            expected_path = Path(tmpdir) / "test_video_TextffCut" / "buzz_clips" / "medium.json"
            assert cache_path == expected_path

    def test_get_cache_path_default_model(self, presenter):
        """モデル名が指定されない場合のキャッシュパスをテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test_video.mp4"

            cache_path = presenter.get_cache_path(video_path, transcription_model=None)

            # デフォルトファイル名
            expected_path = Path(tmpdir) / "test_video_TextffCut" / "buzz_clips" / "default.json"
            assert cache_path == expected_path

    def test_save_and_load_cache(self, presenter):
        """キャッシュの保存と読み込みをテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test_video.mp4"
            transcription_model = "medium"

            # テスト用の候補を作成
            candidates = [
                BuzzClipCandidate(
                    id="1",
                    title="テスト候補1",
                    text="これはテストです",
                    start_time=10.0,
                    end_time=40.0,
                    duration=30.0,
                    score=0.9,
                    category="面白系",
                    reasoning="面白い内容",
                    keywords=["テスト", "面白い"],
                )
            ]

            # ViewModelに候補を設定
            presenter.view_model.candidates = candidates
            presenter.view_model.total_processing_time = 5.0
            presenter.view_model.model_used = "gpt-4o"
            presenter.view_model.token_usage = {"total_tokens": 1000}

            # キャッシュに保存
            presenter.save_to_cache(video_path, transcription_model)

            # キャッシュから読み込み
            loaded = presenter.load_from_cache(video_path, transcription_model)

            # 読み込み結果の確認
            assert loaded is True
            assert len(presenter.view_model.candidates) == 1
            assert presenter.view_model.candidates[0].title == "テスト候補1"
            assert presenter.view_model.model_used == "gpt-4o"

    def test_cache_directory_creation(self, presenter):
        """キャッシュディレクトリが自動作成されることをテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "videos" / "test_video.mp4"
            video_path.parent.mkdir(parents=True)

            # キャッシュパスを取得（この時点ではディレクトリは存在しない）
            cache_path = presenter.get_cache_path(video_path, "medium")
            assert not cache_path.parent.exists()

            # 候補を設定して保存
            presenter.view_model.candidates = [
                BuzzClipCandidate(
                    id="1",
                    title="テスト",
                    text="テスト",
                    start_time=0,
                    end_time=10,
                    duration=10,
                    score=0.5,
                    category="その他",
                    reasoning="テスト",
                    keywords=[],
                )
            ]

            presenter.save_to_cache(video_path, "medium")

            # ディレクトリとファイルが作成されたことを確認
            assert cache_path.parent.exists()
            assert cache_path.exists()

    def test_find_available_buzz_caches(self, presenter):
        """利用可能なバズクリップキャッシュの検索をテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test_video.mp4"

            # 複数のキャッシュファイルを作成
            cache_dir = Path(tmpdir) / "test_video_TextffCut" / "buzz_clips"
            cache_dir.mkdir(parents=True)

            # medium.json
            medium_cache = cache_dir / "medium.json"
            with open(medium_cache, "w") as f:
                json.dump({"version": "1.0", "results": {"candidates": []}}, f)

            # large.json
            large_cache = cache_dir / "large.json"
            with open(large_cache, "w") as f:
                json.dump({"version": "1.0", "results": {"candidates": []}}, f)

            # 検索
            caches = presenter._find_available_buzz_caches(video_path)

            # 2つのキャッシュが見つかることを確認
            assert len(caches) == 2
            cache_names = [c.name for c in caches]
            assert "medium.json" in cache_names
            assert "large.json" in cache_names

    def test_load_cache_with_auto_adjust(self, presenter):
        """パラメータ自動調整付きのキャッシュ読み込みをテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "test_video.mp4"

            # 異なるパラメータでキャッシュを作成
            cache_data = {
                "version": "1.0",
                "parameters": {
                    "num_candidates": 3,  # デフォルトは5
                    "min_duration": 20,  # デフォルトは30
                    "max_duration": 30,  # デフォルトは40
                    "selected_categories": ["面白系"],
                },
                "results": {"candidates": [], "total_processing_time": 1.0, "model_used": "gpt-4o", "token_usage": {}},
            }

            cache_path = presenter.get_cache_path(video_path, "medium")
            cache_path.parent.mkdir(parents=True)
            with open(cache_path, "w") as f:
                json.dump(cache_data, f)

            # auto_adjust=Trueで読み込み
            loaded = presenter.load_from_cache(video_path, "medium", auto_adjust_params=True)

            # パラメータが自動調整されたことを確認
            assert loaded is True
            assert presenter.view_model.num_candidates == 3
            assert presenter.view_model.min_duration == 20
            assert presenter.view_model.max_duration == 30
            assert presenter.view_model.selected_categories == ["面白系"]
