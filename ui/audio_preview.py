"""
音声プレビューUIコンポーネント
境界調整機能と連携した音声プレビューを提供
"""

import tempfile

import streamlit as st

from config import Config
from core.video import VideoProcessor
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def show_audio_preview_for_clips(
    video_path: str, time_ranges: list[tuple[float, float]], max_previews: int = 3
) -> None:
    """
    クリップの音声プレビューを表示

    Args:
        video_path: 動画ファイルパス
        time_ranges: 時間範囲のリスト
        max_previews: 最大プレビュー数
    """
    if not time_ranges:
        st.info("プレビューする範囲がありません")
        return

    st.markdown("#### 🎵 音声プレビュー")

    # VideoProcessorのインスタンス
    config = Config()
    video_processor = VideoProcessor(config)

    # プレビュー数を制限
    preview_ranges = time_ranges[:max_previews]
    if len(time_ranges) > max_previews:
        st.info(f"最初の{max_previews}クリップのみプレビュー可能です")

    # 各クリップのプレビューを生成
    for i, (start, end) in enumerate(preview_ranges):
        col1, col2 = st.columns([3, 1])

        with col1:
            st.text(f"クリップ {i+1}: {format_time(start)} - {format_time(end)}")

        with col2:
            if st.button("▶️ 再生", key=f"preview_clip_{i}"):
                with st.spinner("音声を生成中..."):
                    try:
                        # 一時ファイルに音声を抽出
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                            output_path = tmp_file.name

                        # 音声抽出（最大5秒に制限）
                        preview_duration = min(end - start, 5.0)
                        preview_end = start + preview_duration

                        video_processor.extract_audio_segment(video_path, output_path, start, preview_end)

                        # 音声プレーヤーを表示
                        st.audio(output_path, format="audio/wav")

                        # プレビューが短縮された場合は通知
                        if preview_duration < (end - start):
                            st.caption("※ プレビューは最初の5秒のみ")

                    except Exception as e:
                        logger.error(f"音声プレビュー生成エラー: {e}")
                        st.error("音声の生成に失敗しました")


def show_boundary_adjusted_preview(
    video_path: str,
    original_ranges: list[tuple[float, float]],
    adjusted_ranges: list[tuple[float, float]],
    preview_index: int = 0,
) -> None:
    """
    境界調整前後の音声プレビューを比較表示

    Args:
        video_path: 動画ファイルパス
        original_ranges: 調整前の時間範囲
        adjusted_ranges: 調整後の時間範囲
        preview_index: プレビューするクリップのインデックス
    """
    if not original_ranges or not adjusted_ranges:
        st.info("プレビューする範囲がありません")
        return

    if preview_index >= len(original_ranges) or preview_index >= len(adjusted_ranges):
        st.error("無効なプレビューインデックス")
        return

    st.markdown("#### 🎵 境界調整プレビュー")

    # VideoProcessorのインスタンス
    config = Config()
    video_processor = VideoProcessor(config)

    # 調整前後の範囲
    orig_start, orig_end = original_ranges[preview_index]
    adj_start, adj_end = adjusted_ranges[preview_index]

    # 2カラムで表示
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**調整前**")
        st.text(f"{format_time(orig_start)} - {format_time(orig_end)}")

        if st.button("▶️ 調整前を再生", key="preview_original"):
            with st.spinner("音声を生成中..."):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                        output_path = tmp_file.name

                    # 最大5秒に制限
                    preview_duration = min(orig_end - orig_start, 5.0)
                    preview_end = orig_start + preview_duration

                    video_processor.extract_audio_segment(video_path, output_path, orig_start, preview_end)

                    st.audio(output_path, format="audio/wav")

                except Exception as e:
                    logger.error(f"音声プレビュー生成エラー: {e}")
                    st.error("音声の生成に失敗しました")

    with col2:
        st.markdown("**調整後**")
        st.text(f"{format_time(adj_start)} - {format_time(adj_end)}")

        # 調整内容を表示
        if adj_start != orig_start:
            diff = adj_start - orig_start
            st.caption(f"開始: {diff:+.1f}秒")
        if adj_end != orig_end:
            diff = adj_end - orig_end
            st.caption(f"終了: {diff:+.1f}秒")

        if st.button("▶️ 調整後を再生", key="preview_adjusted"):
            with st.spinner("音声を生成中..."):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                        output_path = tmp_file.name

                    # 最大5秒に制限
                    preview_duration = min(adj_end - adj_start, 5.0)
                    preview_end = adj_start + preview_duration

                    video_processor.extract_audio_segment(video_path, output_path, adj_start, preview_end)

                    st.audio(output_path, format="audio/wav")

                except Exception as e:
                    logger.error(f"音声プレビュー生成エラー: {e}")
                    st.error("音声の生成に失敗しました")
