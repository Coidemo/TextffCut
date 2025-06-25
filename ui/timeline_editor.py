"""
タイムライン編集UIコンポーネント
波形表示とキーボードショートカット機能を含む統合版
"""

import os
from typing import Any

import streamlit as st

from core.timeline_processor import TimelineSegment
from core.waveform_processor import WaveformProcessor
from services.timeline_editing_service import TimelineEditingService
from ui.keyboard_handler import KeyboardShortcuts, inject_keyboard_handler_script
from ui.timeline_dark_mode_fix import inject_dark_mode_css
from ui.waveform_display import WaveformDisplay
from ui.waveform_interaction import WaveformInteraction, WaveformPlayback
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def render_timeline_editor(
    time_ranges: list[tuple[float, float]], transcription_result: dict[str, Any], video_path: str
) -> list[tuple[float, float]] | None:
    """
    タイムライン編集UIをレンダリング

    Args:
        time_ranges: 初期の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス

    Returns:
        調整後の時間範囲リスト（キャンセルされた場合はNone）
    """
    # ダークモード用のCSS注入
    inject_dark_mode_css()

    service = TimelineEditingService()

    # キーボードハンドラーの初期化
    if "keyboard_shortcuts" not in st.session_state:
        st.session_state.keyboard_shortcuts = KeyboardShortcuts()

    keyboard = st.session_state.keyboard_shortcuts

    # インタラクション管理の初期化
    if "waveform_interaction" not in st.session_state:
        st.session_state.waveform_interaction = WaveformInteraction()

    interaction = st.session_state.waveform_interaction

    # 再生制御の初期化
    if "playback_control" not in st.session_state:
        st.session_state.playback_control = WaveformPlayback()

    playback = st.session_state.playback_control

    # JavaScriptの注入（キーボードイベント用）
    inject_keyboard_handler_script()

    # タイムラインの初期化
    if "timeline_initialized" not in st.session_state:
        result = service.initialize_timeline(time_ranges, transcription_result, video_path)
        if result["success"]:
            st.session_state.timeline_initialized = True
        else:
            st.error("タイムラインの初期化に失敗しました")
            return None

    # UIヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### 📝 タイムライン編集")
    with col2:
        with st.expander("⌨️ ショートカット"):
            st.markdown(keyboard.get_help_text())

    st.markdown("波形表示とインタラクティブ操作で、より直感的な編集が可能です")

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

    # メインレイアウト（2カラム）
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("#### 📋 セグメントリスト")

        if "timeline_data" in st.session_state:
            timeline_data = st.session_state.timeline_data
            segments_data = timeline_data.get("segments", [])

            if segments_data:
                # セグメントリストの表示
                for i, seg_data in enumerate(segments_data):
                    segment = TimelineSegment.from_dict(seg_data)

                    # セグメントカード
                    with st.container():
                        if st.button(
                            f"**{segment.id}** | {format_time(segment.start)} - {format_time(segment.end)}",
                            key=f"seg_button_{segment.id}",
                            use_container_width=True,
                        ):
                            st.session_state.selected_segment_id = segment.id

                        # 選択中のセグメントはハイライト
                        if st.session_state.get("selected_segment_id") == segment.id:
                            st.markdown("📍 **選択中**")
                            st.caption(segment.text[:50] + "..." if len(segment.text) > 50 else segment.text)

    with col_right:
        if "timeline_data" in st.session_state and "selected_segment_id" in st.session_state:
            selected_segment_id = st.session_state.selected_segment_id
            timeline_data = st.session_state.timeline_data
            segments_data = timeline_data.get("segments", [])

            # 選択されたセグメントを取得
            selected_segment_data = next((seg for seg in segments_data if seg["id"] == selected_segment_id), None)

            if selected_segment_data:
                selected_segment = TimelineSegment.from_dict(selected_segment_data)

                # タブで機能を分割
                tab1, tab2, tab3 = st.tabs(["📊 波形表示", "⚡ クイック調整", "🎮 詳細編集"])

                with tab1:
                    render_waveform_tab(selected_segment, video_path, timeline_data, service, interaction, playback)

                with tab2:
                    render_quick_adjust_tab(selected_segment, timeline_data, service)

                with tab3:
                    render_detailed_edit_tab(selected_segment, timeline_data, service)

    # キーボードショートカットのハンドラー登録
    register_keyboard_handlers(keyboard, service, timeline_data)

    # 操作ボタン
    st.divider()
    render_action_buttons(service)

    return None


def render_waveform_tab(
    segment: TimelineSegment,
    video_path: str,
    timeline_data: dict,
    service: TimelineEditingService,
    interaction: WaveformInteraction,
    playback: WaveformPlayback,
):
    """波形表示タブをレンダリング"""
    st.markdown(f"#### セグメント {segment.id}")

    # 再生コントロール
    playback_state = playback.create_playback_controls()

    # 波形データの取得
    waveform_processor = WaveformProcessor()
    waveform_display = WaveformDisplay()

    with st.spinner("波形データを読み込み中..."):
        waveform_data = waveform_processor.extract_waveform(video_path, segment.start, segment.end, segment.id)

        # 無音領域の検出
        silence_regions = waveform_processor.detect_silence_regions(waveform_data)

        # セグメント境界の計算
        segment_boundaries = [segment.start, segment.end]

        # 波形の描画
        fig = waveform_display.render_waveform(waveform_data, silence_regions=silence_regions, show_time_axis=True)

        if fig:
            # インタラクティブ機能を追加
            interaction.add_boundary_markers(fig, segment_boundaries)
            interaction.add_hover_info(fig, waveform_data)

            # Plotly設定
            config = interaction.create_interactive_waveform_config()

            # 波形表示
            st.plotly_chart(fig, use_container_width=True, config=config, key=f"waveform_{segment.id}")


def render_quick_adjust_tab(segment: TimelineSegment, timeline_data: dict, service: TimelineEditingService):
    """クイック調整タブをレンダリング"""
    st.markdown("##### ⚡ 時間のクイック調整")

    # プリセット調整
    st.markdown("**プリセット調整**")
    col1, col2, col3 = st.columns(3)

    presets = [
        ("両端を0.5秒広げる", -0.5, 0.5),
        ("両端を0.5秒狭める", 0.5, -0.5),
        ("前に1秒ずらす", -1.0, -1.0),
        ("後に1秒ずらす", 1.0, 1.0),
    ]

    for i, (label, start_adj, end_adj) in enumerate(presets):
        col = [col1, col2, col3][i % 3]
        with col:
            if st.button(label, key=f"preset_{i}"):
                new_start = segment.start + start_adj
                new_end = segment.end + end_adj
                result = service.set_segment_time_range(segment.id, new_start, new_end)
                if result["success"]:
                    st.success("調整しました")
                    st.rerun()
                else:
                    st.error(result.get("error", "調整に失敗しました"))

    st.divider()

    # スライダー調整
    st.markdown("**スライダー調整**")

    col1, col2 = st.columns(2)

    with col1:
        new_start = st.slider(
            "開始時間",
            min_value=0.0,
            max_value=segment.end - 0.1,
            value=segment.start,
            step=0.1,
            format="%.1f秒",
            key=f"start_slider_{segment.id}",
        )

    with col2:
        new_end = st.slider(
            "終了時間",
            min_value=segment.start + 0.1,
            max_value=timeline_data["video_duration"],
            value=segment.end,
            step=0.1,
            format="%.1f秒",
            key=f"end_slider_{segment.id}",
        )

    if st.button("スライダーの値を適用", type="primary", key=f"apply_slider_{segment.id}"):
        result = service.set_segment_time_range(segment.id, new_start, new_end)
        if result["success"]:
            st.success("時間を更新しました")
            st.rerun()
        else:
            st.error(result.get("error", "更新に失敗しました"))


def render_detailed_edit_tab(segment: TimelineSegment, timeline_data: dict, service: TimelineEditingService):
    """詳細編集タブをレンダリング"""
    st.markdown("##### 🎮 詳細編集")

    # 現在の値
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("開始時間", format_time(segment.start))
    with col2:
        st.metric("終了時間", format_time(segment.end))
    with col3:
        st.metric("長さ", format_time(segment.duration()))

    # フレーム単位の調整
    st.markdown("**フレーム単位調整**")

    fps = timeline_data.get("fps", 30)
    frame_duration = 1.0 / fps

    # 開始時間調整
    st.markdown("開始時間")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    frame_adjustments = [
        (col1, "-30f", -30),
        (col2, "-10f", -10),
        (col3, "-1f", -1),
        (col4, "+1f", 1),
        (col5, "+10f", 10),
        (col6, "+30f", 30),
    ]

    for col, label, frames in frame_adjustments:
        with col:
            if st.button(label, key=f"start_{label}_{segment.id}"):
                adjustment = frames * frame_duration
                service.adjust_segment_timing(segment.id, "start", adjustment)
                st.rerun()

    # 終了時間調整
    st.markdown("終了時間")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    for i, (col, label, frames) in enumerate(frame_adjustments):
        with col:
            if st.button(label, key=f"end_{label}_{segment.id}"):
                adjustment = frames * frame_duration
                service.adjust_segment_timing(segment.id, "end", adjustment)
                st.rerun()

    # テキスト編集
    st.divider()
    st.markdown("**セグメントテキスト**")

    with st.expander("テキストを表示/編集", expanded=False):
        new_text = st.text_area("テキスト", value=segment.text, height=100, key=f"text_edit_{segment.id}")

        if st.button("テキストを更新", key=f"update_text_{segment.id}"):
            # テキスト更新機能の実装（必要に応じて）
            st.info("テキスト更新機能は今後実装予定です")


def register_keyboard_handlers(keyboard: KeyboardShortcuts, service: TimelineEditingService, timeline_data: dict):
    """キーボードショートカットのハンドラーを登録"""

    def toggle_playback():
        if "playback_control" in st.session_state:
            playback = st.session_state.playback_control
            playback.is_playing = not playback.is_playing
            st.rerun()

    def previous_segment():
        if "selected_segment_id" in st.session_state and "timeline_data" in st.session_state:
            segments = timeline_data.get("segments", [])
            current_idx = next(
                (i for i, s in enumerate(segments) if s["id"] == st.session_state.selected_segment_id), -1
            )
            if current_idx > 0:
                st.session_state.selected_segment_id = segments[current_idx - 1]["id"]
                st.rerun()

    def next_segment():
        if "selected_segment_id" in st.session_state and "timeline_data" in st.session_state:
            segments = timeline_data.get("segments", [])
            current_idx = next(
                (i for i, s in enumerate(segments) if s["id"] == st.session_state.selected_segment_id), -1
            )
            if 0 <= current_idx < len(segments) - 1:
                st.session_state.selected_segment_id = segments[current_idx + 1]["id"]
                st.rerun()

    def adjust_start_time(value: float):
        if "selected_segment_id" in st.session_state:
            service.adjust_segment_timing(st.session_state.selected_segment_id, "start", value)
            st.rerun()

    def adjust_end_time(value: float):
        if "selected_segment_id" in st.session_state:
            service.adjust_segment_timing(st.session_state.selected_segment_id, "end", value)
            st.rerun()

    # ハンドラーを登録
    keyboard.register_handler("toggle_playback", toggle_playback)
    keyboard.register_handler("previous_segment", previous_segment)
    keyboard.register_handler("next_segment", next_segment)
    keyboard.register_handler("adjust_start_time", adjust_start_time)
    keyboard.register_handler("adjust_end_time", adjust_end_time)


def render_action_buttons(service: TimelineEditingService):
    """アクションボタンをレンダリング"""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("✅ 編集を完了", type="primary"):
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
        if st.button("💾 設定を保存"):
            service.save_timeline_settings()
            st.success("設定を保存しました")

    with col3:
        if st.button("🔄 リセット"):
            cleanup_session_state()
            st.rerun()

    with col4:
        if st.button("❌ キャンセル"):
            cleanup_session_state()
            return None


def cleanup_session_state():
    """セッション状態をクリーンアップ"""
    keys_to_remove = [
        "timeline_initialized",
        "timeline_data",
        "selected_segment_id",
        "keyboard_shortcuts",
        "waveform_interaction",
        "playback_control",
        "preview_audio_path",
    ]

    for key in keys_to_remove:
        if key in st.session_state:
            if key == "preview_audio_path" and os.path.exists(st.session_state[key]):
                os.remove(st.session_state[key])
            del st.session_state[key]
