"""タイムライン編集UI

Plotlyを使用して視覚的なタイムライン表示と
セグメント間のギャップ調整機能を提供します。
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional

from core.timeline import Timeline, TimelineSegment


def show_timeline_editor(timeline: Timeline) -> Timeline:
    """タイムライン編集UIを表示
    
    Args:
        timeline: 編集対象のタイムライン
        
    Returns:
        編集後のタイムライン
    """
    st.markdown("### 🎬 タイムライン編集")
    st.markdown("各セグメント間の間隔を調整できます。間隔を増やすと、元動画からより多くの部分が含まれます。")
    
    # タイムラインのコピーを作成（編集用）
    if 'edited_timeline' not in st.session_state:
        st.session_state.edited_timeline = timeline.clone()
    
    edited_timeline = st.session_state.edited_timeline
    
    # タイムライン表示
    col1, col2 = st.columns([3, 1])
    
    with col1:
        fig = create_timeline_figure(edited_timeline)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # 一括設定
        st.markdown("#### 一括設定")
        gap_value = st.number_input(
            "全ギャップ（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key="uniform_gap"
        )
        
        col_apply, col_reset = st.columns(2)
        with col_apply:
            if st.button("一括適用", use_container_width=True):
                edited_timeline.set_uniform_gap(gap_value)
                st.rerun()
        
        with col_reset:
            if st.button("リセット", use_container_width=True):
                edited_timeline.reset_gaps()
                st.rerun()
    
    # 個別調整
    st.markdown("#### 個別調整")
    
    # 有効なセグメントのみ表示
    enabled_segments = [s for s in edited_timeline.segments if s.enabled]
    
    if len(enabled_segments) > 1:
        # セグメント間の調整UI
        for i in range(len(enabled_segments) - 1):
            current = enabled_segments[i]
            next_seg = enabled_segments[i + 1]
            
            with st.expander(f"セグメント{current.index + 1} → セグメント{next_seg.index + 1}"):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    # 現在のセグメントの後のギャップ
                    new_gap_after = st.slider(
                        f"セグメント{current.index + 1}の後の余白（秒）",
                        min_value=0.0,
                        max_value=2.0,
                        value=current.gap_after,
                        step=0.1,
                        key=f"gap_after_{current.index}"
                    )
                    if new_gap_after != current.gap_after:
                        current.gap_after = new_gap_after
                
                with col2:
                    # 次のセグメントの前のギャップ
                    new_gap_before = st.slider(
                        f"セグメント{next_seg.index + 1}の前の余白（秒）",
                        min_value=0.0,
                        max_value=2.0,
                        value=next_seg.gap_before,
                        step=0.1,
                        key=f"gap_before_{next_seg.index}"
                    )
                    if new_gap_before != next_seg.gap_before:
                        next_seg.gap_before = new_gap_before
                
                with col3:
                    total_gap = current.gap_after + next_seg.gap_before
                    st.metric("合計間隔", f"{total_gap:.1f}秒")
                
                # 元動画での実際の間隔を表示
                actual_gap = next_seg.original_start - current.original_end
                if actual_gap > 0:
                    st.info(f"💡 元動画での実際の間隔: {actual_gap:.1f}秒")
                else:
                    st.info("💡 元動画では連続しています")
    
    # セグメントの有効/無効切り替え
    st.markdown("#### セグメントの有効/無効")
    
    cols = st.columns(min(4, len(edited_timeline.segments)))
    for i, segment in enumerate(edited_timeline.segments):
        with cols[i % 4]:
            enabled = st.checkbox(
                f"セグメント{segment.index + 1}",
                value=segment.enabled,
                key=f"enabled_{segment.index}"
            )
            if enabled != segment.enabled:
                segment.enabled = enabled
                st.rerun()
    
    return edited_timeline


def create_timeline_figure(timeline: Timeline) -> go.Figure:
    """タイムラインの視覚表現を作成"""
    fig = go.Figure()
    
    display_data = timeline.get_timeline_display_data()
    
    # セグメントを描画
    for segment in display_data['segments']:
        fig.add_trace(go.Scatter(
            x=[segment['start'], segment['end']],
            y=[0.5, 0.5],
            mode='lines',
            line=dict(color='blue', width=40),
            name=segment['label'],
            hovertemplate=(
                f"{segment['label']}<br>"
                f"元動画: {segment['original_start']:.1f}秒 - {segment['original_end']:.1f}秒<br>"
                f"長さ: {segment['end'] - segment['start']:.1f}秒"
                "<extra></extra>"
            )
        ))
        
        # セグメント名を表示
        fig.add_annotation(
            x=(segment['start'] + segment['end']) / 2,
            y=0.5,
            text=f"S{segment['index'] + 1}",
            showarrow=False,
            font=dict(color='white', size=12),
            bgcolor='blue',
            bordercolor='blue'
        )
    
    # ギャップマーカーを描画
    for gap in display_data['gaps']:
        if gap['duration'] > 0:
            fig.add_trace(go.Scatter(
                x=[gap['position']],
                y=[0.5],
                mode='markers',
                marker=dict(
                    symbol='line-ns',
                    size=20,
                    color='red',
                    line=dict(width=2)
                ),
                name=f"ギャップ{gap['index'] + 1}",
                hovertemplate=f"間隔: {gap['duration']:.1f}秒<extra></extra>"
            ))
    
    # レイアウト設定
    fig.update_layout(
        xaxis=dict(
            title="時間（秒）",
            range=[-1, display_data['total_duration'] + 1],
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            range=[0, 1],
            showticklabels=False,
            showgrid=False
        ),
        height=150,
        margin=dict(l=0, r=0, t=20, b=40),
        showlegend=False,
        plot_bgcolor='white'
    )
    
    return fig