"""
タイムライン編集UI

Plotlyを使用した視覚的なタイムライン編集機能
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Tuple, Optional, Dict
import numpy as np

from core.timeline import Timeline, TimelineSegment
from utils.time_utils import format_time


def create_timeline_figure(timeline: Timeline, video_duration: float) -> go.Figure:
    """
    タイムラインの視覚的表現を作成
    
    Args:
        timeline: タイムラインオブジェクト
        video_duration: 動画の総時間
        
    Returns:
        Plotlyのフィギュアオブジェクト
    """
    # 入力検証
    if video_duration <= 0:
        raise ValueError("動画の長さは0より大きい必要があります")
    
    if not timeline.segments:
        # セグメントがない場合は空のフィギュアを返す
        fig = go.Figure()
        fig.update_layout(title="セグメントがありません")
        return fig
    
    fig = go.Figure()
    
    # カラーパレット
    colors = {
        'enabled': '#2E86AB',      # 有効なセグメント（青）
        'disabled': '#A0A0A0',     # 無効なセグメント（グレー）
        'gap': '#FF6B6B',          # ギャップ部分（赤）
        'timeline': '#E0E0E0',     # タイムラインの背景（薄いグレー）
        'adjusted': '#4ECDC4'      # 調整後のセグメント（青緑）
    }
    
    # タイムラインの背景を描画
    fig.add_trace(go.Scatter(
        x=[0, video_duration],
        y=[0, 0],
        mode='lines',
        line=dict(color=colors['timeline'], width=40),
        name='タイムライン',
        showlegend=False,
        hoverinfo='skip'
    ))
    
    # セグメントを描画
    y_original = 0.5  # 元のセグメントのY位置
    y_adjusted = -0.5  # 調整後のセグメントのY位置
    
    for i, segment in enumerate(timeline.segments):
        color = colors['enabled'] if segment.enabled else colors['disabled']
        
        # 元のセグメント
        fig.add_trace(go.Scatter(
            x=[segment.start_time, segment.end_time],
            y=[y_original, y_original],
            mode='lines',
            line=dict(color=color, width=20),
            name=f'セグメント {i+1}',
            showlegend=False,
            hovertemplate=(
                f'セグメント {i+1}<br>' +
                f'開始: {format_time(segment.start_time)}<br>' +
                f'終了: {format_time(segment.end_time)}<br>' +
                f'長さ: {format_time(segment.duration)}<br>' +
                '<extra></extra>'
            )
        ))
        
        # 調整後のセグメント（有効な場合のみ）
        if segment.enabled:
            # 前後のセグメントを考慮した調整後の範囲を計算
            prev_end = None
            if i > 0 and timeline.segments[i-1].enabled:
                prev_end = timeline.segments[i-1].end_time
                
            next_start = None
            if i < len(timeline.segments) - 1 and timeline.segments[i+1].enabled:
                next_start = timeline.segments[i+1].start_time
                
            adj_start, adj_end = segment.get_adjusted_range(prev_end, next_start)
            
            if adj_start is not None and adj_end is not None:
                # ギャップ部分を表示
                if adj_start < segment.start_time:
                    fig.add_trace(go.Scatter(
                        x=[adj_start, segment.start_time],
                        y=[y_adjusted, y_adjusted],
                        mode='lines',
                        line=dict(color=colors['gap'], width=15, dash='dot'),
                        name=f'前ギャップ {i+1}',
                        showlegend=False,
                        hovertemplate=(
                            f'前のギャップ<br>' +
                            f'長さ: {format_time(segment.start_time - adj_start)}<br>' +
                            '<extra></extra>'
                        )
                    ))
                
                # 調整後のセグメント本体
                fig.add_trace(go.Scatter(
                    x=[segment.start_time, segment.end_time],
                    y=[y_adjusted, y_adjusted],
                    mode='lines',
                    line=dict(color=colors['adjusted'], width=20),
                    name=f'調整後 {i+1}',
                    showlegend=False,
                    hovertemplate=(
                        f'調整後セグメント {i+1}<br>' +
                        f'開始: {format_time(adj_start)}<br>' +
                        f'終了: {format_time(adj_end)}<br>' +
                        f'長さ: {format_time(adj_end - adj_start)}<br>' +
                        '<extra></extra>'
                    )
                ))
                
                if adj_end > segment.end_time:
                    fig.add_trace(go.Scatter(
                        x=[segment.end_time, adj_end],
                        y=[y_adjusted, y_adjusted],
                        mode='lines',
                        line=dict(color=colors['gap'], width=15, dash='dot'),
                        name=f'後ギャップ {i+1}',
                        showlegend=False,
                        hovertemplate=(
                            f'後のギャップ<br>' +
                            f'長さ: {format_time(adj_end - segment.end_time)}<br>' +
                            '<extra></extra>'
                        )
                    ))
    
    # レイアウトの設定
    fig.update_layout(
        title={
            'text': 'タイムライン編集',
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis=dict(
            title='時間（秒）',
            range=[0, video_duration],
            tickformat='.1f',
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)'
        ),
        yaxis=dict(
            title='',
            range=[-1, 1],
            tickvals=[y_adjusted, y_original],
            ticktext=['調整後', '元のセグメント'],
            showgrid=False
        ),
        height=300,
        margin=dict(l=50, r=50, t=50, b=50),
        hovermode='x unified',
        showlegend=False,
        plot_bgcolor='white'
    )
    
    return fig


def render_timeline_editor(
    timeline: Timeline,
    video_duration: float,
    key_prefix: str = "timeline"
) -> Timeline:
    """
    タイムライン編集UIをレンダリング
    
    Args:
        timeline: 編集対象のタイムライン
        video_duration: 動画の総時間
        key_prefix: Streamlitのキープレフィックス
        
    Returns:
        編集後のタイムライン
    """
    st.markdown("### 🎬 タイムライン編集")
    st.markdown("各セグメント間の間隔を調整できます。元動画から追加で含める秒数を指定してください。")
    
    # タイムラインの視覚表示
    fig = create_timeline_figure(timeline, video_duration)
    st.plotly_chart(fig, use_container_width=True)
    
    # 合計時間の表示
    original_duration, adjusted_duration = timeline.get_total_duration()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("元の合計時間", format_time(original_duration))
    with col2:
        st.metric("調整後の合計時間", format_time(adjusted_duration))
    with col3:
        diff = adjusted_duration - original_duration
        st.metric("差分", format_time(abs(diff)), delta=f"{diff:+.1f}秒")
    
    # 一括設定とリセット
    st.markdown("#### 一括設定")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        all_gap_before = st.number_input(
            "全セグメントの前ギャップ（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_all_before"
        )
    
    with col2:
        all_gap_after = st.number_input(
            "全セグメントの後ギャップ（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_all_after"
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)  # スペーサー
        col3_1, col3_2 = st.columns(2)
        with col3_1:
            if st.button("一括適用", key=f"{key_prefix}_apply_all"):
                timeline.set_all_gaps(all_gap_before, all_gap_after)
                st.rerun()
        with col3_2:
            if st.button("リセット", key=f"{key_prefix}_reset_all"):
                timeline.reset_all_gaps()
                st.rerun()
    
    # 個別セグメントの調整
    st.markdown("#### 個別調整")
    
    # セグメントごとの設定をエクスパンダーで表示
    for i, segment in enumerate(timeline.segments):
        with st.expander(
            f"セグメント {i+1} ({format_time(segment.start_time)} - {format_time(segment.end_time)})",
            expanded=False
        ):
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                # 有効/無効の切り替え
                enabled = st.checkbox(
                    "このセグメントを含める",
                    value=segment.enabled,
                    key=f"{key_prefix}_enabled_{i}"
                )
                if enabled != segment.enabled:
                    segment.enabled = enabled
            
            if segment.enabled:
                with col2:
                    # 前のギャップ
                    gap_before = st.slider(
                        "前の間隔（秒）",
                        min_value=0.0,
                        max_value=2.0,
                        value=segment.gap_before,
                        step=0.1,
                        key=f"{key_prefix}_before_{i}",
                        help="このセグメントの前に含める追加時間"
                    )
                    if gap_before != segment.gap_before:
                        segment.gap_before = gap_before
                
                with col3:
                    # 後のギャップ
                    gap_after = st.slider(
                        "後の間隔（秒）",
                        min_value=0.0,
                        max_value=2.0,
                        value=segment.gap_after,
                        step=0.1,
                        key=f"{key_prefix}_after_{i}",
                        help="このセグメントの後に含める追加時間"
                    )
                    if gap_after != segment.gap_after:
                        segment.gap_after = gap_after
            
            # 調整後の範囲を表示
            if segment.enabled:
                prev_end = None
                if i > 0 and timeline.segments[i-1].enabled:
                    prev_end = timeline.segments[i-1].end_time
                    
                next_start = None
                if i < len(timeline.segments) - 1 and timeline.segments[i+1].enabled:
                    next_start = timeline.segments[i+1].start_time
                
                adj_start, adj_end = segment.get_adjusted_range(prev_end, next_start)
                
                if adj_start is not None and adj_end is not None:
                    st.info(
                        f"調整後: {format_time(adj_start)} - {format_time(adj_end)} " +
                        f"（長さ: {format_time(adj_end - adj_start)}）"
                    )
    
    return timeline