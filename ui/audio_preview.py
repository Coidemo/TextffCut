"""
音声プレビューUIコンポーネント
境界調整機能と連携した音声プレビューを提供
"""

import tempfile
from contextlib import suppress
from pathlib import Path

import streamlit as st

from config import Config
from core.video import VideoProcessor
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def _generate_combined_audio(
    video_processor: VideoProcessor,
    video_path: str | Path,
    time_ranges: list[tuple[float, float]],
    output_path: str | Path,
) -> None:
    """
    複数の時間範囲から音声を抽出して結合

    Args:
        video_processor: VideoProcessorインスタンス
        video_path: 入力動画パス
        time_ranges: 時間範囲のリスト
        output_path: 出力音声パス
    """
    import subprocess

    # 一時ディレクトリ
    temp_dir = Path(output_path).parent

    # 各セグメントの音声を抽出
    temp_audio_files = []
    for i, (start, end) in enumerate(time_ranges):
        temp_audio = temp_dir / f"preview_audio_{i:04d}.wav"

        try:
            logger.info(f"音声セグメント抽出: {i + 1}/{len(time_ranges)} - {start:.1f}s-{end:.1f}s")
            video_processor.extract_audio_segment(video_path, str(temp_audio), start, end)
            temp_audio_files.append(str(temp_audio))
            logger.info(f"音声セグメント抽出成功: {temp_audio}")
        except Exception as e:
            logger.error(f"セグメント{i + 1}の音声抽出エラー: {e}")
            logger.error(f"エラー詳細: video_path={video_path}, output={temp_audio}, start={start}, end={end}")
            # クリーンアップして例外を再発生
            for temp_file in temp_audio_files:
                with suppress(Exception):
                    Path(temp_file).unlink()
            raise

    # 複数ファイルがある場合は結合
    try:
        if len(temp_audio_files) > 1:
            # リストファイルを作成
            list_file = temp_dir / "preview_list.txt"
            with open(str(list_file), "w") as f:
                for audio_file in temp_audio_files:
                    f.write(f"file '{Path(audio_file).resolve()}'\n")

            # FFmpegで結合
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-acodec",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-f",
                "wav",
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"音声結合エラー: {result.stderr}")

            # リストファイルを削除
            list_file.unlink()

        elif len(temp_audio_files) == 1:
            # 単一ファイルの場合はリネーム
            Path(temp_audio_files[0]).rename(output_path)

    finally:
        # 一時ファイルをクリーンアップ
        for temp_file in temp_audio_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
            except Exception:
                pass


def show_audio_preview_for_clips(
    video_path: str | Path, time_ranges: list[tuple[float, float]], max_duration: float = 30.0
) -> None:
    """
    クリップの音声プレビューを表示（すべてのクリップを結合）

    Args:
        video_path: 動画ファイルパス
        time_ranges: 時間範囲のリスト
        max_duration: 最大プレビュー時間（秒）
    """
    if not time_ranges:
        st.info("プレビューする範囲がありません")
        return

    st.markdown("#### 🎵 音声プレビュー")

    # VideoProcessorのインスタンス
    config = Config()
    video_processor = VideoProcessor(config)

    # 合計時間を計算
    total_duration = sum(end - start for start, end in time_ranges)

    # プレビュー情報を表示
    st.text(f"クリップ数: {len(time_ranges)}")
    st.text(f"合計時間: {format_time(total_duration)}")

    if total_duration > max_duration:
        st.info(f"プレビューは最大{max_duration}秒に制限されます")

    # 結合プレビューボタン
    if st.button("▶️ すべてのクリップを再生", type="primary", use_container_width=True):
        with st.spinner("音声を生成中..."):
            try:
                # 一時ファイルに結合音声を生成
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    output_path = tmp_file.name

                # プレビュー用の時間範囲を調整（最大時間を超えないように）
                preview_ranges = []
                accumulated_duration = 0.0

                for start, end in time_ranges:
                    segment_duration = end - start
                    if accumulated_duration + segment_duration <= max_duration:
                        preview_ranges.append((start, end))
                        accumulated_duration += segment_duration
                    else:
                        # 残り時間分だけ追加
                        remaining = max_duration - accumulated_duration
                        if remaining > 0:
                            preview_ranges.append((start, start + remaining))
                        break

                # 結合音声を生成
                _generate_combined_audio(video_processor, video_path, preview_ranges, output_path)

                # 音声プレーヤーを表示
                st.audio(output_path, format="audio/wav")

                # プレビューが短縮された場合は通知
                if accumulated_duration < total_duration:
                    st.caption(f"※ プレビューは最初の{max_duration}秒のみ")

            except Exception as e:
                logger.error(f"音声プレビュー生成エラー: {e}")
                st.error("音声の生成に失敗しました")


def show_boundary_adjusted_preview(
    video_path: str | Path,
    original_ranges: list[tuple[float, float]],
    adjusted_ranges: list[tuple[float, float]],
    max_duration: float = 30.0,
) -> None:
    """
    境界調整前後の音声プレビューを比較表示（すべてのクリップを結合）

    Args:
        video_path: 動画ファイルパス
        original_ranges: 調整前の時間範囲
        adjusted_ranges: 調整後の時間範囲
        max_duration: 最大プレビュー時間（秒）
    """
    if not original_ranges or not adjusted_ranges:
        st.info("プレビューする範囲がありません")
        return

    st.markdown("#### 🎵 境界調整プレビュー")

    # VideoProcessorのインスタンス
    config = Config()
    video_processor = VideoProcessor(config)

    # 合計時間を計算
    orig_total = sum(end - start for start, end in original_ranges)
    adj_total = sum(end - start for start, end in adjusted_ranges)

    # 時間情報を表示
    col1, col2 = st.columns(2)
    with col1:
        st.metric("調整前の合計時間", format_time(orig_total))
    with col2:
        st.metric("調整後の合計時間", format_time(adj_total))

    # 調整による変化を表示
    time_diff = adj_total - orig_total
    if time_diff != 0:
        st.info(f"時間の変化: {time_diff:+.1f}秒")

    # プレビューボタンを横並びで表示
    col1, col2 = st.columns(2)

    with col1:
        if st.button("▶️ 調整前をすべて再生", key="preview_original_all", use_container_width=True):
            with st.spinner("音声を生成中..."):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                        output_path = tmp_file.name

                    # プレビュー用の時間範囲を調整
                    preview_ranges = []
                    accumulated_duration = 0.0

                    for start, end in original_ranges:
                        segment_duration = end - start
                        if accumulated_duration + segment_duration <= max_duration:
                            preview_ranges.append((start, end))
                            accumulated_duration += segment_duration
                        else:
                            remaining = max_duration - accumulated_duration
                            if remaining > 0:
                                preview_ranges.append((start, start + remaining))
                            break

                    # 結合音声を生成
                    _generate_combined_audio(video_processor, video_path, preview_ranges, output_path)

                    st.audio(output_path, format="audio/wav")

                    if accumulated_duration < orig_total:
                        st.caption(f"※ プレビューは最初の{max_duration}秒のみ")

                except Exception as e:
                    logger.error(f"音声プレビュー生成エラー: {e}")
                    st.error("音声の生成に失敗しました")

    with col2:
        if st.button("▶️ 調整後をすべて再生", key="preview_adjusted_all", use_container_width=True):
            with st.spinner("音声を生成中..."):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                        output_path = tmp_file.name

                    # プレビュー用の時間範囲を調整
                    preview_ranges = []
                    accumulated_duration = 0.0

                    for start, end in adjusted_ranges:
                        segment_duration = end - start
                        if accumulated_duration + segment_duration <= max_duration:
                            preview_ranges.append((start, end))
                            accumulated_duration += segment_duration
                        else:
                            remaining = max_duration - accumulated_duration
                            if remaining > 0:
                                preview_ranges.append((start, start + remaining))
                            break

                    # 結合音声を生成
                    _generate_combined_audio(video_processor, video_path, preview_ranges, output_path)

                    st.audio(output_path, format="audio/wav")

                    if accumulated_duration < adj_total:
                        st.caption(f"※ プレビューは最初の{max_duration}秒のみ")

                except Exception as e:
                    logger.error(f"音声プレビュー生成エラー: {e}")
                    st.error("音声の生成に失敗しました")
