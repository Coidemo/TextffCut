"""
設定ヘルパー関数のユニットテスト
"""

from unittest.mock import patch, Mock

import pytest

from utils.config_helpers import (
    get_ui_page_title,
    get_ui_layout,
    get_whisper_models,
    get_api_models,
    is_api_mode,
    get_default_model_size,
    get_config_service,
    get_isolation_mode,
    set_api_mode
)


class TestConfigHelpers:
    """設定ヘルパー関数のテスト"""
    
    @patch('utils.config_helpers.config')
    def test_get_ui_page_title(self, mock_config):
        """UIページタイトルの取得"""
        mock_config.ui.page_title = "TextffCut - テスト"
        
        result = get_ui_page_title()
        
        assert result == "TextffCut - テスト"
    
    @patch('utils.config_helpers.config')
    def test_get_ui_layout(self, mock_config):
        """UIレイアウトの取得"""
        mock_config.ui.layout = "wide"
        
        result = get_ui_layout()
        
        assert result == "wide"
    
    @patch('utils.config_helpers.config')
    def test_get_whisper_models(self, mock_config):
        """Whisperモデルリストの取得"""
        mock_models = ["small", "medium", "large"]
        mock_config.transcription.whisper_models = mock_models
        
        result = get_whisper_models()
        
        assert result == mock_models
    
    @patch('utils.config_helpers.config')
    def test_get_api_models(self, mock_config):
        """APIモデルリストの取得"""
        mock_models = ["whisper-1"]
        mock_config.transcription.api_models = mock_models
        
        result = get_api_models()
        
        assert result == mock_models
    
    @patch('utils.config_helpers.config')
    def test_is_api_mode_true(self, mock_config):
        """APIモードがTrueの場合"""
        mock_config.transcription.use_api = True
        
        result = is_api_mode()
        
        assert result is True
    
    @patch('utils.config_helpers.config')
    def test_is_api_mode_false(self, mock_config):
        """APIモードがFalseの場合"""
        mock_config.transcription.use_api = False
        
        result = is_api_mode()
        
        assert result is False
    
    @patch('utils.config_helpers.config')
    def test_get_default_model_size(self, mock_config):
        """デフォルトモデルサイズの取得"""
        mock_config.transcription.model_size = "large-v3"
        
        result = get_default_model_size()
        
        assert result == "large-v3"
    
    @patch('utils.config_helpers.config')
    def test_get_isolation_mode(self, mock_config):
        """分離モードの取得"""
        mock_config.transcription.isolation_mode = "subprocess"
        
        result = get_isolation_mode()
        
        assert result == "subprocess"
    
    @patch('utils.config_helpers.config')
    def test_set_api_mode_enabled(self, mock_config):
        """APIモードを有効にする"""
        set_api_mode(True, "test-api-key")
        
        assert mock_config.transcription.use_api is True
        assert mock_config.transcription.api_key == "test-api-key"
    
    @patch('utils.config_helpers.config')
    def test_set_api_mode_disabled(self, mock_config):
        """APIモードを無効にする"""
        set_api_mode(False)
        
        assert mock_config.transcription.use_api is False
        assert mock_config.transcription.api_key is None


class TestConfigServiceSingleton:
    """ConfigurationServiceシングルトンのテスト"""
    
    @patch('utils.config_helpers._config_service', None)
    @patch('utils.config_helpers.ConfigurationService')
    @patch('utils.config_helpers.config')
    def test_get_config_service_creates_instance(self, mock_config, mock_service_class):
        """初回呼び出し時にインスタンスを作成"""
        mock_instance = Mock()
        mock_service_class.return_value = mock_instance
        
        result = get_config_service()
        
        mock_service_class.assert_called_once_with(mock_config)
        assert result == mock_instance
    
    @patch('utils.config_helpers._config_service', Mock())
    @patch('utils.config_helpers.ConfigurationService')
    def test_get_config_service_returns_existing(self, mock_service_class):
        """2回目以降は既存のインスタンスを返す"""
        # 既にインスタンスが存在する状態をシミュレート
        from utils.config_helpers import _config_service
        existing_instance = _config_service
        
        result = get_config_service()
        
        # 新しいインスタンスは作成されない
        mock_service_class.assert_not_called()
        assert result == existing_instance