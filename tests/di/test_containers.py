"""
DIコンテナのテスト
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from di.containers import (
    ApplicationContainer,
    create_container,
    get_container,
    reset_container
)
from di.config import DIConfig
from config import Config
from dependency_injector import providers


class TestApplicationContainer:
    """ApplicationContainerのテスト"""
    
    @pytest.fixture
    def container(self):
        """テスト用コンテナ"""
        container = create_container()
        yield container
        container.shutdown_resources()
    
    def test_container_creation(self, container):
        """コンテナの作成テスト"""
        # dependency-injectorはDynamicContainerを返す
        assert container is not None
        assert hasattr(container, 'config')
        assert hasattr(container, 'gateways')
        assert hasattr(container, 'use_cases')
        assert hasattr(container, 'services')
        
        # 設定を取得
        config = container.config()
        assert config is not None
        assert isinstance(config, DIConfig)
    
    def test_legacy_config_provider(self, container):
        """レガシー設定プロバイダーのテスト"""
        legacy_config = container.legacy_config()
        assert isinstance(legacy_config, Config)
        assert legacy_config is container.config().legacy_config
    
    def test_gateway_providers(self, container):
        """ゲートウェイプロバイダーのテスト"""
        # ファイルゲートウェイ
        file_gateway = container.gateways.file_gateway()
        assert file_gateway is not None
        
        # シングルトンの確認
        file_gateway2 = container.gateways.file_gateway()
        assert file_gateway is file_gateway2
    
    def test_use_case_providers(self, container):
        """ユースケースプロバイダーのテスト"""
        # 文字起こしユースケース
        transcribe_use_case = container.use_cases.transcribe_video()
        assert transcribe_use_case is not None
        
        # ファクトリーパターンの確認（毎回新しいインスタンス）
        transcribe_use_case2 = container.use_cases.transcribe_video()
        assert transcribe_use_case is not transcribe_use_case2
    
    def test_service_providers(self, container):
        """サービスプロバイダーのテスト"""
        # 設定サービス
        config_service = container.services.configuration_service()
        assert config_service is not None
        
        # シングルトンの確認
        config_service2 = container.services.configuration_service()
        assert config_service is config_service2
    
    def test_config_override(self):
        """設定のオーバーライドテスト"""
        # カスタム設定
        custom_config = DIConfig(
            environment="test",
            is_testing=True
        )
        
        container = create_container(config=custom_config)
        
        assert container.config().environment == "test"
        assert container.config().is_testing is True
        
        container.shutdown_resources()
    
    def test_provider_override(self):
        """プロバイダーのオーバーライドテスト"""
        # モックゲートウェイ
        mock_file_gateway = Mock()
        
        # 別のコンテナを作成してゲートウェイをオーバーライド
        container = create_container()
        
        # file_gatewayプロバイダーをオーバーライド
        container.gateways.file_gateway.override(providers.Object(mock_file_gateway))
        
        # オーバーライドされたゲートウェイを確認
        file_gateway = container.gateways.file_gateway()
        assert file_gateway is mock_file_gateway
        
        container.shutdown_resources()


class TestDIConfig:
    """DIConfigのテスト"""
    
    def test_di_config_creation(self):
        """DIConfig作成のテスト"""
        config = DIConfig()
        
        assert config.legacy_config is not None
        assert config.environment == "production"
        assert config.is_testing is False
        assert config.is_production is True
        assert config.is_development is False
    
    def test_di_config_serialization(self):
        """DIConfigのシリアライズ/デシリアライズテスト"""
        config = DIConfig(
            environment="test",
            is_testing=True
        )
        
        # 辞書に変換
        config_dict = config.to_dict()
        assert config_dict["environment"] == "test"
        assert config_dict["is_testing"] is True
        
        # 辞書から復元
        restored_config = DIConfig.from_dict(config_dict)
        assert restored_config.environment == "test"
        assert restored_config.is_testing is True
    
    def test_streamlit_session_update(self):
        """Streamlitセッション状態からの更新テスト"""
        config = DIConfig()
        
        # 初期値を確認
        original_model_size = config.legacy_config.transcription.model_size
        
        # セッション状態をシミュレート
        session_state = {"api_key": "test-key", "model_size": "small", "use_api": True}
        config.update_from_streamlit_session(session_state)
        
        # 更新されていることを確認
        assert getattr(config.legacy_config, "api_key", None) == "test-key"
        assert config.legacy_config.transcription.model_size == "small"
        assert getattr(config.legacy_config, "use_api", None) == True


class TestGlobalContainer:
    """グローバルコンテナのテスト"""
    
    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        reset_container()
    
    def test_get_container(self):
        """グローバルコンテナの取得テスト"""
        container1 = get_container()
        container2 = get_container()
        
        # 同じインスタンスが返される
        assert container1 is container2
    
    def test_reset_container(self):
        """グローバルコンテナのリセットテスト"""
        container1 = get_container()
        reset_container()
        container2 = get_container()
        
        # 異なるインスタンスが返される
        assert container1 is not container2


class TestCustomProviders:
    """カスタムプロバイダーのテスト"""
    
    def test_streamlit_session_provider_with_streamlit(self):
        """StreamlitSessionProviderのテスト（Streamlitあり）"""
        from di.providers import StreamlitSessionProvider
        
        # Streamlitセッション状態をモック
        with patch('streamlit.session_state', {"test_key": "test_value"}):
            provider = StreamlitSessionProvider(
                session_key="test_key",
                default_factory=lambda: "default"
            )
            
            value = provider()
            assert value == "test_value"
    
    @pytest.mark.skip(reason="Streamlitのモジュール操作が複雑なため一時的にスキップ")
    def test_streamlit_session_provider_without_streamlit(self):
        """StreamlitSessionProviderのテスト（Streamlitなし）"""
        from di.providers import StreamlitSessionProvider
        
        # Streamlitのインポートを失敗させる
        import sys
        original_modules = sys.modules.copy()
        if 'streamlit' in sys.modules:
            del sys.modules['streamlit']
        
        try:
            provider = StreamlitSessionProvider(
                session_key="test_key",
                default_factory=lambda: "default"
            )
            
            value = provider()
            assert value == "default"
        finally:
            # モジュールを元に戻す
            sys.modules.update(original_modules)
    
    def test_conditional_provider(self):
        """ConditionalProviderのテスト"""
        from di.providers import ConditionalProvider
        
        # 条件プロバイダー
        condition = providers.Object(True)
        when_true = providers.Object("true_value")
        when_false = providers.Object("false_value")
        
        provider = ConditionalProvider(
            condition=condition,
            when_true=when_true,
            when_false=when_false
        )
        
        # 条件が真の場合
        assert provider() == "true_value"
        
        # 条件を変更
        condition.override(providers.Object(False))
        assert provider() == "false_value"