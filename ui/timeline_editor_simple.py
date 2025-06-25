"""
シンプルな横並びタイムライン編集UI
DaVinci Resolve風の直感的な操作を目指す
"""

from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.waveform_processor import WaveformProcessor
from services.timeline_editing_service import TimelineEditingService
from ui.timeline_dark_mode_fix import inject_dark_mode_css
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def render_simple_timeline_editor(
    time_ranges: list[tuple[float, float]], transcription_result: dict[str, Any], video_path: str
) -> None:
    """
    シンプルな横並びタイムライン編集UIをレンダリング

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
    st.markdown("### 📝 タイムライン編集")
    st.markdown("セグメントの境界をスライダーで調整してください")

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

    # 横並び波形表示
    render_combined_waveform(video_path, time_ranges, service)

    st.divider()

    # セグメント調整UI
    render_segment_adjusters(time_ranges, service)

    # 操作ボタン
    st.divider()
    render_action_buttons(service)


def render_combined_waveform(video_path: str, time_ranges: list[tuple[float, float]], service: TimelineEditingService):
    """全セグメントの波形を横並びで表示"""

    with st.spinner("波形データを読み込み中..."):
        # 波形プロセッサーの初期化
        waveform_processor = WaveformProcessor()

        # 全セグメントの波形データを取得
        fig = go.Figure()

        # ダークモード用の色設定
        is_dark_mode = st.get_option("theme.base") == "dark"
        bg_color = "#0E1117" if is_dark_mode else "#FFFFFF"
        text_color = "#FAFAFA" if is_dark_mode else "#262730"
        wave_color = "#26C6DA" if is_dark_mode else "#1F77B4"
        segment_color = "#FF6B6B" if is_dark_mode else "#FF4444"

        current_x_offset = 0
        segment_boundaries = [0]  # セグメント境界の位置

        for i, (start, end) in enumerate(time_ranges):
            # 波形データの取得
            try:
                waveform_data = waveform_processor.extract_waveform(video_path, start, end, f"segment_{i+1}")
                
                # waveform_dataはWaveformDataオブジェクトとして返される
                if waveform_data and waveform_data.samples and len(waveform_data.samples) > 0:
                    # 時間軸を作成
                    duration = end - start
                    time_points = np.linspace(0, duration, len(waveform_data.samples))
                    adjusted_time = time_points + current_x_offset

                    # 波形を追加
                    fig.add_trace(
                        go.Scatter(
                            x=adjusted_time,
                            y=waveform_data.samples,
                            mode="lines",
                            name=f"セグメント {i+1}",
                            line=dict(color=wave_color, width=1),
                            fill="tozeroy",
                            hovertemplate="時間: %{x:.2f}秒<br>振幅: %{y:.3f}<extra></extra>",
                        )
                    )

                    # 次のセグメントのオフセット
                    current_x_offset += duration
                    segment_boundaries.append(current_x_offset)
                else:
                    # 波形データがない場合も境界を追加
                    duration = end - start
                    current_x_offset += duration
                    segment_boundaries.append(current_x_offset)
            except Exception as e:
                logger.error(f"波形データ取得エラー (セグメント{i+1}): {e}")
                # エラーの場合も境界を追加
                duration = end - start
                current_x_offset += duration
                segment_boundaries.append(current_x_offset)

        # セグメント境界を縦線で表示
        for i, boundary in enumerate(segment_boundaries[1:-1]):  # 最初と最後を除く
            fig.add_vline(
                x=boundary,
                line_color=segment_color,
                line_width=2,
                line_dash="dash",
                annotation_text=f"境界 {i+1}",
                annotation_position="top",
            )

        # レイアウト設定
        fig.update_layout(
            title="全セグメントの波形表示",
            xaxis_title="時間 (秒)",
            yaxis_title="振幅",
            height=300,
            showlegend=False,
            paper_bgcolor=bg_color,
            plot_bgcolor=bg_color,
            font=dict(color=text_color),
            xaxis=dict(
                showgrid=True, gridcolor="rgba(128,128,128,0.2)", zeroline=True, zerolinecolor="rgba(128,128,128,0.2)"
            ),
            yaxis=dict(
                showgrid=True, gridcolor="rgba(128,128,128,0.2)", zeroline=True, zerolinecolor="rgba(128,128,128,0.2)"
            ),
        )

        # グラフを表示
        st.plotly_chart(fig, use_container_width=True)


def render_segment_adjusters(time_ranges: list[tuple[float, float]], service: TimelineEditingService):
    """セグメントの境界調整UI"""

    st.markdown("#### 🎚️ セグメント境界の調整")

    timeline_data = st.session_state.get("timeline_data", {})
    segments = timeline_data.get("segments", [])
    video_duration = timeline_data.get("video_duration", 0)

    if not segments:
        st.warning("セグメントデータがありません")
        return

    # 各セグメントの境界を調整
    updated_ranges = []

    for i, segment_data in enumerate(segments):
        segment_id = segment_data["id"]
        current_start = segment_data["start"]
        current_end = segment_data["end"]

        # 前後のセグメントの制約を取得
        min_start = 0.0 if i == 0 else updated_ranges[-1][1] + 0.1
        max_end = video_duration if i == len(segments) - 1 else segments[i + 1]["start"] - 0.1

        st.markdown(f"**セグメント {i+1}** ({format_time(current_start)} - {format_time(current_end)})")

        col1, col2 = st.columns(2)

        with col1:
            new_start = st.slider(
                "開始時間",
                min_value=min_start,
                max_value=current_end - 0.1,
                value=current_start,
                step=0.1,
                format="%.1f秒",
                key=f"start_{segment_id}",
            )

        with col2:
            new_end = st.slider(
                "終了時間",
                min_value=new_start + 0.1,
                max_value=max_end,
                value=current_end,
                step=0.1,
                format="%.1f秒",
                key=f"end_{segment_id}",
            )

        # 値が変更された場合は更新
        if new_start != current_start or new_end != current_end:
            service.set_segment_time_range(segment_id, new_start, new_end)

        updated_ranges.append((new_start, new_end))

        # セグメントのテキストを表示
        with st.expander("テキスト内容", expanded=False):
            st.text(segment_data.get("text", ""))

        st.divider()


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
            st.rerun()

    with col3:
        if st.button("❌ キャンセル", use_container_width=True):
            st.session_state.timeline_editing_cancelled = True
            cleanup_session_state()
            st.rerun()


def cleanup_session_state():
    """セッション状態をクリーンアップ"""
    keys_to_remove = ["timeline_initialized", "timeline_data", "selected_segment_id"]

    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]
