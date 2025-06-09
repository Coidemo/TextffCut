"""
音声プレビュー機能のUIコンポーネント
"""
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional
import tempfile
import uuid

from core.video import VideoProcessor
from utils.logging import get_logger

logger = get_logger(__name__)


def show_audio_preview_section(
    video_path: str,
    time_ranges: List[Tuple[float, float]],
    progress_callback: Optional[callable] = None
) -> None:
    """
    音声プレビューセクションを表示
    
    Args:
        video_path: 動画ファイルのパス
        time_ranges: プレビューする時間範囲のリスト
        progress_callback: 進捗コールバック
    """
    st.markdown("#### 🎧 音声プレビュー")
    
    if not time_ranges:
        st.info("切り抜き箇所を指定してください")
        return
    
    # プレビュー情報の表示
    total_duration = sum(end - start for start, end in time_ranges)
    st.caption(f"プレビュー時間: {total_duration:.1f}秒 | セグメント数: {len(time_ranges)}")
    
    # プレビュー生成ボタン
    if st.button("🎵 プレビューを生成", key="generate_preview"):
        with st.spinner("音声を準備中..."):
            audio_path = generate_audio_preview(video_path, time_ranges, progress_callback)
            
            if audio_path and Path(audio_path).exists():
                st.session_state.preview_audio_path = audio_path
                st.success("✅ プレビュー生成完了！")
                st.rerun()
            else:
                st.error("音声プレビューの生成に失敗しました")
    
    # 生成済みの音声を表示
    if 'preview_audio_path' in st.session_state:
        audio_path = st.session_state.preview_audio_path
        if Path(audio_path).exists():
            # 音声プレーヤーを表示
            st.audio(audio_path, format='audio/wav')
            
            # 時間範囲の詳細を表示
            with st.expander("📊 プレビュー詳細", expanded=False):
                for i, (start, end) in enumerate(time_ranges):
                    duration = end - start
                    st.text(f"セグメント {i+1}: {start:.1f}秒 - {end:.1f}秒 (長さ: {duration:.1f}秒)")
            
            # クリアボタン
            if st.button("🗑️ プレビューをクリア", key="clear_preview"):
                try:
                    Path(audio_path).unlink()
                except:
                    pass
                del st.session_state.preview_audio_path
                st.rerun()


def generate_audio_preview(
    video_path: str,
    time_ranges: List[Tuple[float, float]],
    progress_callback: Optional[callable] = None
) -> Optional[str]:
    """
    指定された時間範囲の音声を結合してプレビューファイルを生成
    
    Args:
        video_path: 動画ファイルのパス
        time_ranges: 抽出する時間範囲のリスト
        progress_callback: 進捗コールバック
        
    Returns:
        生成された音声ファイルのパス（失敗時はNone）
    """
    try:
        from config import config
        video_processor = VideoProcessor(config)
        
        # 動画ファイルの存在確認
        if not Path(video_path).exists():
            logger.error(f"動画ファイルが存在しません: {video_path}")
            return None
        
        # 時間範囲が空でないことを確認
        if not time_ranges:
            logger.warning("時間範囲が指定されていません")
            return None
        
        # 一時ディレクトリを使用
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # VideoSegmentのリストを作成
            from core.video import VideoSegment
            segments = []
            for start, end in time_ranges:
                segments.append(VideoSegment(start=start, end=end))
            
            # 音声を抽出
            output_audio_path = temp_path / "preview_audio.wav"
            
            success = video_processor.extract_audio_from_segments(
                video_path,
                segments,
                str(output_audio_path),
                progress_callback,
                preview_mode=True  # プレビューモードで高速処理
            )
            
            if success and output_audio_path.exists():
                # ファイルサイズを確認
                file_size = output_audio_path.stat().st_size
                if file_size == 0:
                    logger.warning("生成された音声ファイルが空です")
                    return None
                
                # Streamlitの一時ディレクトリにコピー（UUID使用で衝突回避）
                import shutil
                final_path = Path(tempfile.gettempdir()) / f"preview_audio_{uuid.uuid4()}.wav"
                shutil.copy2(str(output_audio_path), str(final_path))
                logger.info(f"音声プレビューファイル生成完了: {final_path} ({file_size} bytes)")
                return str(final_path)
            else:
                logger.error("音声抽出に失敗しました")
            
    except Exception as e:
        logger.error(f"音声プレビュー生成エラー: {e}", exc_info=True)
    
    return None