"""
エクスポートセクション

切り抜き箇所の抽出と動画/字幕のエクスポート機能。
既存のmain.pyのロジックを保持しながらモジュール化。
"""

import os
import streamlit as st
from pathlib import Path
from typing import Optional, List, Tuple, Any

from config import config
from core import TextProcessor, TranscriptionSegment
from core.alignment_processor import AlignmentProcessor
from core.error_handling import ErrorHandler
from core.time_mapper import TimeMapper
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription_subprocess import SubprocessTranscriber
from services import ConfigurationService, ExportService, TextEditingService, VideoProcessingService
from ui import show_export_settings, show_progress
from utils import ProcessingContext, cleanup_intermediate_files
from utils.config_helpers import set_api_mode, is_api_mode
from utils.debug_helpers import debug_words_status
from utils.environment import VIDEOS_DIR
from utils.file_utils import ensure_directory, get_safe_filename
from utils.logging import get_logger
from utils.path_helpers import get_display_path
from utils.time_utils import format_time
from utils.export_helpers import (
    determine_export_format,
    export_xml,
    export_srt_with_diff,
    generate_export_paths,
    format_export_success_message,
    get_srt_settings_from_session
)
from infrastructure.ui.session_manager import get_session_manager

logger = get_logger(__name__)


def show_export_section(
    video_path: str,
    edited_text: str,
    time_ranges: List[Tuple[float, float]],
    transcription_result: Any,
    noise_threshold: float = -35,
    min_silence_duration: float = 0.3,
    min_segment_duration: float = 0.3,
    padding_start: float = 0.1,
    padding_end: float = 0.1
) -> None:
    """
    エクスポートセクションを表示
    
    Args:
        video_path: 動画ファイルパス
        edited_text: 編集されたテキスト
        time_ranges: 切り抜き時間範囲
        transcription_result: 文字起こし結果
        noise_threshold: 無音検出の閾値
        min_silence_duration: 最小無音時間
        min_segment_duration: 最小セグメント時間
        padding_start: 開始パディング
        padding_end: 終了パディング
    """
    session = get_session_manager()
    
    st.markdown("---")
    st.subheader("🎬 切り抜き箇所の抽出")
    
    # タイムライン編集ボタン（時間範囲が計算されている場合のみ表示）
    if time_ranges:
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button(
                "📊 タイムライン編集", 
                use_container_width=True, 
                help="クリップの境界を細かく調整します"
            ):
                st.session_state.show_timeline_section = True
                st.rerun()
        
        # 調整された時間範囲がある場合は表示
        if "adjusted_time_ranges" in st.session_state:
            with col2:
                st.success("✅ タイムライン編集済み（調整が適用されます）")
    
    # 処理オプション
    st.markdown("#### ⚙️ 処理オプション")
    process_type, primary_format, export_srt, timeline_fps = show_export_settings()
    
    if process_type == "無音削除付き":
        st.markdown("##### 🔇 無音削除の設定")
        st.info(
            f"現在の設定: 閾値{noise_threshold}dB | 無音{min_silence_duration}秒 | "
            f"セグメント{min_segment_duration}秒 | パディング{padding_start}-{padding_end}秒 | "
            f"設定変更は左サイドパネルの「無音検出」タブから"
        )
    
    # 出力先の表示
    st.markdown("#### 📁 出力先")
    video_name = Path(video_path).stem
    safe_name = get_safe_filename(video_name)
    
    # 出力パスを表示（Docker環境ではホストパスに変換）
    video_parent = Path(video_path).parent
    project_path = video_parent / f"{safe_name}_TextffCut"
    
    if os.path.exists("/.dockerenv"):
        # Docker環境：ホストパスに変換して表示
        host_videos_path = os.getenv("HOST_VIDEOS_PATH", str(video_parent))
        display_path = os.path.join(host_videos_path, f"{safe_name}_TextffCut")
    else:
        # ローカル環境：そのまま表示
        display_path = str(project_path)
    
    st.code(display_path, language=None)
    
    # 処理実行ボタン
    if st.button("🚀 処理を実行", type="primary", use_container_width=True):
        _execute_export(
            video_path=video_path,
            edited_text=edited_text,
            time_ranges=time_ranges,
            transcription_result=transcription_result,
            process_type=process_type,
            primary_format=primary_format,
            export_srt=export_srt,
            timeline_fps=timeline_fps,
            noise_threshold=noise_threshold,
            min_silence_duration=min_silence_duration,
            min_segment_duration=min_segment_duration,
            padding_start=padding_start,
            padding_end=padding_end,
            project_path=project_path,
            safe_name=safe_name
        )


def _execute_export(
    video_path: str,
    edited_text: str,
    time_ranges: List[Tuple[float, float]],
    transcription_result: Any,
    process_type: str,
    primary_format: str,
    export_srt: bool,
    timeline_fps: str,
    noise_threshold: float,
    min_silence_duration: float,
    min_segment_duration: float,
    padding_start: float,
    padding_end: float,
    project_path: Path,
    safe_name: str
) -> None:
    """
    エクスポート処理を実行
    
    移行期間中は、レガシー実装を使用して動作の同一性を保証。
    """
    # 実行前にAPI設定を反映
    if st.session_state.get("use_api", False):
        set_api_mode(True, st.session_state.get("api_key", ""))
    else:
        set_api_mode(False)
    
    # 区切り文字対応の差分検索を使用
    text_processor = TextProcessor()
    
    # 境界マーカーを解析
    boundary_adjustments = text_processor.parse_boundary_markers(edited_text)
    
    # マーカーを除去したテキストで処理
    cleaned_text = text_processor.remove_boundary_markers(edited_text)
    
    # 区切り文字の様々なパターンをチェック（処理実行時）
    separator_patterns = ["---", "——", "－－－"]
    found_separator = None
    
    for pattern in separator_patterns:
        if pattern in cleaned_text:
            found_separator = pattern
            break
    
    # フルテキストを取得
    full_text = transcription_result.text
    
    # レガシー実装を呼び出す
    from .export_section_legacy import execute_export_legacy
    
    execute_export_legacy(
        video_path=video_path,
        edited_text=edited_text,
        time_ranges=time_ranges,
        transcription_result=transcription_result,
        process_type=process_type,
        primary_format=primary_format,
        export_srt=export_srt,
        timeline_fps=timeline_fps,
        noise_threshold=noise_threshold,
        min_silence_duration=min_silence_duration,
        min_segment_duration=min_segment_duration,
        padding_start=padding_start,
        padding_end=padding_end,
        project_path=project_path,
        safe_name=safe_name,
        full_text=full_text,
        found_separator=found_separator,
        cleaned_text=cleaned_text
    )