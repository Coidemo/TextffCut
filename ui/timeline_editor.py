"""
タイムライン編集UIコンポーネント
視覚的なタイムライン編集インターフェースを提供
"""

import os
from typing import Any

import pandas as pd
import streamlit as st

from core.timeline_processor import TimelineSegment
from core.waveform_processor import WaveformProcessor
from services.timeline_editing_service import TimelineEditingService
from ui.timeline_dark_mode_fix import inject_dark_mode_css
from ui.waveform_display import WaveformDisplay
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

    # タイムラインの初期化
    if "timeline_initialized" not in st.session_state:
        result = service.initialize_timeline(time_ranges, transcription_result, video_path)
        if result["success"]:
            st.session_state.timeline_initialized = True
        else:
            st.error("タイムラインの初期化に失敗しました")
            return None

    # UIヘッダー
    st.markdown("### 📝 タイムライン編集")
    st.markdown("切り抜き箇所の開始・終了時間を微調整できます")

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

    # セグメント一覧表示
    if "timeline_data" in st.session_state:
        timeline_data = st.session_state.timeline_data
        segments_data = timeline_data.get("segments", [])

        if segments_data:
            # データフレームで表示
            df_data = []
            for seg_data in segments_data:
                segment = TimelineSegment.from_dict(seg_data)
                df_data.append(
                    {
                        "ID": segment.id,
                        "開始時間": format_time(segment.start),
                        "終了時間": format_time(segment.end),
                        "長さ": format_time(segment.duration()),
                        "テキスト": segment.text[:50] + "..." if len(segment.text) > 50 else segment.text,
                    }
                )

            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()

            # タイムライン全体の概要表示
            with st.container():
                st.markdown("#### 📊 タイムライン概要")
                # ダークモード対応の波形表示を作成
                waveform_display = WaveformDisplay(width=800, height=100)
                
                # セグメントデータをWaveformData形式に変換（概要表示用）
                overview_segments = []
                for seg_data in segments_data:
                    from core.waveform_processor import WaveformData
                    overview_segments.append(WaveformData(
                        segment_id=seg_data["id"],
                        sample_rate=44100,
                        samples=[],
                        duration=seg_data["end"] - seg_data["start"],
                        start_time=seg_data["start"],
                        end_time=seg_data["end"]
                    ))
                
                overview_fig = waveform_display.render_timeline_overview(
                    overview_segments, 
                    timeline_data["video_duration"]
                )
                # Plotlyグラフの表示（ダークモード対応）
                config = {
                    'displayModeBar': False,  # 概要図はツールバー非表示
                    'staticPlot': True        # インタラクション無効
                }
                st.plotly_chart(overview_fig, use_container_width=True, config=config)

            st.divider()

            # セグメント選択
            segment_ids = [seg["id"] for seg in segments_data]
            selected_segment_id = st.selectbox(
                "編集するセグメントを選択",
                segment_ids,
                format_func=lambda x: f"{x} - {df_data[segment_ids.index(x)]['テキスト'][:30]}...",
            )

            if selected_segment_id:
                # 選択されたセグメントの詳細編集
                selected_segment_data = next(seg for seg in segments_data if seg["id"] == selected_segment_id)
                selected_segment = TimelineSegment.from_dict(selected_segment_data)

                st.markdown(f"#### セグメント {selected_segment_id} の編集")

                # 波形表示
                with st.container():
                    st.markdown("##### 🎵 音声波形")
                    
                    # 波形データの取得（キャッシュ利用）
                    waveform_processor = WaveformProcessor()
                    # ダークモード対応の波形表示を作成
                    waveform_display = WaveformDisplay()
                    
                    with st.spinner("波形データを読み込み中..."):
                        waveform_data = waveform_processor.extract_waveform(
                            video_path,
                            selected_segment.start,
                            selected_segment.end,
                            selected_segment_id
                        )
                        
                        # 無音領域の検出
                        silence_regions = waveform_processor.detect_silence_regions(waveform_data)
                        
                        # 波形の描画
                        waveform_fig = waveform_display.render_waveform(
                            waveform_data,
                            silence_regions=silence_regions,
                            show_time_axis=True
                        )
                        
                        # Plotlyグラフの表示（ダークモード対応）
                        config = {
                            'displayModeBar': True,
                            'displaylogo': False,
                            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
                            'toImageButtonOptions': {
                                'format': 'png',
                                'filename': f'waveform_{selected_segment_id}',
                                'scale': 2
                            }
                        }
                        st.plotly_chart(waveform_fig, use_container_width=True, config=config)

                # テキスト表示
                with st.expander("セグメントのテキスト", expanded=False):
                    st.text(selected_segment.text)

                # 時間調整UI
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**開始時間**")

                    # 数値入力
                    new_start = st.number_input(
                        "開始時間（秒）",
                        min_value=0.0,
                        max_value=timeline_data["video_duration"],
                        value=selected_segment.start,
                        step=0.1,
                        format="%.1f",
                        key=f"start_input_{selected_segment_id}",
                    )

                    # フレーム単位調整ボタン
                    st.markdown("フレーム単位で調整")
                    bcol1, bcol2, bcol3, bcol4, bcol5, bcol6 = st.columns(6)

                    with bcol1:
                        if st.button("-30f", key=f"start_-30f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", -30 / timeline_data["fps"])
                            st.rerun()

                    with bcol2:
                        if st.button("-5f", key=f"start_-5f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", -5 / timeline_data["fps"])
                            st.rerun()

                    with bcol3:
                        if st.button("-1f", key=f"start_-1f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", -1 / timeline_data["fps"])
                            st.rerun()

                    with bcol4:
                        if st.button("+1f", key=f"start_+1f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", 1 / timeline_data["fps"])
                            st.rerun()

                    with bcol5:
                        if st.button("+5f", key=f"start_+5f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", 5 / timeline_data["fps"])
                            st.rerun()

                    with bcol6:
                        if st.button("+30f", key=f"start_+30f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "start", 30 / timeline_data["fps"])
                            st.rerun()

                with col2:
                    st.markdown("**終了時間**")

                    # 数値入力
                    new_end = st.number_input(
                        "終了時間（秒）",
                        min_value=0.0,
                        max_value=timeline_data["video_duration"],
                        value=selected_segment.end,
                        step=0.1,
                        format="%.1f",
                        key=f"end_input_{selected_segment_id}",
                    )

                    # フレーム単位調整ボタン
                    st.markdown("フレーム単位で調整")
                    bcol1, bcol2, bcol3, bcol4, bcol5, bcol6 = st.columns(6)

                    with bcol1:
                        if st.button("-30f", key=f"end_-30f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", -30 / timeline_data["fps"])
                            st.rerun()

                    with bcol2:
                        if st.button("-5f", key=f"end_-5f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", -5 / timeline_data["fps"])
                            st.rerun()

                    with bcol3:
                        if st.button("-1f", key=f"end_-1f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", -1 / timeline_data["fps"])
                            st.rerun()

                    with bcol4:
                        if st.button("+1f", key=f"end_+1f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", 1 / timeline_data["fps"])
                            st.rerun()

                    with bcol5:
                        if st.button("+5f", key=f"end_+5f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", 5 / timeline_data["fps"])
                            st.rerun()

                    with bcol6:
                        if st.button("+30f", key=f"end_+30f_{selected_segment_id}"):
                            service.adjust_segment_timing(selected_segment_id, "end", 30 / timeline_data["fps"])
                            st.rerun()

                # 数値入力が変更された場合の更新
                if (new_start != selected_segment.start or new_end != selected_segment.end) and st.button(
                    "時間を更新", type="primary", key=f"update_{selected_segment_id}"
                ):
                    result = service.set_segment_time_range(selected_segment_id, new_start, new_end)
                    if result["success"]:
                        st.success("時間を更新しました")
                        st.rerun()
                    else:
                        st.error(result.get("error", "更新に失敗しました"))
                        if "validation_errors" in result:
                            for error in result["validation_errors"]:
                                st.error(error)

                # プレビュー再生
                st.divider()

                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("🔊 プレビュー再生", key=f"preview_{selected_segment_id}"):
                        with st.spinner("音声を準備中..."):
                            preview_path = service.generate_preview_audio(selected_segment_id)
                            if preview_path and os.path.exists(preview_path):
                                st.session_state.preview_audio_path = preview_path

                with col2:
                    if "preview_audio_path" in st.session_state:
                        if os.path.exists(st.session_state.preview_audio_path):
                            st.audio(st.session_state.preview_audio_path)
                        else:
                            st.error("プレビュー音声ファイルが見つかりません")

        else:
            st.info("編集可能なセグメントがありません")

    # 操作ボタン
    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("🔄 リセット", use_container_width=True):
            # タイムラインを再初期化
            if "timeline_initialized" in st.session_state:
                del st.session_state.timeline_initialized
            if "timeline_data" in st.session_state:
                del st.session_state.timeline_data
            st.rerun()

    with col2:
        if st.button("✅ 編集を完了", type="primary", use_container_width=True):
            try:
                adjusted_ranges = service.get_adjusted_time_ranges()
                # 設定を保存
                service.save_timeline_settings()
                # クリーンアップ
                if "timeline_initialized" in st.session_state:
                    del st.session_state.timeline_initialized
                if "preview_audio_path" in st.session_state:
                    if os.path.exists(st.session_state.preview_audio_path):
                        os.remove(st.session_state.preview_audio_path)
                    del st.session_state.preview_audio_path
                return adjusted_ranges
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")
                return None

    # 編集が完了していない場合はNoneを返す（UIは表示し続ける）
    return None
