"""
処理実行画面のページコントローラー

main.pyから分離された処理実行処理を管理します。
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st

from config import Config
from core import (
    TextProcessor,
    TranscriptionResult,
    TranscriptionSegment,
    VideoSegment,
)
from core.srt_diff_exporter import SRTDiffExporter
from core.time_mapper import TimeMapper
from services import (
    ConfigurationService,
    ExportService,
    VideoProcessingService,
)
from ui import (
    show_export_settings,
    show_progress,
)
from utils import (
    ProcessingContext,
    cleanup_intermediate_files,
    ensure_directory,
    get_display_path,
    get_safe_filename,
    get_unique_path,
)
from utils.logging import get_logger
from utils.session_state_manager import SessionStateManager

logger = get_logger(__name__)


class ProcessingPageController:
    """処理実行画面の制御"""

    def __init__(self):
        self.config = Config()
        self.text_processor = TextProcessor()
        self.config_service = ConfigurationService(self.config)
        self.video_service = VideoProcessingService(self.config)
        self.export_service = ExportService(self.config)

    def render(self) -> None:
        """処理実行画面をレンダリング"""
        # 必要な情報の確認
        if not self._validate_prerequisites():
            return
        
        st.markdown("---")
        st.subheader("🎬 切り抜き処理実行")
        
        # 処理オプション
        st.markdown("#### ⚙️ 処理オプション")
        process_type, primary_format, export_srt, timeline_fps = show_export_settings()
        
        # 無音削除設定の表示
        if process_type == "無音削除付き":
            self._show_silence_removal_settings()
        
        # 出力先の表示
        self._show_output_destination()
        
        # 処理実行ボタン
        if st.button("🚀 処理を実行", type="primary", use_container_width=True):
            self._execute_processing(
                process_type, primary_format, export_srt, timeline_fps
            )

    def _validate_prerequisites(self) -> bool:
        """前提条件の検証"""
        # 動画パスの確認
        video_path = SessionStateManager.get("video_path")
        if not video_path:
            st.error("動画ファイルが選択されていません。")
            return False
        
        # 文字起こし結果の確認
        transcription = SessionStateManager.get("transcription_result")
        if not transcription:
            st.error("文字起こし結果がありません。")
            return False
        
        # 時間範囲の確認
        time_ranges = SessionStateManager.get("time_ranges")
        if not time_ranges:
            st.error("切り抜き箇所が指定されていません。")
            return False
        
        return True

    def _show_silence_removal_settings(self) -> None:
        """無音削除設定の表示"""
        st.markdown("##### 🔇 無音削除の設定")
        
        # サイドバーから設定を取得
        noise_threshold = SessionStateManager.get("noise_threshold", -35)
        min_silence_duration = SessionStateManager.get("min_silence_duration", 0.3)
        min_segment_duration = SessionStateManager.get("min_segment_duration", 0.3)
        padding_start = SessionStateManager.get("padding_start", 0.1)
        padding_end = SessionStateManager.get("padding_end", 0.1)
        
        st.info(
            f"現在の設定: 閾値{noise_threshold}dB | "
            f"無音{min_silence_duration}秒 | "
            f"セグメント{min_segment_duration}秒 | "
            f"パディング{padding_start}-{padding_end}秒 | "
            f"設定変更は左サイドパネルの「無音検出」タブから"
        )

    def _show_output_destination(self) -> None:
        """出力先の表示"""
        st.markdown("#### 📁 出力先")
        
        video_path = SessionStateManager.get("video_path")
        video_name = Path(video_path).stem
        safe_name = get_safe_filename(video_name)
        
        # 出力パスを表示（Docker環境ではホストパスに変換）
        video_parent = Path(video_path).parent
        project_path = video_parent / f"{safe_name}_TextffCut"
        
        if os.path.exists("/.dockerenv"):
            # Docker環境：ホストパスに変換して表示
            host_videos_path = os.getenv("HOST_VIDEOS_PATH", str(video_parent))
            display_path = os.path.join(host_videos_path, f"{safe_name}_TextffCut")
        else:
            # ローカル環境：そのまま表示
            display_path = str(project_path)
        
        st.code(display_path, language=None)

    def _execute_processing(
        self,
        process_type: str,
        primary_format: str,
        export_srt: bool,
        timeline_fps: str
    ) -> None:
        """処理を実行"""
        # 必要な情報を取得
        video_path = SessionStateManager.get("video_path")
        transcription = SessionStateManager.get("transcription_result")
        time_ranges = SessionStateManager.get("time_ranges")
        edited_text = SessionStateManager.get("edited_text", "")
        full_text = SessionStateManager.get("original_text", "")
        
        if not edited_text:
            st.error("切り抜き箇所が指定されていません。")
            return
        
        # API設定を反映
        if SessionStateManager.get("use_api", False):
            self.config.transcription.use_api = True
            self.config.transcription.api_key = SessionStateManager.get("api_key", "")
        else:
            self.config.transcription.use_api = False
        
        # タイムライン編集で調整された時間範囲があれば使用
        if "adjusted_time_ranges" in st.session_state:
            st.info(
                f"📊 タイムライン編集済みの時間範囲を使用します"
                f"（{len(st.session_state.adjusted_time_ranges)}クリップ）"
            )
            time_ranges = st.session_state.adjusted_time_ranges
        
        # 出力ディレクトリの設定
        video_name = Path(video_path).stem
        safe_name = get_safe_filename(video_name)
        video_parent = Path(video_path).parent
        project_dir = video_parent / f"{safe_name}_TextffCut"
        project_path = ensure_directory(Path(project_dir), clean=False)
        
        # 処理タイプに応じたサフィックス
        type_suffix = "Clip" if process_type == "切り抜きのみ" else "NoSilence"
        
        # デバッグ情報の表示
        with st.expander("🔍 デバッグ情報", expanded=True):
            st.write(f"処理に使用する時間範囲: {len(time_ranges)}クリップ")
            for i, (start, end) in enumerate(time_ranges[:3]):
                st.write(
                    f"  - クリップ{i+1}: {start:.1f}秒 〜 {end:.1f}秒 "
                    f"(長さ: {end-start:.1f}秒)"
                )
            if len(time_ranges) > 3:
                st.write(f"  ... 他 {len(time_ranges) - 3} クリップ")
        
        # ProcessingContextで処理を実行
        with st.spinner("処理中..."), ProcessingContext(project_path) as temp_manager:
            try:
                # プログレスバーを初期化
                progress_bar, status_text = show_progress(0, "処理を開始しています...")
                
                # 無音削除処理
                keep_ranges = self._process_silence_removal(
                    process_type, video_path, time_ranges,
                    progress_bar, status_text
                )
                
                if not keep_ranges:
                    return
                
                # 出力形式に応じて処理
                if primary_format in ["FCPXMLファイル", "Premiere Pro XML"]:
                    self._process_xml_output(
                        primary_format, video_path, keep_ranges,
                        project_path, safe_name, type_suffix,
                        export_srt, time_ranges, edited_text,
                        full_text, transcription, timeline_fps,
                        process_type, progress_bar, status_text
                    )
                else:
                    self._process_video_output(
                        video_path, keep_ranges, project_path,
                        safe_name, type_suffix, export_srt,
                        time_ranges, edited_text, full_text,
                        transcription, timeline_fps, process_type,
                        progress_bar, status_text
                    )
                
            except Exception as e:
                logger.error(f"処理中にエラーが発生: {e}")
                st.error(f"処理中にエラーが発生しました: {str(e)}")

    def _process_silence_removal(
        self,
        process_type: str,
        video_path: str,
        time_ranges: List[Tuple[float, float]],
        progress_bar,
        status_text
    ) -> Optional[List[Tuple[float, float]]]:
        """無音削除処理"""
        if process_type == "切り抜きのみ":
            # 切り抜きのみの場合はtime_rangesをそのまま使用
            show_progress(0.5, "切り抜き箇所を処理中...", progress_bar, status_text)
            return time_ranges
        else:
            # 無音削除付きで処理
            def progress_callback(progress, status):
                show_progress(progress, status, progress_bar, status_text)
            
            # 無音削除設定を取得
            noise_threshold = SessionStateManager.get("noise_threshold", -35)
            min_silence_duration = SessionStateManager.get("min_silence_duration", 0.3)
            min_segment_duration = SessionStateManager.get("min_segment_duration", 0.3)
            padding_start = SessionStateManager.get("padding_start", 0.1)
            padding_end = SessionStateManager.get("padding_end", 0.1)
            
            # time_rangesからセグメントを作成
            segments_for_removal = []
            for start, end in time_ranges:
                segments_for_removal.append(
                    TranscriptionSegment(start=start, end=end, text="", words=[])
                )
            
            silence_result = self.video_service.remove_silence(
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
                return [(seg.start, seg.end) for seg in adjusted_segments]
            else:
                st.error(f"無音削除エラー: {silence_result.error}")
                return None

    def _process_xml_output(
        self,
        primary_format: str,
        video_path: str,
        keep_ranges: List[Tuple[float, float]],
        project_path: Path,
        safe_name: str,
        type_suffix: str,
        export_srt: bool,
        time_ranges: List[Tuple[float, float]],
        edited_text: str,
        full_text: str,
        transcription: TranscriptionResult,
        timeline_fps: str,
        process_type: str,
        progress_bar,
        status_text
    ) -> None:
        """XML出力処理"""
        # 形式を決定
        if primary_format == "FCPXMLファイル":
            export_format = "fcpxml"
            xml_ext = ".fcpxml"
        else:  # Premiere Pro XML
            export_format = "xmeml"
            xml_ext = ".xml"
        
        xml_path = get_unique_path(project_path / f"{safe_name}_TextffCut_{type_suffix}{xml_ext}")
        
        # XMLの場合は空のセグメントでOK
        export_segments = []
        for i, (start, end) in enumerate(keep_ranges):
            export_segments.append(TranscriptionSegment(start=start, end=end, text="", words=[]))
        
        # XMLエクスポート実行
        export_result = self.export_service.execute(
            format=export_format,
            video_path=video_path,
            segments=export_segments,
            output_path=str(xml_path),
            project_name=f"{safe_name} Project",
            event_name="TextffCut",
            remove_silence=(process_type != "切り抜きのみ"),
        )
        
        if export_result.success:
            # メタデータから統計情報を取得
            timeline_pos = export_result.metadata.get("used_duration", 0)
            
            # パス表示（Docker環境ではホストパスに変換）
            display_path = get_display_path(xml_path)
            
            # SRT字幕も出力する場合
            if export_srt:
                srt_success = self._export_srt(
                    xml_path, project_path, time_ranges, keep_ranges,
                    edited_text, full_text, transcription,
                    timeline_fps, process_type
                )
                
                if srt_success:
                    srt_path = xml_path.with_suffix('.srt')
                    srt_display_path = get_display_path(srt_path)
                    show_progress(
                        1.0,
                        f"処理が完了しました！ 出力先: {display_path} | "
                        f"SRT字幕: {srt_display_path} | "
                        f"📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
                        progress_bar,
                        status_text,
                    )
                else:
                    show_progress(
                        1.0,
                        f"処理が完了しました！ 出力先: {display_path} | "
                        f"⚠️ SRT字幕の生成に失敗 | "
                        f"📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
                        progress_bar,
                        status_text,
                    )
            else:
                show_progress(
                    1.0,
                    f"処理が完了しました！ 出力先: {display_path} | "
                    f"📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
                    progress_bar,
                    status_text,
                )
            
            # 中間ファイルを削除
            cleanup_intermediate_files(
                project_path,
                keep_patterns=[
                    f"{safe_name}_TextffCut_*.fcpxml",
                    f"{safe_name}_TextffCut_*.xml",
                    f"{safe_name}_TextffCut_*.srt",
                    f"{safe_name}_TextffCut_*.mp4",
                    "transcriptions/",
                ],
            )
        else:
            st.error(f"{primary_format}ファイルの生成に失敗しました。")

    def _process_video_output(
        self,
        video_path: str,
        keep_ranges: List[Tuple[float, float]],
        project_path: Path,
        safe_name: str,
        type_suffix: str,
        export_srt: bool,
        time_ranges: List[Tuple[float, float]],
        edited_text: str,
        full_text: str,
        transcription: TranscriptionResult,
        timeline_fps: str,
        process_type: str,
        progress_bar,
        status_text
    ) -> None:
        """動画出力処理"""
        show_progress(0.0, "動画セグメントを抽出中...", progress_bar, status_text)
        
        output_files = []
        total_ranges = len(keep_ranges)
        
        # 各セグメントを抽出
        for i, (start, end) in enumerate(keep_ranges):
            progress = (i + 1) / total_ranges * 0.8  # 最大80%まで
            show_progress(
                progress, f"セグメント {i+1}/{total_ranges} を抽出中...", 
                progress_bar, status_text
            )
            
            segment_file = project_path / f"segment_{i+1}.mp4"
            
            # 一つのセグメントを抽出
            segments_to_extract = [VideoSegment(start=start, end=end)]
            
            extract_result = self.video_service.extract_segments(
                video_path=video_path,
                segments=segments_to_extract,
                output_dir=str(project_path),
                format="mp4",
            )
            
            if extract_result.success:
                extracted_files = extract_result.data
                if extracted_files:
                    # ファイル名をリネーム
                    import shutil
                    shutil.move(extracted_files[0], str(segment_file))
                    output_files.append(str(segment_file))
        
        # 結合処理
        if len(output_files) > 1:
            combined_path = get_unique_path(
                project_path / f"{safe_name}_TextffCut_{type_suffix}.mp4"
            )
            show_progress(0.8, "動画を統合しています...", progress_bar, status_text)
            
            merge_result = self.video_service.merge_videos(
                video_files=output_files,
                output_path=str(combined_path),
                progress_callback=lambda p, s: show_progress(
                    0.8 + p * 0.2, s, progress_bar, status_text
                ),
            )
            
            if merge_result.success:
                # パス表示
                display_path = get_display_path(project_path)
                
                # SRT字幕も出力する場合
                if export_srt:
                    srt_success = self._export_srt(
                        combined_path, project_path, time_ranges, keep_ranges,
                        edited_text, full_text, transcription,
                        timeline_fps, process_type
                    )
                    
                    if srt_success:
                        srt_path = combined_path.with_suffix('.srt')
                        srt_display_path = get_display_path(srt_path)
                        show_progress(
                            1.0,
                            f"処理が完了しました！ 出力先: {display_path} | "
                            f"SRT字幕: {srt_display_path} | "
                            f"📊 {len(keep_ranges)}個のセグメントを結合",
                            progress_bar,
                            status_text,
                        )
                    else:
                        show_progress(
                            1.0,
                            f"処理が完了しました！ 出力先: {display_path} | "
                            f"⚠️ SRT字幕の生成に失敗 | "
                            f"📊 {len(keep_ranges)}個のセグメントを結合",
                            progress_bar,
                            status_text,
                        )
                else:
                    show_progress(
                        1.0,
                        f"処理が完了しました！ 出力先: {display_path} | "
                        f"📊 {len(keep_ranges)}個のセグメントを結合",
                        progress_bar,
                        status_text,
                    )
                
                # 動画プレビュー
                st.video(str(combined_path))
                
                # 中間ファイルをクリーンアップ
                cleanup_intermediate_files(
                    project_path,
                    keep_patterns=[
                        f"{safe_name}_TextffCut_*.mp4",
                        f"{safe_name}_TextffCut_*.fcpxml",
                        f"{safe_name}_TextffCut_*.srt",
                        "transcriptions/",
                    ],
                )
            else:
                st.error("動画の結合に失敗しました")
        elif len(output_files) == 1:
            # 単一ファイルの場合はリネームのみ
            final_path = get_unique_path(
                project_path / f"{safe_name}_TextffCut_{type_suffix}.mp4"
            )
            import shutil
            shutil.move(output_files[0], str(final_path))
            
            display_path = get_display_path(project_path)
            show_progress(
                1.0,
                f"処理が完了しました！ 出力先: {display_path}",
                progress_bar,
                status_text,
            )
            
            st.video(str(final_path))

    def _export_srt(
        self,
        output_path: Path,
        project_path: Path,
        time_ranges: List[Tuple[float, float]],
        keep_ranges: List[Tuple[float, float]],
        edited_text: str,
        full_text: str,
        transcription: TranscriptionResult,
        timeline_fps: str,
        process_type: str
    ) -> bool:
        """SRT字幕のエクスポート"""
        try:
            # 出力ファイルのステムから連番を使用
            output_stem = output_path.stem
            srt_path = project_path / f"{output_stem}.srt"
            
            # 区切り文字の検出
            separator_patterns = ["---", "——", "－－－"]
            found_separator = None
            for pattern in separator_patterns:
                if pattern in edited_text:
                    found_separator = pattern
                    break
            
            # 差分情報を取得
            if found_separator:
                # 区切り文字を除去して差分計算
                text_without_separator = edited_text.replace(found_separator, " ")
                diff = self.text_processor.find_differences(full_text, text_without_separator)
            else:
                diff = self.text_processor.find_differences(full_text, edited_text)
            
            # SRT設定を取得
            srt_settings = SessionStateManager.get(
                "srt_settings",
                {
                    "min_duration": 0.5,
                    "max_duration": 7.0,
                    "gap_threshold": 0.1,
                    "chars_per_second": 15.0,
                    "max_line_length": 42,
                    "max_lines": 2,
                    "encoding": "utf-8",
                    "fps": float(timeline_fps),
                },
            )
            
            # FPSを追加
            srt_settings["fps"] = float(timeline_fps)
            
            # SRTエクスポーターを使用
            srt_exporter = SRTDiffExporter(self.config)
            
            if process_type == "切り抜きのみ":
                # 無音削除なし：従来の処理
                return srt_exporter.export_from_diff(
                    diff=diff,
                    transcription_result=transcription,
                    output_path=str(srt_path),
                    encoding=srt_settings.get("encoding", "utf-8"),
                    srt_settings=srt_settings,
                )
            else:
                # 無音削除あり：タイムマッピングを使用
                time_mapper = TimeMapper(time_ranges, keep_ranges)
                
                return srt_exporter.export_from_diff_with_silence_removal(
                    diff=diff,
                    transcription_result=transcription,
                    output_path=str(srt_path),
                    time_mapper=time_mapper,
                    encoding=srt_settings.get("encoding", "utf-8"),
                    srt_settings=srt_settings,
                )
        
        except Exception as e:
            logger.error(f"SRT出力エラー: {e}")
            return False