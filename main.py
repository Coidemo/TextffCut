"""
Buzz Clip - 動画の文字起こしと切り抜きツール
"""

import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional

from config import config
from modules import (
    transcription,
    text_diff,
    video_processing,
    fcpxml_export,
    ui_components
)
from utils import BuzzClipError

# Streamlitの設定
st.set_page_config(
    page_title="Buzz Clip", 
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def process_video(video_path: str, model_name: str, noise_threshold: float,
                 min_silence_duration: float, output_name: str,
                 remove_fillers: bool, create_fcpxml: bool) -> None:
    """動画の処理を実行"""
    try:
        # 出力ディレクトリの作成
        output_dir = config.output_dir / output_name
        output_dir.mkdir(exist_ok=True)
        
        # 文字起こしの実行
        st.info("文字起こしを実行中...")
        result = transcription.transcribe_video(video_path, model_name)
        
        # 文字起こし結果の保存
        transcription_path = transcription.save_transcription(result, video_path, model_name)
        st.success(f"文字起こしが完了しました: {transcription_path}")
        
        # テキストの取得
        text = transcription.get_transcription_text(result)
        segments = transcription.get_transcription_segments(result)
        
        # 変更セグメントの検出
        st.info("変更セグメントを検出中...")
        differences = text_diff.find_differences(text, text)  # 同じテキストを比較して全セグメントを取得
        changed_segments = text_diff.get_changed_segments(segments, differences)
        time_ranges = text_diff.get_segment_time_ranges(changed_segments)
        merged_ranges = text_diff.merge_overlapping_ranges(time_ranges, min_silence_duration)
        
        # セグメント情報の表示
        ui_components.render_segment_info(merged_ranges)
        
        if not merged_ranges:
            st.warning("検出されたセグメントがありません")
            return
        
        # セグメントの処理
        st.info("セグメントを処理中...")
        segment_paths = []
        
        for i, (start, end) in enumerate(merged_ranges, 1):
            # 出力パスの設定
            segment_path = output_dir / f"segment_{i}.mp4"
            
            # セグメントの抽出
            if remove_fillers:
                video_processing.remove_fillers_from_segment(
                    video_path, start, end, str(segment_path),
                    noise_threshold, min_silence_duration
                )
            else:
                video_processing.extract_segment(
                    video_path, start, end, str(segment_path)
                )
            
            segment_paths.append(str(segment_path))
        
        # セグメントの結合
        if len(segment_paths) > 1:
            st.info("セグメントを結合中...")
            combined_path = output_dir / f"{output_name}_combined.mp4"
            video_processing.combine_segments(segment_paths, str(combined_path))
            
            # 結合した動画の表示
            ui_components.render_video_player(str(combined_path))
            ui_components.render_download_button(str(combined_path), "結合した動画をダウンロード")
        
        # FCPXMLファイルの生成
        if create_fcpxml:
            st.info("FCPXMLファイルを生成中...")
            fcpxml_path = output_dir / f"{output_name}.fcpxml"
            
            if len(segment_paths) > 1:
                fcpxml_export.create_fcpxml(segment_paths, str(fcpxml_path))
            else:
                fcpxml_export.create_fcpxml_from_segments(
                    video_path, merged_ranges, str(fcpxml_path)
                )
            
            ui_components.render_success_message(f"FCPXMLファイルを生成しました: {fcpxml_path}")
        
    except BuzzClipError as e:
        ui_components.render_error_message(e)
    except Exception as e:
        ui_components.render_error_message(e)

def main():
    """メイン関数"""
    st.title("🎙️ Buzz Clip")
    
    # ファイルアップローダー
    video_path = ui_components.render_file_uploader()
    
    if video_path:
        # Whisperモデルの選択
        model_name = ui_components.render_model_selection()
        
        # ノイズ設定
        noise_threshold, min_silence_duration = ui_components.render_noise_settings()
        
        # 出力設定
        output_name, remove_fillers, create_fcpxml = ui_components.render_output_settings()
        
        # 処理開始ボタン
        if st.button("処理を開始"):
            process_video(
                video_path, model_name, noise_threshold,
                min_silence_duration, output_name,
                remove_fillers, create_fcpxml
            )

if __name__ == "__main__":
    main() 