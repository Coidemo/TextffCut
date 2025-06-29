"""
セッション状態管理

Streamlitのセッション状態を管理し、テスト可能にする。
移行期間中は既存のセッション状態と互換性を保つ。
"""

import streamlit as st
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TranscriptionState:
    """文字起こし関連の状態"""
    video_path: Optional[str] = None
    transcription_result: Optional[Any] = None
    is_processing: bool = False
    use_api: bool = False
    api_key: Optional[str] = None
    local_model_size: str = "medium"
    cancel_requested: bool = False
    
    
@dataclass
class EditingState:
    """編集関連の状態"""
    edited_text: Optional[str] = None
    current_diff: Optional[Any] = None
    time_ranges: Optional[List[tuple]] = None
    adjusted_time_ranges: Optional[List[tuple]] = None
    boundary_adjustment_mode: bool = False
    has_boundary_adjustments: bool = False
    

@dataclass
class ExportState:
    """エクスポート関連の状態"""
    export_settings: Dict[str, Any] = field(default_factory=dict)
    last_export_path: Optional[str] = None
    

class SessionManager:
    """セッション状態を管理するクラス"""
    
    def __init__(self):
        """初期化"""
        self._ensure_initialized()
    
    def _ensure_initialized(self):
        """セッション状態が初期化されていることを確認"""
        if "session_manager_initialized" not in st.session_state:
            # 初回のみ初期化
            st.session_state["session_manager_initialized"] = True
            st.session_state["_transcription_state"] = TranscriptionState()
            st.session_state["_editing_state"] = EditingState()
            st.session_state["_export_state"] = ExportState()
    
    # === 文字起こし関連 ===
    
    @property
    def transcription(self) -> TranscriptionState:
        """文字起こし状態を取得"""
        return st.session_state.get("_transcription_state", TranscriptionState())
    
    def set_video_path(self, path: str):
        """動画パスを設定"""
        self.transcription.video_path = path
        # 既存の互換性のため
        st.session_state["current_video_path"] = path
        st.session_state["video_path"] = path  # 音声プレビュー用
    
    def get_video_path(self) -> Optional[str]:
        """動画パスを取得"""
        # 既存のキーも確認（互換性）
        return self.transcription.video_path or st.session_state.get("current_video_path")
    
    def set_transcription_result(self, result: Any):
        """文字起こし結果を設定"""
        self.transcription.transcription_result = result
        # 既存の互換性のため
        st.session_state["transcription_result"] = result
    
    def get_transcription_result(self) -> Optional[Any]:
        """文字起こし結果を取得"""
        # 既存のキーも確認（互換性）
        return self.transcription.transcription_result or st.session_state.get("transcription_result")
    
    # === 編集関連 ===
    
    @property
    def editing(self) -> EditingState:
        """編集状態を取得"""
        return st.session_state.get("_editing_state", EditingState())
    
    def set_edited_text(self, text: str):
        """編集されたテキストを設定"""
        self.editing.edited_text = text
        # 既存の互換性のため
        st.session_state["edited_text"] = text
        st.session_state["current_edited_text"] = text
    
    def get_edited_text(self) -> Optional[str]:
        """編集されたテキストを取得"""
        # 既存のキーも確認（互換性）
        return (self.editing.edited_text or 
                st.session_state.get("edited_text") or 
                st.session_state.get("current_edited_text"))
    
    def set_time_ranges(self, ranges: List[tuple]):
        """時間範囲を設定"""
        self.editing.time_ranges = ranges
        # 既存の互換性のため
        st.session_state["time_ranges"] = ranges
    
    def get_time_ranges(self) -> Optional[List[tuple]]:
        """時間範囲を取得"""
        # 既存のキーも確認（互換性）
        return self.editing.time_ranges or st.session_state.get("time_ranges")
    
    # === エクスポート関連 ===
    
    @property
    def export(self) -> ExportState:
        """エクスポート状態を取得"""
        return st.session_state.get("_export_state", ExportState())
    
    # === 汎用メソッド ===
    
    def get(self, key: str, default: Any = None) -> Any:
        """既存のセッション状態との互換性のためのget"""
        return st.session_state.get(key, default)
    
    def set(self, key: str, value: Any):
        """既存のセッション状態との互換性のためのset"""
        st.session_state[key] = value
    
    def delete(self, key: str):
        """キーを削除"""
        if key in st.session_state:
            del st.session_state[key]
    
    def clear_transcription_state(self):
        """文字起こし状態をクリア"""
        st.session_state["_transcription_state"] = TranscriptionState()
        # 既存のキーもクリア
        for key in ["transcription_result", "current_video_path", "cancel_transcription"]:
            self.delete(key)
    
    def clear_editing_state(self):
        """編集状態をクリア"""
        st.session_state["_editing_state"] = EditingState()
        # 既存のキーもクリア
        for key in ["edited_text", "current_edited_text", "time_ranges", "adjusted_time_ranges"]:
            self.delete(key)
    
    def is_ready_for_export(self) -> bool:
        """エクスポート可能な状態かチェック"""
        return bool(
            self.get_video_path() and
            self.get_edited_text() and
            self.get_time_ranges()
        )


# シングルトンインスタンス
_session_manager = None


def get_session_manager() -> SessionManager:
    """SessionManagerのシングルトンインスタンスを取得"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager