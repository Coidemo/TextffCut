"""
UIコンポーネントのモジュール
"""

import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from ..config import config
from ..utils import BuzzClipError, format_time

def render_file_uploader() -> Optional[str]:
    """ファイルアップローダーを表示"""
    st.subheader("1. 動画ファイルのアップロード")
    uploaded_file = st.file_uploader(
        "動画ファイルを選択してください",
        type=config.supported_video_formats
    )
    
    if uploaded_file:
        # 一時ファイルとして保存
        temp_path = Path("temp") / uploaded_file.name
        temp_path.parent.mkdir(exist_ok=True)
        
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getvalue())
        
        return str(temp_path)
    
    return None

def render_model_selection() -> str:
    """Whisperモデルの選択UIを表示"""
    st.subheader("2. Whisperモデルの選択")
    return st.selectbox(
        "使用するWhisperモデルを選択してください",
        options=config.whisper_models,
        index=0
    )

def render_noise_settings() -> Tuple[float, float]:
    """ノイズ設定のUIを表示"""
    st.subheader("3. ノイズ設定")
    col1, col2 = st.columns(2)
    
    with col1:
        noise_threshold = st.slider(
            "ノイズ閾値 (dB)",
            min_value=-60,
            max_value=-10,
            value=config.default_noise_threshold,
            step=1
        )
    
    with col2:
        min_silence_duration = st.slider(
            "最小無音時間 (秒)",
            min_value=0.1,
            max_value=1.0,
            value=config.default_min_silence_duration,
            step=0.1
        )
    
    return noise_threshold, min_silence_duration

def render_output_settings() -> Tuple[str, bool, bool]:
    """出力設定のUIを表示"""
    st.subheader("4. 出力設定")
    
    output_name = st.text_input(
        "出力ファイル名",
        value="output",
        help="出力ファイルの基本名を指定してください"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        remove_fillers = st.checkbox(
            "無音部分を除去",
            value=True,
            help="無音部分を自動的に除去します"
        )
    
    with col2:
        create_fcpxml = st.checkbox(
            "FCPXMLファイルを生成",
            value=True,
            help="Final Cut Pro用のXMLファイルを生成します"
        )
    
    return output_name, remove_fillers, create_fcpxml

def render_progress_bar(progress: float, status: str) -> None:
    """進捗バーを表示"""
    st.progress(progress)
    st.text(status)

def render_error_message(error: Exception) -> None:
    """エラーメッセージを表示"""
    st.error(f"エラーが発生しました: {str(error)}")

def render_success_message(message: str) -> None:
    """成功メッセージを表示"""
    st.success(message)

def render_segment_info(segments: List[Tuple[float, float]]) -> None:
    """セグメント情報を表示"""
    st.subheader("検出されたセグメント")
    
    for i, (start, end) in enumerate(segments, 1):
        st.text(f"セグメント {i}: {format_time(start)} - {format_time(end)}")

def render_video_player(video_path: str) -> None:
    """動画プレーヤーを表示"""
    st.video(video_path)

def render_download_button(file_path: str, label: str) -> None:
    """ダウンロードボタンを表示"""
    with open(file_path, "rb") as f:
        st.download_button(
            label=label,
            data=f,
            file_name=Path(file_path).name,
            mime="video/mp4"
        ) 