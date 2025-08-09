"""
SessionManagerの単体テスト
"""

from unittest.mock import patch

import pytest

from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from infrastructure.ui.session_manager import SessionManager, TranscriptionState


class TestSessionManager:
    """SessionManagerのテスト"""

    @pytest.fixture
    def mock_session_state(self):
        """モックのsession_state"""
        return {}

    @pytest.fixture
    def session_manager(self, mock_session_state):
        """テスト用のSessionManager"""
        with patch("streamlit.session_state", mock_session_state):
            return SessionManager()

    def test_set_and_get_transcription_result(self, session_manager, mock_session_state):
        """文字起こし結果の設定と取得"""
        # テストデータ作成
        word = Word(word="test", start=0.0, end=1.0, confidence=0.9)
        segment = TranscriptionSegment(id="seg_1", text="test", start=0.0, end=1.0, words=[word])
        result = TranscriptionResult(id="test_id", language="ja", segments=[segment], metadata={})

        # SessionManagerで設定
        with patch("streamlit.session_state", mock_session_state):
            session_manager.set_transcription_result(result)

            # 取得
            retrieved = session_manager.get_transcription_result()

        # 検証
        assert retrieved is not None
        assert isinstance(retrieved, TranscriptionResult)
        assert len(retrieved.segments) == 1
        assert retrieved.segments[0].words is not None
        assert len(retrieved.segments[0].words) == 1
        assert retrieved.segments[0].words[0].word == "test"

    def test_transcription_state_initialization(self, session_manager, mock_session_state):
        """TranscriptionStateの初期化"""
        with patch("streamlit.session_state", mock_session_state):
            # 初期化確認
            assert "session_manager_initialized" in mock_session_state
            assert "_transcription_state" in mock_session_state

            # TranscriptionStateのインスタンス確認
            state = session_manager.transcription
            assert isinstance(state, TranscriptionState)
            assert state.transcription_result is None
