"""
E2Eテストの共通設定
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def test_data_dir():
    """テストデータディレクトリ"""
    return Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def sample_video_path(test_data_dir):
    """サンプル動画のパス"""
    # 実際のテストでは適切なサンプル動画を配置
    return test_data_dir / "sample.mp4"


def pytest_configure(config):
    """pytest設定"""
    config.addinivalue_line("markers", "e2e: E2E tests that require browser automation")


# Playwrightの設定は自動的に読み込まれるため、明示的な指定は不要
