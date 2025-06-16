"""
タイムライン編集UI
Plotlyを使用した視覚的なタイムライン表示と調整機能
"""
import streamlit as st
import plotly.graph_objects as go
from typing import List, Tuple, Optional
from core.timeline import Timeline, TimelineSegment
from utils.time_utils import format_time


def create_timeline_figure(timeline: Timeline) -> go.Figure:
    """タイムラインの視覚的表現を作成
    
    Args:
        timeline: タイムラインオブジェクト
        
    Returns:
        Plotlyのfigureオブジェクト
    """
    fig = go.Figure()
    
    # 元のセグメントを青で表示
    original_x = []
    original_y = []
    original_text = []
    
    # 調整後のセグメントを青緑で表示
    adjusted_x = []
    adjusted_y = []
    adjusted_text = []
    
    # ギャップ部分を赤い点線で表示
    gap_shapes = []
    
    adjusted_ranges = timeline.get_adjusted_ranges()
    
    for i, segment in enumerate(timeline.segments):
        if not segment.enabled:
            continue
            
        # 元のセグメント
        original_x.extend([segment.original_start, segment.original_end, None])
        original_y.extend([1, 1, None])
        original_text.append(
            f"セグメント {i+1}<br>"
            f"開始: {format_time(segment.original_start)}<br>"
            f"終了: {format_time(segment.original_end)}<br>"
            f"長さ: {segment.duration:.1f}秒"
        )
        
        # 調整後のセグメント
        if i < len(adjusted_ranges):
            adj_start, adj_end = adjusted_ranges[i]
            adjusted_x.extend([adj_start, adj_end, None])
            adjusted_y.extend([0.5, 0.5, None])
            adjusted_text.append(
                f"調整後セグメント {i+1}<br>"
                f"開始: {format_time(adj_start)}<br>"
                f"終了: {format_time(adj_end)}<br>"
                f"長さ: {adj_end - adj_start:.1f}秒"
            )
            
            # ギャップを点線で表示
            if segment.gap_before > 0:
                gap_shapes.append(dict(
                    type="line",
                    x0=segment.original_start,
                    y0=1,
                    x1=adj_start,
                    y1=0.5,
                    line=dict(color="red", width=2, dash="dot")
                ))
            
            if segment.gap_after > 0:
                gap_shapes.append(dict(
                    type="line",
                    x0=segment.original_end,
                    y0=1,
                    x1=adj_end,
                    y1=0.5,
                    line=dict(color="red", width=2, dash="dot")
                ))
    
    # 元のセグメントを追加
    fig.add_trace(go.Scatter(
        x=original_x,
        y=original_y,
        mode='lines',
        name='元のセグメント',
        line=dict(color='blue', width=8),
        hovertemplate='%{text}<extra></extra>',
        text=original_text * (len(original_x) // 3)
    ))
    
    # 調整後のセグメントを追加
    fig.add_trace(go.Scatter(
        x=adjusted_x,
        y=adjusted_y,
        mode='lines',
        name='調整後',
        line=dict(color='cyan', width=8),
        hovertemplate='%{text}<extra></extra>',
        text=adjusted_text * (len(adjusted_x) // 3)
    ))
    
    # レイアウト設定
    fig.update_layout(
        title="タイムライン調整ビュー",
        xaxis=dict(
            title="時間（秒）",
            range=[0, timeline.video_duration],
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title="",
            range=[0, 1.5],
            showticklabels=False,
            showgrid=False
        ),
        height=300,
        hovermode='x',
        shapes=gap_shapes,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig


def show_timeline_editor(timeline: Timeline, key_prefix: str = "timeline") -> Timeline:
    """タイムライン編集UIを表示
    
    Args:
        timeline: タイムラインオブジェクト
        key_prefix: Streamlitのkey prefix
        
    Returns:
        編集されたタイムライン
    """
    st.markdown("### 🎬 タイムライン編集")
    
    # タイムラインの視覚表示
    fig = create_timeline_figure(timeline)
    st.plotly_chart(fig, use_container_width=True)
    
    # 調整前後の合計時間を表示
    original_duration = sum(seg.duration for seg in timeline.segments if seg.enabled)
    adjusted_duration = timeline.get_total_duration()
    duration_diff = adjusted_duration - original_duration
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("元の合計時間", f"{original_duration:.1f}秒")
    with col2:
        st.metric("調整後の合計時間", f"{adjusted_duration:.1f}秒")
    with col3:
        st.metric("差分", f"{duration_diff:+.1f}秒")
    
    # 一括設定とリセット
    st.markdown("#### 🎛️ 一括設定")
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        bulk_gap = st.slider(
            "全セグメントの間隔",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_bulk_gap",
            help="すべてのセグメント間に同じ間隔を設定します"
        )
    
    with col2:
        if st.button("一括適用", key=f"{key_prefix}_apply_bulk"):
            timeline.set_all_gaps(bulk_gap)
            st.rerun()
    
    with col3:
        if st.button("リセット", key=f"{key_prefix}_reset"):
            timeline.reset_gaps()
            st.rerun()
    
    # 個別セグメント調整
    st.markdown("#### 🎚️ 個別調整")
    
    # セグメントごとの調整UI
    for i, segment in enumerate(timeline.segments):
        with st.expander(f"セグメント {i+1} ({format_time(segment.original_start)} - {format_time(segment.original_end)})", expanded=False):
            # 有効/無効の切り替え
            col1, col2 = st.columns([1, 3])
            
            with col1:
                enabled = st.checkbox(
                    "有効",
                    value=segment.enabled,
                    key=f"{key_prefix}_enabled_{i}"
                )
                if enabled != segment.enabled:
                    timeline.toggle_segment(i)
                    st.rerun()
            
            with col2:
                if segment.enabled:
                    # 前後のギャップ調整
                    gap_col1, gap_col2 = st.columns(2)
                    
                    with gap_col1:
                        # 最初のセグメントは前のギャップなし
                        if i > 0:
                            gap_before = st.slider(
                                "前のセグメントとの間隔（秒）",
                                min_value=0.0,
                                max_value=2.0,
                                value=segment.gap_before,
                                step=0.1,
                                key=f"{key_prefix}_gap_before_{i}"
                            )
                            if gap_before != segment.gap_before:
                                timeline.set_gap(i, gap_before=gap_before)
                        else:
                            st.info("最初のセグメント")
                    
                    with gap_col2:
                        # 最後のセグメントは後のギャップなし
                        if i < len(timeline.segments) - 1:
                            gap_after = st.slider(
                                "次のセグメントとの間隔（秒）",
                                min_value=0.0,
                                max_value=2.0,
                                value=segment.gap_after,
                                step=0.1,
                                key=f"{key_prefix}_gap_after_{i}"
                            )
                            if gap_after != segment.gap_after:
                                timeline.set_gap(i, gap_after=gap_after)
                        else:
                            st.info("最後のセグメント")
                    
                    # 調整後の範囲を表示
                    adjusted_ranges = timeline.get_adjusted_ranges()
                    if i < len(adjusted_ranges):
                        adj_start, adj_end = adjusted_ranges[i]
                        st.info(f"調整後: {format_time(adj_start)} - {format_time(adj_end)} ({adj_end - adj_start:.1f}秒)")
                else:
                    st.warning("このセグメントは無効化されています")
    
    return timeline