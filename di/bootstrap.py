"""
DIブートストラップ

アプリケーションの起動時にDIコンテナを初期化するためのユーティリティ。
"""

from di.config import DIConfig
from di.containers import ApplicationContainer, create_container
from utils.logging import get_logger

logger = get_logger(__name__)


def bootstrap_di(modules_to_wire: list[str] | None = None, config: DIConfig | None = None) -> ApplicationContainer:
    """
    DIコンテナをブートストラップ

    Args:
        modules_to_wire: ワイヤリングするモジュールのリスト
        config: DI設定

    Returns:
        初期化されたApplicationContainer
    """
    # デフォルトのワイヤリング対象
    if modules_to_wire is None:
        modules_to_wire = [
            "main",
            "presentation.presenters.main",
            "presentation.presenters.sidebar",
            "presentation.presenters.video_input",
            "presentation.presenters.transcription",
            "presentation.presenters.text_editor",
            "presentation.presenters.export_settings",
        ]

    # コンテナの作成
    container = create_container(config=config)

    # モジュールのワイヤリング
    try:
        container.wire(modules=modules_to_wire)
        logger.info(f"Wired modules: {modules_to_wire}")
    except Exception as e:
        logger.warning(f"Failed to wire some modules: {e}")

    return container


def inject_streamlit_session(container: ApplicationContainer) -> None:
    """
    Streamlitセッション状態をコンテナに注入

    Args:
        container: ApplicationContainer
    """
    try:
        import streamlit as st

        # セッション状態から設定を更新
        if hasattr(st, "session_state"):
            container.config().update_from_streamlit_session(dict(st.session_state))
            logger.debug("Updated DI config from Streamlit session state")

    except ImportError:
        logger.debug("Streamlit not available, skipping session injection")


def create_test_container() -> ApplicationContainer:
    """
    テスト用のコンテナを作成

    Returns:
        テスト用に設定されたApplicationContainer
    """
    test_config = DIConfig(environment="test", is_testing=True)

    container = create_container(config=test_config)

    # テスト用のモジュールをワイヤリング
    test_modules = [
        "tests.di.test_containers",
        "tests.adapters.gateways",
        "tests.use_cases",
    ]

    try:
        container.wire(modules=test_modules)
    except Exception as e:
        logger.warning(f"Failed to wire test modules: {e}")

    return container


def create_worker_container(worker_config: dict) -> ApplicationContainer:
    """
    ワーカープロセス用のコンテナを作成

    Args:
        worker_config: ワーカー設定の辞書

    Returns:
        ワーカー用に設定されたApplicationContainer
    """
    # ワーカー設定からDIConfigを作成
    di_config = DIConfig.from_dict(worker_config)
    di_config.container_config["auto_wire"] = False  # ワーカーでは自動ワイヤリングを無効化

    container = create_container(config=di_config)

    # ワーカー固有のモジュールをワイヤリング
    worker_modules = [
        "worker_transcribe",
        "worker_transcribe_v2",
    ]

    try:
        container.wire(modules=worker_modules)
    except Exception as e:
        logger.warning(f"Failed to wire worker modules: {e}")

    return container


# 使用例とドキュメント
if __name__ == "__main__":
    """
    DIコンテナの使用例
    """

    # 1. 基本的な使用方法
    print("=== Basic Usage ===")
    container = bootstrap_di()

    # ゲートウェイの取得
    file_gateway = container.gateways.file_gateway()
    print(f"File Gateway: {file_gateway}")

    # ユースケースの取得
    transcribe_use_case = container.use_cases.transcribe_video()
    print(f"Transcribe Use Case: {transcribe_use_case}")

    # サービスの取得（レガシー互換）
    config_service = container.services.configuration_service()
    print(f"Configuration Service: {config_service}")

    # 2. 依存性注入の例
    print("\n=== Dependency Injection Example ===")
    from dependency_injector.wiring import Provide, inject

    @inject
    def example_function(file_gateway=Provide[ApplicationContainer.gateways.file_gateway]):
        """依存性注入を使用する関数の例"""
        print(f"Injected File Gateway: {file_gateway}")
        return file_gateway

    # コンテナからの自動注入
    result = example_function()

    # 3. テストでの使用例
    print("\n=== Test Usage ===")
    test_container = create_test_container()
    print(f"Test Container Config: {test_container.config().to_dict()}")

    # 4. 設定の動的更新
    print("\n=== Dynamic Config Update ===")
    original_env = container.config().environment
    print(f"Original Environment: {original_env}")

    # Streamlitセッション状態のシミュレーション
    mock_session_state = {"api_key": "new-test-key", "model_size": "small"}
    container.config().update_from_streamlit_session(mock_session_state)
    print(f"Updated API Key: {container.config().legacy_config.api_key}")
    print(f"Updated Model Size: {container.config().legacy_config.model_size}")

    # クリーンアップ
    container.shutdown_resources()
    test_container.shutdown_resources()
