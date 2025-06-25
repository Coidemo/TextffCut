"""
波形表示機能のデモアプリケーション
"""

from pathlib import Path

import streamlit as st

from core.waveform_processor import WaveformProcessor
from ui.waveform_display import WaveformDisplay


def main():
    st.set_page_config(page_title="波形表示デモ", layout="wide")

    st.title("🎵 波形表示機能デモ")
    st.markdown("タイムライン編集UI改善 - Phase 1: 波形表示")

    # videosディレクトリのファイルを取得
    videos_dir = Path("videos")
    if not videos_dir.exists():
        st.error("videosディレクトリが見つかりません")
        return

    video_files = list(videos_dir.glob("*.mp4")) + list(videos_dir.glob("*.mov"))
    if not video_files:
        st.error("動画ファイルが見つかりません")
        return

    # 動画選択
    selected_video = st.selectbox("動画を選択", video_files, format_func=lambda x: x.name)

    if selected_video:
        video_path = str(selected_video)

        # セグメント設定
        st.sidebar.header("セグメント設定")
        start_time = st.sidebar.number_input("開始時間（秒）", min_value=0.0, value=0.0, step=0.1)
        end_time = st.sidebar.number_input("終了時間（秒）", min_value=0.1, value=5.0, step=0.1)

        if start_time >= end_time:
            st.error("終了時間は開始時間より後に設定してください")
            return

        # 波形処理
        processor = WaveformProcessor()
        display = WaveformDisplay()

        # 波形データ抽出
        with st.spinner("波形データを抽出中..."):
            waveform_data = processor.extract_waveform(video_path, start_time, end_time, "demo_segment")

        # 波形表示
        st.header("📊 波形表示")

        # 無音領域検出
        silence_regions = processor.detect_silence_regions(waveform_data)

        # 統計情報
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("サンプル数", len(waveform_data.samples))
        with col2:
            st.metric("サンプリングレート", f"{waveform_data.sample_rate} Hz")
        with col3:
            st.metric("無音領域数", len(silence_regions))

        # 波形グラフ
        fig = display.render_waveform(waveform_data, silence_regions=silence_regions, show_time_axis=True)

        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("波形を表示できません（plotlyがインストールされていない可能性があります）")

        # タイムライン概要（複数セグメントのデモ）
        st.header("📅 タイムライン概要")

        # デモ用の複数セグメント
        demo_segments = []
        for i in range(3):
            seg_start = i * 5.0
            seg_end = (i + 1) * 5.0
            seg_data = processor.extract_waveform(video_path, seg_start, seg_end, f"seg{i+1:03d}")
            demo_segments.append(seg_data)

        overview_fig = display.render_timeline_overview(demo_segments, 15.0)
        if overview_fig:
            st.plotly_chart(overview_fig, use_container_width=True)

        # 設定オプション
        st.sidebar.header("表示設定")

        # 色設定
        st.sidebar.subheader("カラー設定")
        color_positive = st.sidebar.color_picker("正の振幅", value="#4CAF50")
        color_negative = st.sidebar.color_picker("負の振幅", value="#2196F3")
        color_silence = st.sidebar.color_picker("無音領域", value="#cccccc")

        # カスタム色で再描画
        if st.sidebar.button("色を適用"):
            custom_display = WaveformDisplay(
                color_positive=color_positive, color_negative=color_negative, color_silence=color_silence
            )

            custom_fig = custom_display.render_waveform(
                waveform_data, silence_regions=silence_regions, show_time_axis=True
            )

            if custom_fig:
                st.plotly_chart(custom_fig, use_container_width=True)


if __name__ == "__main__":
    main()
