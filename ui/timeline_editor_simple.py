"""
シンプルなタイムライン編集UI
localStorageを使用してJavaScriptとPython間でデータを共有
"""
from typing import Any
import streamlit as st
import streamlit.components.v1 as components
import json
from core.waveform_processor import WaveformProcessor
from utils.logging import get_logger

logger = get_logger(__name__)


def render_timeline_editor_simple(time_ranges: list[tuple[float, float]], transcription_result: Any, video_path: str) -> None:
    """
    シンプルなタイムライン編集UI
    
    Args:
        time_ranges: 編集対象の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
    """
    st.markdown("### 📝 インタラクティブ・タイムライン編集")
    
    # セッション状態の初期化
    if "_timeline_editor_initialized" not in st.session_state:
        st.session_state._timeline_editor_initialized = True
        st.session_state._timeline_current_data = None
    
    # 波形データの準備（既存のコードと同じ）
    if "timeline_waveforms" not in st.session_state:
        with st.spinner("波形データを抽出中..."):
            processor = WaveformProcessor()
            waveform_data = processor.extract_waveforms_for_clips(
                video_path,
                time_ranges,
                samples_per_clip=200
            )
            st.session_state.timeline_waveforms = waveform_data
    else:
        waveform_data = st.session_state.timeline_waveforms
    
    # クリップデータの準備
    clips_data = []
    for i, ((start, end), waveform) in enumerate(zip(time_ranges, waveform_data)):
        clips_data.append({
            "id": f"clip_{i}",
            "start_time": start,
            "end_time": end,
            "samples": waveform.samples if waveform else []
        })
    
    # 現在のデータをJSONに変換
    clips_json = json.dumps(clips_data)
    
    # シンプルなアプローチ：数値入力フィールドを直接使用
    st.markdown("#### 🎯 クリップの時間調整")
    
    # 各クリップの編集UI
    edited_clips = []
    for i, clip in enumerate(clips_data):
        with st.expander(f"クリップ {i+1}", expanded=(i == 0)):
            col1, col2 = st.columns(2)
            
            with col1:
                new_start = st.number_input(
                    "開始時間（秒）",
                    min_value=0.0,
                    max_value=float(clip["end_time"]),
                    value=float(clip["start_time"]),
                    step=0.1,
                    format="%.3f",
                    key=f"start_{i}"
                )
            
            with col2:
                # 次のクリップの開始時間を上限とする
                max_end = clips_data[i+1]["start_time"] if i < len(clips_data)-1 else 9999.0
                new_end = st.number_input(
                    "終了時間（秒）",
                    min_value=float(new_start),
                    max_value=float(max_end),
                    value=float(clip["end_time"]),
                    step=0.1,
                    format="%.3f",
                    key=f"end_{i}"
                )
            
            # 長さを表示
            duration = new_end - new_start
            st.info(f"長さ: {duration:.3f}秒")
            
            # 編集されたデータを保存
            edited_clips.append({
                "start_time": new_start,
                "end_time": new_end
            })
    
    # ボタン
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ 編集完了", key="timeline_apply_simple", use_container_width=True, type="primary"):
            # 編集されたデータを時間範囲のタプルに変換
            adjusted_ranges = [(clip["start_time"], clip["end_time"]) for clip in edited_clips]
            
            # セッション状態に保存
            st.session_state.adjusted_time_ranges = adjusted_ranges
            st.session_state.timeline_editing_completed = True
            if "timeline_waveforms" in st.session_state:
                del st.session_state.timeline_waveforms
            
            st.success(f"✅ {len(adjusted_ranges)}個のクリップを保存しました")
            st.rerun()
    
    with col2:
        if st.button("✖ キャンセル", key="timeline_cancel_simple", use_container_width=True):
            st.session_state.timeline_editing_cancelled = True
            if "timeline_waveforms" in st.session_state:
                del st.session_state.timeline_waveforms
            st.rerun()
    
    # デバッグ情報
    with st.expander("デバッグ情報", expanded=False):
        st.write("元の時間範囲:")
        for i, (start, end) in enumerate(time_ranges[:3]):
            st.text(f"  クリップ{i+1}: {start:.3f}秒 - {end:.3f}秒")
        
        st.write("編集後の時間範囲:")
        for i, clip in enumerate(edited_clips[:3]):
            st.text(f"  クリップ{i+1}: {clip['start_time']:.3f}秒 - {clip['end_time']:.3f}秒")