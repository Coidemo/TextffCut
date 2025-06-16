import streamlit as st
import plotly.graph_objects as go
from typing import List, Tuple, Optional, Dict
from core.timeline import Timeline, TimelineSegment
import numpy as np


def create_timeline_figure(timeline: Timeline, video_duration: float) -> go.Figure:
    """
    Plotlyを使用してタイムラインの視覚的表現を作成
    
    Args:
        timeline: タイムラインオブジェクト
        video_duration: 元動画の総時間（秒）
    """
    fig = go.Figure()
    
    # 有効なセグメントを取得
    enabled_segments = timeline.get_enabled_segments()
    adjusted_ranges = timeline.get_adjusted_ranges()
    
    # Y軸の位置
    original_y = 1
    adjusted_y = 0
    
    # 元のセグメントを描画（青）
    for i, segment in enumerate(enabled_segments):
        fig.add_trace(go.Scatter(
            x=[segment.start_time, segment.end_time],
            y=[original_y, original_y],
            mode='lines',
            line=dict(color='blue', width=20),
            name=f'セグメント {segment.index + 1}',
            hovertemplate=f'セグメント {segment.index + 1}<br>開始: %{{x:.2f}}秒<br>長さ: {segment.duration:.2f}秒',
            showlegend=False
        ))
    
    # 調整後のセグメントを描画（青緑）
    for i, (start, end) in enumerate(adjusted_ranges):
        fig.add_trace(go.Scatter(
            x=[start, end],
            y=[adjusted_y, adjusted_y],
            mode='lines',
            line=dict(color='cyan', width=20),
            name=f'調整後 {i + 1}',
            hovertemplate=f'調整後セグメント {i + 1}<br>開始: %{{x:.2f}}秒<br>長さ: {end - start:.2f}秒',
            showlegend=False
        ))
    
    # ギャップを示す点線（赤）
    for i, segment in enumerate(enabled_segments):
        if segment.gap_before > 0:
            fig.add_trace(go.Scatter(
                x=[segment.start_time - segment.gap_before, segment.start_time],
                y=[adjusted_y, adjusted_y],
                mode='lines',
                line=dict(color='red', width=2, dash='dot'),
                hovertemplate=f'前ギャップ: {segment.gap_before:.2f}秒',
                showlegend=False
            ))
        if segment.gap_after > 0:
            fig.add_trace(go.Scatter(
                x=[segment.end_time, segment.end_time + segment.gap_after],
                y=[adjusted_y, adjusted_y],
                mode='lines',
                line=dict(color='red', width=2, dash='dot'),
                hovertemplate=f'後ギャップ: {segment.gap_after:.2f}秒',
                showlegend=False
            ))
    
    # レイアウト設定
    fig.update_layout(
        title=dict(text="タイムライン編集", font=dict(size=16)),
        xaxis=dict(
            title="時間（秒）",
            range=[0, video_duration],
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title="",
            range=[-0.5, 1.5],
            showticklabels=False,
            showgrid=False
        ),
        height=250,
        margin=dict(l=50, r=50, t=50, b=50),
        hovermode='x unified',
        plot_bgcolor='white'
    )
    
    # Y軸のラベルを追加
    fig.add_annotation(x=-0.05, y=original_y, text="元", xref="paper", yref="y", showarrow=False)
    fig.add_annotation(x=-0.05, y=adjusted_y, text="調整後", xref="paper", yref="y", showarrow=False)
    
    return fig


def render_timeline_editor(timeline: Timeline, video_duration: float, key_prefix: str = "") -> Timeline:
    """
    タイムライン編集UIをレンダリング
    
    Args:
        timeline: 編集対象のタイムライン
        video_duration: 元動画の総時間（秒）
        key_prefix: StreamlitのキーのプレフィックスKey prefix for avoiding conflicts
        
    Returns:
        編集後のタイムライン
    """
    st.subheader("🎬 タイムライン編集")
    
    # タイムラインの視覚表示
    if timeline.segments:
        fig = create_timeline_figure(timeline, video_duration)
        st.plotly_chart(fig, use_container_width=True)
    
    # 時間表示
    col1, col2, col3 = st.columns(3)
    with col1:
        original_duration = timeline.get_total_duration(adjusted=False)
        st.metric("元の合計時間", f"{original_duration:.2f} 秒")
    with col2:
        adjusted_duration = timeline.get_total_duration(adjusted=True)
        st.metric("調整後の合計時間", f"{adjusted_duration:.2f} 秒")
    with col3:
        diff = adjusted_duration - original_duration
        st.metric("差分", f"{diff:+.2f} 秒")
    
    # 一括操作ボタン
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 すべてリセット", key=f"{key_prefix}_reset_all"):
            timeline.reset_all_gaps()
            st.rerun()
    
    with col2:
        batch_gap = st.number_input(
            "一括設定値（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_batch_gap"
        )
    
    with col3:
        if st.button("📋 一括設定", key=f"{key_prefix}_apply_all"):
            timeline.set_all_gaps(batch_gap)
            st.rerun()
    
    # 各セグメントの個別調整
    st.write("### 📊 セグメント個別調整")
    
    enabled_segments = timeline.get_enabled_segments()
    adjusted_ranges = timeline.get_adjusted_ranges()
    
    for i, segment in enumerate(timeline.segments):
        with st.expander(f"セグメント {segment.index + 1} ({segment.start_time:.2f}秒 - {segment.end_time:.2f}秒)", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                # ギャップ調整
                st.write("**ギャップ調整**")
                
                # 前のセグメントとのギャップ
                gap_before = st.slider(
                    "前のギャップ（秒）",
                    min_value=0.0,
                    max_value=2.0,
                    value=segment.gap_before,
                    step=0.1,
                    key=f"{key_prefix}_gap_before_{i}",
                    help="このセグメントの開始を早める秒数"
                )
                segment.gap_before = gap_before
                
                # 次のセグメントとのギャップ
                gap_after = st.slider(
                    "後のギャップ（秒）",
                    min_value=0.0,
                    max_value=2.0,
                    value=segment.gap_after,
                    step=0.1,
                    key=f"{key_prefix}_gap_after_{i}",
                    help="このセグメントの終了を遅らせる秒数"
                )
                segment.gap_after = gap_after
                
                # 調整後の範囲を表示
                if segment.enabled and i < len(adjusted_ranges):
                    adj_start, adj_end = adjusted_ranges[i]
                    st.info(f"調整後: {adj_start:.2f}秒 - {adj_end:.2f}秒 (長さ: {adj_end - adj_start:.2f}秒)")
            
            with col2:
                # 有効/無効の切り替え
                segment.enabled = st.checkbox(
                    "有効",
                    value=segment.enabled,
                    key=f"{key_prefix}_enabled_{i}"
                )
                
                # セグメント情報
                st.write(f"**元の長さ**: {segment.duration:.2f}秒")
    
    return timeline