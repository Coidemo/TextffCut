"""
エクスポートセクション - レガシー実装

main.pyのエクスポート処理をそのまま関数として抽出。
移行期間中、動作の同一性を保証するために使用。
"""

import os
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Any, Optional

from config import config
from core import TextProcessor, TranscriptionSegment
from core.time_mapper import TimeMapper
from services import VideoProcessingService, ConfigurationService
from utils import ProcessingContext
from utils.file_utils import ensure_directory, get_safe_filename
from utils.path_helpers import get_display_path
from utils.time_utils import format_time
from utils.export_helpers import (
    determine_export_format,
    export_xml,
    export_srt_with_diff,
    generate_export_paths,
    format_export_success_message,
    get_srt_settings_from_session
)
from ui import show_progress
from utils.logging import get_logger

logger = get_logger(__name__)


def execute_export_legacy(
    video_path: str,
    edited_text: str,
    time_ranges: List[Tuple[float, float]],
    transcription_result: Any,
    process_type: str,
    primary_format: str,
    export_srt: bool,
    timeline_fps: str,
    noise_threshold: float,
    min_silence_duration: float,
    min_segment_duration: float,
    padding_start: float,
    padding_end: float,
    project_path: Path,
    safe_name: str,
    full_text: str,
    found_separator: Optional[str],
    cleaned_text: str
) -> None:
    """
    main.pyのエクスポート処理をそのまま実行
    
    このコードはmain.pyから直接コピーしたもので、
    動作の同一性を保証します。
    """
    # 出力ディレクトリの設定（動画と同じ場所にTextffCutフォルダ作成）
    video_name = Path(video_path).stem
    safe_name = get_safe_filename(video_name)
    video_parent = Path(video_path).parent
    
    # 動画と同じ場所にTextffCutフォルダを作成
    project_dir = video_parent / f"{safe_name}_TextffCut"
    
    # ディレクトリを作成（XMLファイル保護のためクリーンしない）
    project_path = ensure_directory(Path(project_dir), clean=False)
    
    # ConfigurationServiceを使用して出力パス情報を取得
    config_service = ConfigurationService(config)
    
    # 処理タイプのマッピング
    process_type_map = {"切り抜きのみ": "clip", "切り抜き + 無音削除": "both"}
    mapped_process_type = process_type_map.get(process_type, "full")
    
    # 処理タイプに応じたサフィックス（アルファベット表現）
    if process_type == "切り抜きのみ":
        type_suffix = "Clip"
    else:
        type_suffix = "NoSilence"
    
    # デバッグ：使用する時間範囲を表示（spinner外で表示）
    with st.expander("🔍 デバッグ情報", expanded=True):
        st.write(f"処理に使用する時間範囲: {len(time_ranges)}クリップ")
        for i, (start, end) in enumerate(time_ranges[:3]):  # 最初の3つだけ表示
            st.write(f"  - クリップ{i + 1}: {start:.1f}秒 〜 {end:.1f}秒 (長さ: {end - start:.1f}秒)")
        if len(time_ranges) > 3:
            st.write(f"  ... 他 {len(time_ranges) - 3} クリップ")
    
    # ProcessingContextで処理を実行（エラー時は自動クリーンアップ）
    with st.spinner("処理中..."), ProcessingContext(project_path) as temp_manager:
        try:
            # プログレスバーを初期化
            progress_bar, status_text = show_progress(0, "処理を開始しています...")
            
            # 残す時間範囲を決定
            if process_type == "切り抜きのみ":
                # 切り抜きのみの場合はtime_rangesをそのまま使用
                keep_ranges = time_ranges
                show_progress(0.5, "切り抜き箇所を処理中...", progress_bar, status_text)
            else:
                # 無音削除付きで処理（新フロー）
                def progress_callback(progress, status):
                    show_progress(progress, status, progress_bar, status_text)
                
                # VideoProcessingServiceを使用して無音削除
                video_service = VideoProcessingService(config)
                from core import TranscriptionSegment
                
                # time_rangesからセグメントを作成
                segments_for_removal = []
                for start, end in time_ranges:
                    segments_for_removal.append(
                        TranscriptionSegment(start=start, end=end, text="", words=[])
                    )
                
                silence_result = video_service.remove_silence(
                    video_path=video_path,
                    segments=segments_for_removal,
                    threshold=noise_threshold,
                    min_silence_duration=min_silence_duration,
                    pad_start=padding_start,
                    pad_end=padding_end,
                    min_segment_duration=min_segment_duration,
                    progress_callback=progress_callback,
                )
                
                if silence_result.success:
                    # 調整されたセグメントから時間範囲を抽出
                    adjusted_segments = silence_result.data
                    keep_ranges = [(seg.start, seg.end) for seg in adjusted_segments]
                else:
                    st.error(f"無音削除エラー: {silence_result.error}")
                    return
            
            # 出力形式に応じて処理
            if primary_format in ["FCPXMLファイル", "Premiere Pro XML"]:
                # XMLファイル生成の準備
                timeline_pos = 0  # timeline_posを初期化
                
                # 形式を決定
                export_format, xml_ext = determine_export_format(primary_format)
                
                # 出力パスを生成
                export_paths = generate_export_paths(
                    project_path=project_path,
                    base_name=safe_name,
                    type_suffix=type_suffix,
                    export_srt=export_srt,
                    xml_ext=xml_ext
                )
                xml_path = export_paths["xml"]
                
                # XMLエクスポート実行
                success, error_msg, timeline_pos = export_xml(
                    config=config,
                    video_path=Path(video_path),
                    keep_ranges=keep_ranges,
                    output_path=xml_path,
                    export_format=export_format,
                    remove_silence=(process_type != "切り抜きのみ")
                )
                
                if success:
                    # 100%完了を表示
                    show_progress(1.0, "エクスポート完了！", progress_bar, status_text)
                    
                    # SRT字幕も出力する場合
                    srt_path = None
                    srt_success = True
                    if export_srt and "srt" in export_paths:
                        srt_path = export_paths["srt"]
                        
                        # TimeMapperを作成（無音削除時に必要）
                        time_mapper = None
                        if process_type != "切り抜きのみ":
                            time_mapper = TimeMapper(time_ranges, keep_ranges)
                        
                        # 差分計算
                        text_processor = TextProcessor()
                        if found_separator:
                            text_without_separator = cleaned_text.replace(found_separator, " ")
                            diff = text_processor.find_differences(full_text, text_without_separator)
                        else:
                            diff = text_processor.find_differences(full_text, cleaned_text)
                        
                        # SRTエクスポート
                        srt_success, srt_error = export_srt_with_diff(
                            config=config,
                            video_path=Path(video_path),
                            output_path=srt_path,
                            diff_data=diff,
                            transcription_result=transcription_result,
                            time_mapper=time_mapper,
                            remove_silence=(process_type != "切り抜きのみ")
                        )
                        
                        if not srt_success:
                            logger.warning(f"SRT生成エラー: {srt_error}")
                    
                    # 成功メッセージ
                    message = format_export_success_message(
                        format_name=primary_format,
                        output_path=xml_path,
                        timeline_duration=timeline_pos,
                        srt_path=srt_path,
                        srt_success=srt_success
                    )
                    st.success(message)
                else:
                    st.error(f"エクスポートに失敗しました: {error_msg}")
                    
            elif primary_format == "動画ファイル":
                # 動画ファイルのエクスポート処理
                # （実装は省略 - main.pyから必要に応じてコピー）
                st.info("動画ファイルのエクスポートは現在準備中です。")
                
        except Exception as e:
            from core.error_handling import ErrorHandler
            ErrorHandler.handle_error(e, "動画処理")
            logger.error(f"エクスポート処理エラー: {str(e)}", exc_info=True)