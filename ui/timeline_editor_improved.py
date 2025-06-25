"""
改善されたタイムライン編集UI
Phase 1の実装：基本改善
"""

import streamlit as st
from typing import Any
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.waveform_processor import WaveformProcessor
from services.timeline_editing_service import TimelineEditingService
from ui.timeline_color_scheme import TimelineColorScheme
from ui.timeline_dark_mode_fix import inject_dark_mode_css
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def render_improved_timeline_editor(
    time_ranges: list[tuple[float, float]], transcription_result: dict[str, Any], video_path: str
) -> None:
    """
    改善されたタイムライン編集UIをレンダリング

    Args:
        time_ranges: 初期の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
    """
    # ダークモード用のCSS注入
    inject_dark_mode_css()

    service = TimelineEditingService()

    # タイムラインの初期化
    if "timeline_initialized" not in st.session_state:
        result = service.initialize_timeline(time_ranges, transcription_result, video_path)
        if result["success"]:
            st.session_state.timeline_initialized = True
        else:
            st.error("タイムラインの初期化に失敗しました")
            return

    # UIヘッダー
    st.markdown("### 📝 タイムライン編集（改善版）")
    st.markdown("波形を確認しながら、精密に編集できます")

    # 統計情報表示
    stats = service.get_timeline_statistics()
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("セグメント数", stats.get("segment_count", 0))
        with col2:
            st.metric("総時間", format_time(stats.get("total_duration", 0)))
        with col3:
            st.metric("動画長", format_time(stats.get("video_duration", 0)))
        with col4:
            st.metric("カバー率", f"{stats.get('coverage_percentage', 0):.1f}%")

    st.divider()

    # セグメント選択
    timeline_data = st.session_state.get("timeline_data", {})
    segments = timeline_data.get("segments", [])
    
    if not segments:
        st.warning("セグメントデータがありません")
        return

    # セグメント選択ドロップダウン
    segment_options = [
        f"セグメント {i+1} ({format_time(seg['start'])} - {format_time(seg['end'])})"
        for i, seg in enumerate(segments)
    ]
    
    selected_idx = st.selectbox(
        "編集するセグメントを選択",
        range(len(segment_options)),
        format_func=lambda x: segment_options[x],
        key="selected_segment_idx"
    )

    # 全体波形表示（リアルタイム更新）
    render_realtime_waveform(video_path, segments, selected_idx, service)

    st.divider()

    # 選択セグメントの詳細編集
    if selected_idx < len(segments):
        render_segment_editor(segments[selected_idx], selected_idx, segments, service, transcription_result)

    # 操作ボタン
    st.divider()
    render_action_buttons(service)


def render_realtime_waveform(video_path: str, segments: list, selected_idx: int, service: TimelineEditingService):
    """リアルタイム更新される全体波形表示"""
    
    # 波形データの生成キーを作成（セグメント情報のハッシュ）
    waveform_key = f"waveform_{hash(str([(s['start'], s['end']) for s in segments]))}"
    
    # 波形データを生成（キャッシュ利用）
    if waveform_key not in st.session_state:
        with st.spinner("波形データを読み込み中..."):
            waveform_processor = WaveformProcessor()
            fig = go.Figure()
            
            # カラースキーム
            colors = TimelineColorScheme.get_colors()
            
            current_x_offset = 0
            segment_boundaries = [0]
            
            for i, segment in enumerate(segments):
                try:
                    waveform_data = waveform_processor.extract_waveform(
                        video_path, segment['start'], segment['end'], f"segment_{i+1}"
                    )
                    
                    if waveform_data and waveform_data.samples and len(waveform_data.samples) > 0:
                        duration = segment['end'] - segment['start']
                        time_points = np.linspace(0, duration, len(waveform_data.samples))
                        adjusted_time = time_points + current_x_offset

                        # セグメントの色を選択状態に応じて変更
                        line_color = colors["segment_active"] if i == selected_idx else colors["waveform_positive"]
                        fill_color = f"{line_color}40"  # 半透明

                        fig.add_trace(
                            go.Scatter(
                                x=adjusted_time,
                                y=waveform_data.samples,
                                mode="lines",
                                name=f"セグメント {i+1}",
                                line=dict(color=line_color, width=2 if i == selected_idx else 1),
                                fill="tozeroy",
                                fillcolor=fill_color,
                                hovertemplate="時間: %{x:.2f}秒<br>振幅: %{y:.3f}<extra></extra>",
                            )
                        )

                        current_x_offset += duration
                        segment_boundaries.append(current_x_offset)
                    else:
                        duration = segment['end'] - segment['start']
                        current_x_offset += duration
                        segment_boundaries.append(current_x_offset)
                        
                except Exception as e:
                    logger.error(f"波形データ取得エラー (セグメント{i+1}): {e}")
                    duration = segment['end'] - segment['start']
                    current_x_offset += duration
                    segment_boundaries.append(current_x_offset)

            # セグメント境界を縦線で表示
            for i, boundary in enumerate(segment_boundaries[1:-1]):
                fig.add_vline(
                    x=boundary,
                    line_color=colors["boundary_marker"],
                    line_width=2,
                    line_dash="dash",
                    annotation_text=f"境界 {i+1}",
                    annotation_position="top",
                )

            # レイアウト設定
            fig.update_layout(
                title="全セグメントの波形表示（選択中のセグメントはハイライト）",
                xaxis_title="時間 (秒)",
                yaxis_title="振幅",
                height=300,
                showlegend=False,
                paper_bgcolor=colors["background"],
                plot_bgcolor=colors["background"],
                font=dict(color=colors["text_primary"]),
                xaxis=dict(
                    showgrid=True,
                    gridcolor=colors["grid_lines"],
                    zeroline=True,
                    zerolinecolor=colors["grid_lines"]
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor=colors["grid_lines"],
                    zeroline=True,
                    zerolinecolor=colors["grid_lines"]
                ),
            )
            
            st.session_state[waveform_key] = fig
    
    # 波形を表示
    st.plotly_chart(st.session_state[waveform_key], use_container_width=True, key="main_waveform")


def render_segment_editor(segment: dict, segment_idx: int, all_segments: list, 
                         service: TimelineEditingService, transcription_result: dict):
    """選択セグメントの詳細編集UI"""
    
    st.markdown(f"#### 🎯 セグメント {segment_idx + 1} の精密編集")
    
    # 現在の値
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("開始時間", format_time(segment['start']))
    with col2:
        st.metric("終了時間", format_time(segment['end']))
    with col3:
        st.metric("長さ", format_time(segment['end'] - segment['start']))

    # 精密編集コントロール
    st.markdown("##### 時間調整")
    
    # 制約の計算
    min_start = 0.0 if segment_idx == 0 else all_segments[segment_idx - 1]['end'] + 0.01
    max_end = transcription_result.get("duration", segment['end'] + 10)
    if segment_idx < len(all_segments) - 1:
        max_end = all_segments[segment_idx + 1]['start'] - 0.01

    # 数値入力とボタンコントロール
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**開始時間**")
        # 数値入力
        new_start = st.number_input(
            "開始時間（秒）",
            min_value=min_start,
            max_value=segment['end'] - 0.01,
            value=segment['start'],
            step=0.001,  # ミリ秒単位
            format="%.3f",
            key=f"start_input_{segment['id']}"
        )
        
        # 調整ボタン
        btn_cols = st.columns(6)
        adjustments = [("-1s", -1.0), ("-0.1s", -0.1), ("-10ms", -0.01), 
                      ("+10ms", 0.01), ("+0.1s", 0.1), ("+1s", 1.0)]
        
        for i, (label, adjustment) in enumerate(adjustments):
            if btn_cols[i].button(label, key=f"start_btn_{segment['id']}_{i}"):
                new_val = segment['start'] + adjustment
                if min_start <= new_val <= segment['end'] - 0.01:
                    service.set_segment_time_range(segment['id'], new_val, segment['end'])
                    # 波形を更新するためにキャッシュをクリア
                    clear_waveform_cache()
                    st.rerun()

    with col2:
        st.markdown("**終了時間**")
        # 数値入力
        new_end = st.number_input(
            "終了時間（秒）",
            min_value=new_start + 0.01,
            max_value=max_end,
            value=segment['end'],
            step=0.001,  # ミリ秒単位
            format="%.3f",
            key=f"end_input_{segment['id']}"
        )
        
        # 調整ボタン
        btn_cols = st.columns(6)
        for i, (label, adjustment) in enumerate(adjustments):
            if btn_cols[i].button(label, key=f"end_btn_{segment['id']}_{i}"):
                new_val = segment['end'] + adjustment
                if segment['start'] + 0.01 <= new_val <= max_end:
                    service.set_segment_time_range(segment['id'], segment['start'], new_val)
                    # 波形を更新するためにキャッシュをクリア
                    clear_waveform_cache()
                    st.rerun()

    # 値が変更された場合は更新
    if new_start != segment['start'] or new_end != segment['end']:
        if st.button("変更を適用", type="primary", key=f"apply_{segment['id']}"):
            service.set_segment_time_range(segment['id'], new_start, new_end)
            # 波形を更新するためにキャッシュをクリア
            clear_waveform_cache()
            st.rerun()

    # セグメントのテキスト表示
    with st.expander("テキスト内容", expanded=False):
        st.text(segment.get("text", ""))


def clear_waveform_cache():
    """波形キャッシュをクリア"""
    keys_to_remove = [key for key in st.session_state.keys() if key.startswith("waveform_")]
    for key in keys_to_remove:
        del st.session_state[key]


def render_action_buttons(service: TimelineEditingService):
    """アクションボタンをレンダリング"""
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ 編集を完了", type="primary", use_container_width=True):
            try:
                adjusted_ranges = service.get_adjusted_time_ranges()
                service.save_timeline_settings()
                # セッション状態に保存
                st.session_state.timeline_editing_completed = True
                st.session_state.adjusted_time_ranges = adjusted_ranges
                # クリーンアップ
                cleanup_session_state()
                st.rerun()
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")

    with col2:
        if st.button("🔄 リセット", use_container_width=True):
            cleanup_session_state()
            clear_waveform_cache()
            st.rerun()

    with col3:
        if st.button("❌ キャンセル", use_container_width=True):
            st.session_state.timeline_editing_cancelled = True
            cleanup_session_state()
            clear_waveform_cache()
            st.rerun()


def cleanup_session_state():
    """セッション状態をクリーンアップ"""
    keys_to_remove = ["timeline_initialized", "timeline_data", "selected_segment_idx"]
    
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]