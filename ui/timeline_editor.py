"""Timeline editor UI component for video segment management."""

import streamlit as st
from typing import List, Tuple, Optional
import plotly.graph_objects as go
from core.timeline import Timeline, TimelineSegment


def format_time(seconds: float) -> str:
    """Format time in seconds to MM:SS format."""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


def create_timeline_visualization(timeline: Timeline) -> go.Figure:
    """Create a visual timeline using Plotly."""
    fig = go.Figure()
    
    # Get segment positions for visualization
    positions = timeline.get_segment_positions()
    
    # Define colors
    segment_color = "#4CAF50"
    gap_color = "#FFC107"
    disabled_color = "#9E9E9E"
    
    y_center = 1
    bar_height = 0.4
    
    # Draw segments and gaps
    for i, segment in enumerate(timeline.segments):
        if not segment.enabled:
            continue
            
        # Find position in output timeline
        pos_info = next(p for p in positions if p[0] == segment.index)
        _, start_pos, end_pos = pos_info
        
        # Draw segment rectangle
        fig.add_shape(
            type="rect",
            x0=start_pos,
            x1=end_pos,
            y0=y_center - bar_height/2,
            y1=y_center + bar_height/2,
            fillcolor=segment_color if segment.enabled else disabled_color,
            line=dict(color="black", width=1),
        )
        
        # Add segment label
        fig.add_annotation(
            x=(start_pos + end_pos) / 2,
            y=y_center,
            text=f"S{segment.index + 1}",
            showarrow=False,
            font=dict(color="white", size=12),
        )
        
        # Draw gap after segment (if not last)
        if segment.gap_after > 0 and i < len(timeline.segments) - 1:
            gap_start = end_pos
            gap_end = end_pos + segment.gap_after
            
            # Gap visualization (dotted line)
            fig.add_shape(
                type="line",
                x0=gap_start,
                x1=gap_end,
                y0=y_center,
                y1=y_center,
                line=dict(color=gap_color, width=3, dash="dot"),
            )
            
            # Gap label
            fig.add_annotation(
                x=(gap_start + gap_end) / 2,
                y=y_center + 0.3,
                text=f"{segment.gap_after:.1f}s",
                showarrow=False,
                font=dict(color=gap_color, size=10),
            )
    
    # Configure layout
    total_duration = timeline.get_total_duration()
    fig.update_layout(
        title="セグメントタイムライン",
        xaxis=dict(
            title="時間 (秒)",
            range=[0, max(total_duration * 1.1, 10)],
            tickmode="linear",
            tick0=0,
            dtick=max(total_duration / 10, 1),
        ),
        yaxis=dict(
            visible=False,
            range=[0, 2],
        ),
        height=200,
        margin=dict(l=50, r=50, t=50, b=50),
        showlegend=False,
    )
    
    return fig


def render_timeline_editor(timeline: Timeline) -> Timeline:
    """Render the timeline editor UI and return updated timeline."""
    
    st.subheader("🎬 タイムライン編集")
    
    # Display timeline visualization
    if timeline.segments:
        fig = create_timeline_visualization(timeline)
        st.plotly_chart(fig, use_container_width=True)
    
    # Gap adjustment controls
    st.markdown("### つなぎ目の調整")
    
    # Create columns for segment controls
    enabled_segments = timeline.get_enabled_segments()
    
    if len(enabled_segments) > 1:
        for i in range(len(enabled_segments) - 1):
            segment = enabled_segments[i]
            next_segment = enabled_segments[i + 1]
            
            with st.container():
                col1, col2, col3 = st.columns([2, 3, 1])
                
                with col1:
                    st.markdown(
                        f"**セグメント{segment.index + 1} → セグメント{next_segment.index + 1}**"
                    )
                
                with col2:
                    # Gap adjustment slider
                    new_gap = st.slider(
                        "間隔 (秒)",
                        min_value=0.0,
                        max_value=2.0,
                        value=segment.gap_after,
                        step=0.1,
                        key=f"gap_{segment.index}",
                        label_visibility="collapsed",
                    )
                    segment.gap_after = new_gap
                
                with col3:
                    st.markdown(f"{new_gap:.1f}秒")
            
            st.divider()
    else:
        st.info("セグメントが1つのみのため、つなぎ目の調整はありません。")
    
    # Batch operations
    st.markdown("### 一括操作")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("すべてリセット", use_container_width=True):
            for segment in timeline.segments:
                segment.gap_after = 0.0
            st.rerun()
    
    with col2:
        # Batch gap setting
        batch_gap = st.number_input(
            "一括設定値 (秒)",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            label_visibility="collapsed",
        )
        if st.button("一括設定", use_container_width=True):
            for segment in timeline.segments[:-1]:  # Not for last segment
                segment.gap_after = batch_gap
            st.rerun()
    
    with col3:
        # Preview total duration
        total_duration = timeline.get_total_duration()
        st.metric("合計時間", format_time(total_duration))
    
    # Segment management (enable/disable)
    with st.expander("セグメント管理"):
        st.markdown("各セグメントの有効/無効を切り替えます。")
        
        for segment in timeline.segments:
            col1, col2 = st.columns([1, 4])
            
            with col1:
                segment.enabled = st.checkbox(
                    "",
                    value=segment.enabled,
                    key=f"enable_{segment.index}",
                )
            
            with col2:
                status = "有効" if segment.enabled else "無効"
                st.markdown(
                    f"**セグメント{segment.index + 1}** "
                    f"({format_time(segment.start)} - {format_time(segment.end)}) "
                    f"[{status}]"
                )
    
    return timeline


def should_show_timeline_editor() -> bool:
    """Check if timeline editor should be shown."""
    return (
        st.session_state.get("target_ranges") is not None
        and len(st.session_state.get("target_ranges", [])) > 0
    )