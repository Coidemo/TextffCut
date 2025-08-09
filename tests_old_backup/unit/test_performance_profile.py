"""
パフォーマンスプロファイルのユニットテスト
"""

import pytest
from datetime import datetime
from pathlib import Path
import json
import tempfile

from domain.entities.performance_profile import PerformanceProfile, PerformanceMetrics
from infrastructure.repositories.performance_profile_repository import FilePerformanceProfileRepository


class TestPerformanceProfile:
    """PerformanceProfileエンティティのテスト"""
    
    def test_default_values(self):
        """デフォルト値のテスト"""
        profile = PerformanceProfile()
        
        assert profile.optimization_preference == "auto"
        assert profile.batch_size is None
        assert profile.compute_type is None
        assert profile.max_conversion_time == 300
        assert profile.min_memory_threshold_gb == 4.0
        assert len(profile.metrics_history) == 0
    
    def test_add_metrics(self):
        """メトリクス追加のテスト"""
        profile = PerformanceProfile()
        
        # メトリクスを追加
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            success=True,
            processing_time=120.5,
            optimization_info={'reduced': True}
        )
        profile.add_metrics(metrics)
        
        assert len(profile.metrics_history) == 1
        assert profile.metrics_history[0] == metrics
    
    def test_metrics_history_limit(self):
        """メトリクス履歴の上限テスト"""
        profile = PerformanceProfile()
        
        # 25個のメトリクスを追加
        for i in range(25):
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                success=True,
                processing_time=float(i)
            )
            profile.add_metrics(metrics)
        
        # 最新20件のみ保持されることを確認
        assert len(profile.metrics_history) == 20
        # 最も古いメトリクスの処理時間は5.0
        assert profile.metrics_history[0].processing_time == 5.0
        # 最新のメトリクスの処理時間は24.0
        assert profile.metrics_history[-1].processing_time == 24.0
    
    def test_get_effective_batch_size(self):
        """実効バッチサイズ取得のテスト"""
        profile = PerformanceProfile()
        
        # デフォルト値
        assert profile.get_effective_batch_size() == 8
        
        # カスタム値
        profile.batch_size = 4
        assert profile.get_effective_batch_size() == 4
        
        # エラー履歴がある場合
        for _ in range(3):
            profile.add_metrics(PerformanceMetrics(
                timestamp=datetime.now(),
                success=False,
                processing_time=0,
                error_message="Memory error"
            ))
        # エラーが多い場合は小さい値を返す
        assert profile.get_effective_batch_size() == 2
    
    def test_get_effective_compute_type(self):
        """実効compute_type取得のテスト"""
        profile = PerformanceProfile()
        
        # デフォルト値
        assert profile.get_effective_compute_type() == "int8"
        
        # カスタム値
        profile.compute_type = "float16"
        assert profile.get_effective_compute_type() == "float16"
        
        # メモリエラーがある場合
        profile.add_metrics(PerformanceMetrics(
            timestamp=datetime.now(),
            success=False,
            processing_time=0,
            error_message="OutOfMemoryError"
        ))
        # メモリエラーがある場合は常にint8
        assert profile.get_effective_compute_type() == "int8"
    
    def test_update_from_metrics(self):
        """メトリクスに基づく自動更新のテスト"""
        profile = PerformanceProfile()
        profile.batch_size = 8
        
        # 連続してメモリエラーを追加
        for _ in range(2):
            profile.add_metrics(PerformanceMetrics(
                timestamp=datetime.now(),
                success=False,
                processing_time=0,
                error_message="GPU memory error"
            ))
        
        profile.update_from_metrics()
        
        # バッチサイズが減少し、最適化が有効になることを確認
        assert profile.batch_size == 4
        assert profile.optimization_preference == "always"


class TestFilePerformanceProfileRepository:
    """FilePerformanceProfileRepositoryのテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)
    
    @pytest.fixture
    def repository(self, temp_dir):
        """テスト用リポジトリ"""
        return FilePerformanceProfileRepository(base_dir=temp_dir)
    
    def test_save_and_load(self, repository):
        """保存と読み込みのテスト"""
        # プロファイルを作成
        profile = PerformanceProfile(
            optimization_preference="always",
            batch_size=4,
            compute_type="float16"
        )
        profile.add_metrics(PerformanceMetrics(
            timestamp=datetime.now(),
            success=True,
            processing_time=100.0
        ))
        
        # 保存
        repository.save(profile)
        
        # 読み込み
        loaded = repository.load()
        
        # 検証
        assert loaded is not None
        assert loaded.optimization_preference == "always"
        assert loaded.batch_size == 4
        assert loaded.compute_type == "float16"
        assert len(loaded.metrics_history) == 1
    
    def test_load_nonexistent(self, repository):
        """存在しないファイルの読み込みテスト"""
        loaded = repository.load()
        assert loaded is None
    
    def test_get_default(self, repository):
        """デフォルトプロファイル取得のテスト"""
        default = repository.get_default()
        
        assert default.optimization_preference == "auto"
        assert default.batch_size is None
        assert default.compute_type is None