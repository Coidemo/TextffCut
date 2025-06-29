"""
スタートアップ処理のユニットテスト
"""

from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import pytest

from utils.startup import (
    run_initial_checks,
    initialize_session_state,
    get_version_info,
    check_environment
)


class TestRunInitialChecks:
    """run_initial_checks関数のテスト"""
    
    @patch('streamlit.session_state', new_callable=dict)
    @patch('utils.startup.show_startup_recovery')
    @patch('utils.startup.get_app_version')
    @patch('utils.startup.IS_DOCKER', True)
    def test_normal_startup_docker(self, mock_get_version, mock_show_recovery, mock_session_state):
        """通常起動（Docker環境）"""
        mock_get_version.return_value = "v1.2.3"
        mock_session_state["auto_recovery"] = True
        
        is_docker, version = run_initial_checks()
        
        assert is_docker is True
        assert version == "v1.2.3"
        mock_get_version.assert_called_once()
    
    @patch('streamlit.session_state', new_callable=dict)
    @patch('utils.startup.show_startup_recovery')
    @patch('utils.startup.get_app_version')
    @patch('utils.startup.IS_DOCKER', False)
    def test_normal_startup_local(self, mock_get_version, mock_show_recovery, mock_session_state):
        """通常起動（ローカル環境）"""
        mock_get_version.return_value = "v2.0.0"
        mock_session_state["auto_recovery"] = True
        mock_session_state["startup_recovery_checked"] = True  # 既にチェック済み
        
        is_docker, version = run_initial_checks()
        
        assert is_docker is False
        assert version == "v2.0.0"
        # リカバリチェック済みなので、show_startup_recoveryは呼ばれない
        mock_show_recovery.assert_not_called()
    
    @patch('streamlit.stop')
    @patch('streamlit.session_state', new_callable=dict)
    @patch('utils.startup.show_startup_recovery')
    @patch('utils.startup.get_app_version')
    def test_recovery_needed(self, mock_get_version, mock_show_recovery, mock_session_state, mock_stop):
        """リカバリが必要な場合"""
        mock_get_version.return_value = "v1.0.0"
        mock_session_state["auto_recovery"] = True
        mock_show_recovery.return_value = True  # リカバリ可能
        
        # st.stop()が呼ばれるので戻り値はない
        run_initial_checks()
        
        mock_show_recovery.assert_called_once()
        mock_stop.assert_called_once()
    
    @patch('streamlit.session_state', new_callable=dict)
    @patch('utils.startup.show_startup_recovery')
    def test_auto_recovery_disabled(self, mock_show_recovery, mock_session_state):
        """自動リカバリが無効の場合"""
        mock_session_state["auto_recovery"] = False
        
        is_docker, version = run_initial_checks()
        
        # 自動リカバリが無効なのでshow_startup_recoveryは呼ばれない
        mock_show_recovery.assert_not_called()


class TestInitializeSessionState:
    """initialize_session_state関数のテスト"""
    
    @patch('streamlit.session_state', new_callable=dict)
    def test_initialize_empty_state(self, mock_session_state):
        """空のセッション状態を初期化"""
        initialize_session_state()
        
        assert "auto_recovery" in mock_session_state
        assert mock_session_state["auto_recovery"] is True
        assert "processing_state" in mock_session_state
        assert mock_session_state["processing_state"] is None
        assert "transcription_result" in mock_session_state
        assert "edited_text" in mock_session_state
        assert "time_ranges" in mock_session_state
        assert "video_file_path" in mock_session_state
    
    @patch('streamlit.session_state', {"auto_recovery": False, "custom_key": "value"})
    def test_preserve_existing_values(self):
        """既存の値は上書きしない"""
        with patch('streamlit.session_state', {"auto_recovery": False, "custom_key": "value"}) as mock_state:
            initialize_session_state()
            
            # 既存の値は保持される
            assert mock_state["auto_recovery"] is False
            assert mock_state["custom_key"] == "value"
            # 新しいキーは追加される
            assert "processing_state" in mock_state


class TestGetVersionInfo:
    """get_version_info関数のテスト"""
    
    @patch('utils.startup.get_app_version')
    def test_get_version(self, mock_get_app_version):
        """バージョン情報の取得"""
        mock_get_app_version.return_value = "v3.0.0"
        
        version = get_version_info()
        
        assert version == "v3.0.0"
        mock_get_app_version.assert_called_once()


class TestCheckEnvironment:
    """check_environment関数のテスト"""
    
    @patch('platform.python_version')
    @patch('platform.system')
    @patch('utils.environment.VIDEOS_DIR', "/app/videos")
    @patch('utils.environment.IS_DOCKER', True)
    def test_docker_environment(self, mock_system, mock_python_version):
        """Docker環境の情報取得"""
        mock_system.return_value = "Linux"
        mock_python_version.return_value = "3.12.3"
        
        env_info = check_environment()
        
        assert env_info["is_docker"] is True
        assert env_info["videos_dir"] == "/app/videos"
        assert env_info["platform"] == "Linux"
        assert env_info["python_version"] == "3.12.3"
    
    @patch('platform.python_version')
    @patch('platform.system')
    @patch('utils.environment.VIDEOS_DIR', "./videos")
    @patch('utils.environment.IS_DOCKER', False)
    def test_local_environment(self, mock_system, mock_python_version):
        """ローカル環境の情報取得"""
        mock_system.return_value = "Darwin"
        mock_python_version.return_value = "3.11.0"
        
        env_info = check_environment()
        
        assert env_info["is_docker"] is False
        assert env_info["videos_dir"] == "./videos"
        assert env_info["platform"] == "Darwin"
        assert env_info["python_version"] == "3.11.0"