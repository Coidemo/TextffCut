"""
セッション状態アダプター

Streamlitのセッション状態とサービス層の橋渡しを行う。
セッション状態の複雑性をサービス層から隠蔽し、型安全なインターフェースを提供。
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import streamlit as st

from services import WorkflowSettings, ServiceResult
from core.models import TranscriptionResultV2
from core import TranscriptionSegment as Segment
# SilenceDetection定数のデフォルト値
class SilenceDetection:
    DEFAULT_THRESHOLD = -35.0
    MIN_SILENCE_DURATION = 0.3
    MIN_SEGMENT_DURATION = 0.3


@dataclass
class TranscriptionState:
    """文字起こし関連の状態"""
    result: Optional[TranscriptionResultV2] = None
    in_progress: bool = False
    confirmed: bool = False
    should_run: bool = False
    cancelled: bool = False


@dataclass
class EditingState:
    """編集関連の状態"""
    original_text: Optional[str] = None
    edited_text: Optional[str] = None
    current_diff: Optional[List[Segment]] = None
    show_modal: bool = False


@dataclass
class ProcessingState:
    """処理設定の状態"""
    use_api: bool = False
    api_key: Optional[str] = None
    local_model_size: str = "medium"
    remove_silence: bool = False
    silence_threshold: float = SilenceDetection.DEFAULT_THRESHOLD
    pad_start: float = 0.0
    pad_end: float = 0.0


class SessionStateAdapter:
    """セッション状態とサービス層のアダプター
    
    責任:
    - セッション状態の読み書き
    - サービス層との型変換
    - 状態の一貫性維持
    - デフォルト値の管理
    """
    
    def __init__(self, session_state=None):
        """初期化
        
        Args:
            session_state: Streamlitのセッション状態（テスト時はdict使用可）
        """
        self.session_state = session_state or st.session_state
        self._initialize_defaults()
    
    def _initialize_defaults(self):
        """デフォルト値の初期化"""
        defaults = {
            # ビデオ関連
            'current_video_path': None,
            
            # 文字起こし関連
            'transcription_result': None,
            'transcription_in_progress': False,
            'transcription_confirmed': False,
            'should_run_transcription': False,
            'cancel_transcription': False,
            
            # 編集関連
            'edited_text': None,
            'original_edited_text': None,
            'current_diff': None,
            'current_edited_text': None,
            'show_modal': False,
            
            # 処理設定
            'use_api': False,
            'api_key': None,
            'local_model_size': 'medium',
            'remove_silence': False,
            'silence_threshold': SilenceDetection.DEFAULT_THRESHOLD,
            'pad_start': 0.0,
            'pad_end': 0.0,
            
            # UI状態
            'show_error_and_delete': False,
            'show_confirmation_modal': False,
            'confirmation_info': None
        }
        
        # 存在しないキーのみ設定
        for key, value in defaults.items():
            if key not in self.session_state:
                self.session_state[key] = value
    
    # === Getter メソッド ===
    
    def get_video_path(self) -> Optional[str]:
        """現在の動画パスを取得"""
        return self.session_state.get('current_video_path')
    
    def get_transcription_state(self) -> TranscriptionState:
        """文字起こし状態を取得"""
        return TranscriptionState(
            result=self.session_state.get('transcription_result'),
            in_progress=self.session_state.get('transcription_in_progress', False),
            confirmed=self.session_state.get('transcription_confirmed', False),
            should_run=self.session_state.get('should_run_transcription', False),
            cancelled=self.session_state.get('cancel_transcription', False)
        )
    
    def get_editing_state(self) -> EditingState:
        """編集状態を取得"""
        return EditingState(
            original_text=self.session_state.get('original_edited_text'),
            edited_text=self.session_state.get('edited_text'),
            current_diff=self.session_state.get('current_diff'),
            show_modal=self.session_state.get('show_modal', False)
        )
    
    def get_processing_state(self) -> ProcessingState:
        """処理設定を取得"""
        return ProcessingState(
            use_api=self.session_state.get('use_api', False),
            api_key=self.session_state.get('api_key'),
            local_model_size=self.session_state.get('local_model_size', 'medium'),
            remove_silence=self.session_state.get('remove_silence', False),
            silence_threshold=self.session_state.get('silence_threshold', SilenceDetection.DEFAULT_THRESHOLD),
            pad_start=self.session_state.get('pad_start', 0.0),
            pad_end=self.session_state.get('pad_end', 0.0)
        )
    
    def get_workflow_settings(self) -> WorkflowSettings:
        """ワークフロー設定を生成"""
        processing = self.get_processing_state()
        
        return WorkflowSettings(
            # 文字起こし設定
            model_size=processing.local_model_size if not processing.use_api else "whisper-1",
            use_api=processing.use_api,
            api_key=processing.api_key,
            language="ja",  # 現在は日本語固定
            use_cache=True,
            save_cache=True,
            
            # 無音削除設定
            remove_silence=processing.remove_silence,
            silence_threshold=processing.silence_threshold,
            min_silence_duration=SilenceDetection.MIN_SILENCE_DURATION,
            pad_start=processing.pad_start,
            pad_end=processing.pad_end,
            min_segment_duration=SilenceDetection.MIN_SEGMENT_DURATION,
            
            # エクスポート設定（デフォルト）
            export_format="fcpxml",
            output_dir=None,
            project_name=None,
            event_name=None,
            
            # 動画処理設定
            process_video=False,
            video_output_path=None,
            
            # その他
            separated_mode=self._should_use_separated_mode(),
            task_type="full"
        )
    
    # === Setter メソッド ===
    
    def set_video_path(self, path: str):
        """動画パスを設定"""
        self.session_state['current_video_path'] = path
        # 動画が変更されたら関連状態をリセット
        self.clear_transcription_state()
        self.clear_editing_state()
    
    def set_transcription_result(self, result: TranscriptionResultV2):
        """文字起こし結果を設定"""
        self.session_state['transcription_result'] = result
        self.session_state['transcription_in_progress'] = False
        self.session_state['transcription_confirmed'] = True
    
    def set_edited_text(self, text: str):
        """編集テキストを設定"""
        self.session_state['edited_text'] = text
        if self.session_state.get('original_edited_text') is None:
            self.session_state['original_edited_text'] = text
    
    def set_processing_settings(self, settings: ProcessingState):
        """処理設定を更新"""
        self.session_state['use_api'] = settings.use_api
        self.session_state['api_key'] = settings.api_key
        self.session_state['local_model_size'] = settings.local_model_size
        self.session_state['remove_silence'] = settings.remove_silence
        self.session_state['silence_threshold'] = settings.silence_threshold
        self.session_state['pad_start'] = settings.pad_start
        self.session_state['pad_end'] = settings.pad_end
    
    # === 状態更新メソッド ===
    
    def update_from_service_result(self, result: ServiceResult, service_type: str):
        """サービス結果をセッション状態に反映
        
        Args:
            result: サービスの実行結果
            service_type: サービスタイプ（transcription, editing, export等）
        """
        if not result.success:
            # エラーの場合は何もしない（UIで処理）
            return
        
        if service_type == "transcription":
            if isinstance(result.data, TranscriptionResultV2):
                self.set_transcription_result(result.data)
        
        elif service_type == "editing":
            if result.data and isinstance(result.data, list):
                self.session_state['current_diff'] = result.data
        
        elif service_type == "export":
            # エクスポート完了の記録など
            pass
    
    def start_transcription(self):
        """文字起こし開始"""
        self.session_state['transcription_in_progress'] = True
        self.session_state['cancel_transcription'] = False
        self.session_state['should_run_transcription'] = True
    
    def cancel_transcription(self):
        """文字起こしキャンセル"""
        self.session_state['cancel_transcription'] = True
        self.session_state['transcription_in_progress'] = False
    
    def clear_transcription_state(self):
        """文字起こし状態をクリア"""
        self.session_state['transcription_result'] = None
        self.session_state['transcription_in_progress'] = False
        self.session_state['transcription_confirmed'] = False
        self.session_state['should_run_transcription'] = False
        self.session_state['cancel_transcription'] = False
    
    def clear_editing_state(self):
        """編集状態をクリア"""
        self.session_state['edited_text'] = None
        self.session_state['original_edited_text'] = None
        self.session_state['current_diff'] = None
        self.session_state['current_edited_text'] = None
        self.session_state['show_modal'] = False
    
    def clear_all(self):
        """すべての状態をクリア"""
        keys_to_keep = ['use_api', 'api_key', 'local_model_size']  # 設定は保持
        
        for key in list(self.session_state.keys()):
            if key not in keys_to_keep:
                del self.session_state[key]
        
        self._initialize_defaults()
    
    # === ヘルパーメソッド ===
    
    def _should_use_separated_mode(self) -> bool:
        """分離モードを使用すべきか判定"""
        # APIモードでは分離モード不要
        if self.session_state.get('use_api', False):
            return False
        
        # ローカルモードでは常に分離モード推奨
        return True
    
    def has_transcription_result(self) -> bool:
        """文字起こし結果があるか確認"""
        return self.session_state.get('transcription_result') is not None
    
    def has_edited_text(self) -> bool:
        """編集テキストがあるか確認"""
        return bool(self.session_state.get('edited_text'))
    
    def is_text_changed(self) -> bool:
        """テキストが変更されているか確認"""
        original = self.session_state.get('original_edited_text')
        current = self.session_state.get('edited_text')
        return original is not None and current is not None and original != current
    
    def get_export_settings(self, format: str = "fcpxml") -> Dict[str, Any]:
        """エクスポート設定を取得"""
        return {
            'format': format,
            'remove_silence': self.session_state.get('remove_silence', False),
            'project_name': None,  # UIから取得
            'event_name': None,    # UIから取得
            'output_dir': None     # UIから取得
        }