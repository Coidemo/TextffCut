"""
タイムライン編集UI
Plotlyを使用した視覚的なタイムライン表示と編集機能
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Tuple, Optional
from core.timeline import Timeline, TimelineSegment
from utils.time_utils import format_time


def create_timeline_figure(timeline: Timeline, video_duration: float) -> go.Figure:
    """タイムラインの視覚的な表示を作成
    
    Args:
        timeline: タイムラインオブジェクト
        video_duration: 元動画の総時間（秒）
        
    Returns:
        Plotly Figure
    """
    fig = go.Figure()
    
    # 背景となる全体のタイムライン
    fig.add_trace(go.Scatter(
        x=[0, video_duration],
        y=[0.5, 0.5],
        mode='lines',
        line=dict(color='lightgray', width=20),
        hoverinfo='skip',
        showlegend=False
    ))
    
    # 各セグメントを描画
    adjusted_ranges = timeline.get_adjusted_ranges()
    enabled_segments = [seg for seg in timeline.segments if seg.enabled]
    
    for i, (segment, (adj_start, adj_end)) in enumerate(zip(enabled_segments, adjusted_ranges)):
        # 元のセグメント（濃い色）
        fig.add_trace(go.Scatter(
            x=[segment.start_time, segment.end_time],
            y=[0.5, 0.5],
            mode='lines',
            line=dict(color='#1f77b4', width=15),
            name=f'セグメント {segment.index + 1}',
            hovertemplate=f'セグメント {segment.index + 1}<br>' +
                         f'開始: {format_time(segment.start_time)}<br>' +
                         f'終了: {format_time(segment.end_time)}<br>' +
                         f'長さ: {segment.duration:.1f}秒<extra></extra>',
            showlegend=False
        ))
        
        # ギャップによる拡張部分（薄い色）
        if adj_start < segment.start_time:
            fig.add_trace(go.Scatter(
                x=[adj_start, segment.start_time],
                y=[0.5, 0.5],
                mode='lines',
                line=dict(color='#7fc7ff', width=15, dash='dot'),
                hovertemplate=f'前ギャップ: {segment.gap_before:.1f}秒<extra></extra>',
                showlegend=False
            ))
        
        if adj_end > segment.end_time:
            fig.add_trace(go.Scatter(
                x=[segment.end_time, adj_end],
                y=[0.5, 0.5],
                mode='lines',
                line=dict(color='#7fc7ff', width=15, dash='dot'),
                hovertemplate=f'後ギャップ: {segment.gap_after:.1f}秒<extra></extra>',
                showlegend=False
            ))
        
        # セグメント番号を表示
        fig.add_annotation(
            x=(segment.start_time + segment.end_time) / 2,
            y=0.5,
            text=str(segment.index + 1),
            showarrow=False,
            font=dict(color='white', size=12, family='Arial Black'),
            bgcolor='#1f77b4',
            borderpad=4
        )
    
    # レイアウト設定
    fig.update_layout(
        height=150,
        margin=dict(l=20, r=20, t=20, b=40),
        xaxis=dict(
            title="時間（秒）",
            titlefont=dict(size=12),
            tickfont=dict(size=10),
            range=[0, video_duration],
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            visible=False,
            range=[0, 1]
        ),
        hovermode='x unified',
        plot_bgcolor='white'
    )
    
    return fig


def show_timeline_editor(time_ranges: List[Tuple[float, float]], video_duration: float) -> Optional[Timeline]:
    """タイムライン編集UIを表示
    
    Args:
        time_ranges: 元の時間範囲リスト
        video_duration: 動画の総時間（秒）
        
    Returns:
        編集されたTimelineオブジェクト（編集されていない場合はNone）
    """
    # 入力検証
    if not time_ranges:
        st.warning("編集可能な時間範囲がありません。")
        return None
    
    if video_duration <= 0:
        st.warning("動画の長さが不正です。")
        return None
    # タイムライン編集の説明
    st.info("🎬 各セグメント間の間隔を調整できます。元動画から追加で含める秒数を指定してください。")
    
    # セッションステートでタイムラインを管理
    if 'timeline' not in st.session_state or st.session_state.get('timeline_time_ranges') != time_ranges:
        st.session_state.timeline = Timeline(time_ranges)
        st.session_state.timeline_time_ranges = time_ranges
    
    timeline = st.session_state.timeline
    
    # タイムライン表示
    fig = create_timeline_figure(timeline, video_duration)
    st.plotly_chart(fig, use_container_width=True)
    
    # 一括設定とリセットボタン
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        bulk_gap = st.number_input(
            "一括ギャップ設定（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            help="全セグメントのギャップを一括で設定します"
        )
    
    with col2:
        if st.button("一括適用", use_container_width=True):
            timeline.set_all_gaps(bulk_gap)
            st.rerun()
    
    with col3:
        if st.button("リセット", use_container_width=True):
            timeline.reset_all_gaps()
            st.rerun()
    
    # 各セグメントの個別調整
    st.markdown("### 📏 セグメント別調整")
    
    # タブで各セグメントを表示
    if len(timeline.segments) > 5:
        # セグメントが多い場合はエキスパンダーで表示
        for segment in timeline.segments:
            with st.expander(f"セグメント {segment.index + 1} ({format_time(segment.start_time)} - {format_time(segment.end_time)})", 
                           expanded=False):
                show_segment_controls(segment, timeline)
    else:
        # セグメントが少ない場合は直接表示
        for i, segment in enumerate(timeline.segments):
            if i > 0:
                st.markdown("---")
            st.markdown(f"#### セグメント {segment.index + 1}")
            st.caption(f"{format_time(segment.start_time)} - {format_time(segment.end_time)} ({segment.duration:.1f}秒)")
            show_segment_controls(segment, timeline)
    
    # 統計情報を表示
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("有効セグメント数", f"{timeline.get_enabled_count()}/{len(timeline.segments)}")
    
    with col2:
        original_duration = sum(seg.duration for seg in timeline.segments if seg.enabled)
        st.metric("元の合計時間", f"{original_duration:.1f}秒")
    
    with col3:
        adjusted_duration = timeline.get_total_duration()
        diff = adjusted_duration - original_duration
        st.metric("調整後の合計時間", f"{adjusted_duration:.1f}秒", delta=f"{diff:+.1f}秒")
    
    return timeline


def show_segment_controls(segment: TimelineSegment, timeline: Timeline):
    """個別セグメントのコントロールを表示
    
    Args:
        segment: 表示するセグメント
        timeline: 親のタイムラインオブジェクト
    """
    # 有効/無効の切り替え
    col1, col2, col3 = st.columns([1, 2, 2])
    
    with col1:
        enabled = st.checkbox(
            "有効",
            value=segment.enabled,
            key=f"enabled_{segment.index}",
            help="このセグメントを含めるかどうか"
        )
        if enabled != segment.enabled:
            segment.enabled = enabled
            st.rerun()
    
    with col2:
        gap_before = st.slider(
            "前ギャップ（秒）",
            min_value=0.0,
            max_value=2.0,
            value=segment.gap_before,
            step=0.1,
            key=f"gap_before_{segment.index}",
            disabled=not segment.enabled,
            help="前のセグメントとの間から追加で取得する秒数"
        )
        if gap_before != segment.gap_before:
            segment.gap_before = gap_before
    
    with col3:
        gap_after = st.slider(
            "後ギャップ（秒）",
            min_value=0.0,
            max_value=2.0,
            value=segment.gap_after,
            step=0.1,
            key=f"gap_after_{segment.index}",
            disabled=not segment.enabled,
            help="次のセグメントとの間まで追加で取得する秒数"
        )
        if gap_after != segment.gap_after:
            segment.gap_after = gap_after