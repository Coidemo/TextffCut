"""
<<<<<<< Updated upstream
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
=======
Buzz Clip - メインアプリケーション
リファクタリング版：モジュール化された構造を使用
"""
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional
import subprocess

from config import config
from core import Transcriber, TextProcessor, VideoProcessor, FCPXMLExporter, SRTExporter, ExportSegment, VideoSegment
from utils.file_utils import ensure_directory, get_safe_filename
from utils import ProcessingContext, cleanup_intermediate_files
from ui import (
    show_video_input,
    show_model_selector,
    show_transcription_controls,
    show_silence_settings,
    show_export_settings,
    show_subtitle_settings,
    show_progress,
    show_text_editor,
    show_diff_viewer,
    show_help,
    cleanup_temp_files
)


# Streamlitの設定
st.set_page_config(
    page_title=config.ui.page_title,
    page_icon=config.ui.page_icon,
    layout=config.ui.layout,
    initial_sidebar_state="expanded"
)


def generate_srt_from_combined_audio(
    video_path: str,
    time_ranges: List[Tuple[float, float]],
    output_path: Path,
    video_name: str,
    chars_per_line: int,
    max_lines: int,
    model_size: str = "base",
    use_combined_video: bool = False,
    combined_video_path: Optional[str] = None,
    subtitle_model_size: Optional[str] = None
) -> bool:
    """
    結合音声から新たに文字起こししてSRT字幕ファイルを生成
    
    Args:
        video_path: 元の動画パス
        time_ranges: 切り抜き時間範囲のリスト
        output_path: 出力ディレクトリ
        video_name: 動画名（ファイル名用）
        chars_per_line: 1行あたりの文字数
        max_lines: 最大行数
        model_size: Whisperモデルサイズ（字幕用は軽量モデルで十分）
        use_combined_video: 結合済み動画を使用するか
        combined_video_path: 結合済み動画のパス
        
    Returns:
        成功したかどうか
    """
    try:
        # プログレス表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 1. 音声を抽出
        import time
        timestamp = int(time.time())
        audio_path = output_path / f"{video_name}_combined_{timestamp}.wav"
        
        
        # 動画のFPSを取得（結合動画または元動画から）
        source_video = combined_video_path if (use_combined_video and combined_video_path and Path(combined_video_path).exists()) else video_path
        video_fps = None
        try:
            fps_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(source_video)]
            fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
            if fps_result.returncode == 0:
                fps_str = fps_result.stdout.strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    video_fps = float(num) / float(den)
                else:
                    video_fps = float(fps_str)
        except Exception:
            pass
        
        if use_combined_video and combined_video_path and Path(combined_video_path).exists():
            # 結合済み動画から音声を抽出（シンプルで高速）
            status_text.text("結合動画から音声を抽出中...")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", str(combined_video_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                str(audio_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                st.error(f"音声抽出エラー: {result.stderr}")
                return False
            
            # 音声ファイルが正しく作成されたか確認
            if not audio_path.exists():
                st.error("音声ファイルが作成されませんでした")
                return False
                
            progress_bar.progress(0.3)
            
        else:
            # 元の動画から指定セグメントの音声を抽出
            status_text.text("音声を抽出中...")
            video_processor = VideoProcessor(config)
            segments = [VideoSegment(start=start, end=end) for start, end in time_ranges]
            
            success = video_processor.extract_audio_from_segments(
                video_path,
                segments,
                str(audio_path),
                lambda p, s: progress_bar.progress(p * 0.3)
            )
            
            if not success:
                st.error("音声抽出に失敗しました")
                return False
        
        # 2. 結合音声を文字起こし
        status_text.text("音声を文字起こし中...")
        transcriber = Transcriber(config)
        
        # 字幕用のモデルサイズを決定
        actual_model_size = subtitle_model_size if subtitle_model_size else model_size
        
        result = transcriber.transcribe(
            str(audio_path),
            model_size=actual_model_size,
            progress_callback=lambda p, s: (
                progress_bar.progress(0.3 + p * 0.6),
                status_text.text(s)
            ),
            use_cache=False  # 一時音声なのでキャッシュしない
        )
        
        if not result:
            st.error("文字起こしに失敗しました")
            return False
        
        # 3. SRT生成
        status_text.text("字幕ファイルを生成中...")
        
        srt_exporter = SRTExporter(config)
        # タイムスタンプを含めて新しいファイルであることを明確にする
        srt_filename = f"{video_name}_{timestamp}.srt"
        srt_path = output_path / srt_filename
        
        # 結合後の動画全体を1つのセグメントとして扱う
        # 音声の長さを取得
        audio_duration = 0
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
            result_probe = subprocess.run(cmd, capture_output=True, text=True)
            if result_probe.returncode == 0:
                audio_duration = float(result_probe.stdout.strip())
            else:
                # フォールバック：元のセグメントの合計時間
                audio_duration = sum(end - start for start, end in time_ranges)
        except:
            audio_duration = sum(end - start for start, end in time_ranges)
        
        # 結合動画がある場合は、そちらの長さを基準にする
        if use_combined_video and combined_video_path and Path(combined_video_path).exists():
            try:
                cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(combined_video_path)]
                result_probe = subprocess.run(cmd, capture_output=True, text=True)
                if result_probe.returncode == 0:
                    video_duration = float(result_probe.stdout.strip())
                    st.info(f"結合動画の長さ: {video_duration:.2f}秒 (音声: {audio_duration:.2f}秒)")
                    # 動画の長さを基準にする
                    audio_duration = video_duration
            except Exception as e:
                st.warning(f"結合動画の長さ取得エラー: {e}")
        
        full_segment = [VideoSegment(start=0, end=audio_duration)]
        
        
        success = srt_exporter.export(
            result,
            full_segment,
            str(srt_path),
            chars_per_line,
            max_lines,
            fps=video_fps,
            max_duration=audio_duration
        )
        
        # 4. クリーンアップ
        try:
            if audio_path.exists():
                audio_path.unlink()
        except Exception:
            pass
        
        progress_bar.progress(1.0)
        status_text.text("")
        
        if success:
            st.success(f"📝 字幕ファイルを生成しました: {srt_path.name}")
            
            return True
        
        return success
        
    except Exception as e:
        st.error(f"字幕生成エラー: {str(e)}")
        return False


def main():
    """メインアプリケーション"""
    st.title(f"{config.ui.page_icon} Buzz Clip")
    
    # サイドバー
    with st.sidebar:
        # タブで設定を整理
        tab1, tab2, tab3 = st.tabs(["⚙️ 基本設定", "💾 保存設定", "❓ ヘルプ"])
        
        with tab1:
            st.header("基本設定")
            
            # モデル選択
            model_size = show_model_selector(config)
            
            # 無音検出のパラメータ
            noise_threshold, min_silence_duration, min_segment_duration = show_silence_settings()
        
        with tab2:
            st.header("保存された設定")
            from utils import settings_manager
            
            # 現在の保存設定を表示
            saved_settings = settings_manager.get_all()
            if saved_settings:
                st.json(saved_settings)
                
                if st.button("🗑️ すべての設定をリセット", type="secondary"):
                    settings_manager.clear()
                    st.success("設定をリセットしました")
                    st.rerun()
            else:
                st.info("保存された設定はありません")
        
        with tab3:
            show_help()
    
    # 動画ファイル選択（新しい入力方式）
    video_input = show_video_input()
    if not video_input:
        return
    
    video_path, output_dir = video_input
    
    # 文字起こし処理
    st.header("📝 文字起こし")
    
    transcriber = Transcriber(config)
    cache_path = transcriber.get_cache_path(video_path, model_size)
    has_cache = cache_path.exists()
    
    use_cache, run_new = show_transcription_controls(has_cache)
    
    if use_cache:
        result = transcriber.load_from_cache(cache_path)
        if result:
            st.session_state.transcription_result = result
            st.success("✅ 文字起こし結果を読み込みました！")
            st.rerun()
    
    if run_new:
        with st.spinner("文字起こし中..."):
            try:
                # プログレスバーを表示
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def progress_callback(progress, status):
                    progress_bar.progress(progress)
                    status_text.text(status)
                
                # 文字起こし実行
                result = transcriber.transcribe(
                    video_path, 
                    model_size,
                    progress_callback=progress_callback
                )
                
                if result:
                    st.session_state.transcription_result = result
                    st.success("✅ 文字起こし完了！")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ エラー: {str(e)}")
    
    # 文字起こし結果の処理
    if 'transcription_result' in st.session_state and st.session_state.transcription_result:
        transcription = st.session_state.transcription_result
        
        st.header("✂️ 切り抜き箇所の指定")
        
        # 全テキストを取得
        full_text = transcription.get_full_text()
        
        # 2カラムレイアウト
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した文章が緑色でハイライトされます")
            
            # 編集されたテキストがある場合は差分を表示
            edited_text = st.session_state.get('edited_text', '')
            if edited_text:
                text_processor = TextProcessor()
                diff = text_processor.find_differences(full_text, edited_text)
                show_diff_viewer(full_text, diff)
            else:
                show_diff_viewer(full_text)
        
        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く文章をコピペしてください")
            
            # テキストエディタ
            edited_text = show_text_editor(
                st.session_state.get('edited_text', ''),
                height=400
            )
            
            # 文字数と時間の表示
            if edited_text:
                text_processor = TextProcessor()
                diff = text_processor.find_differences(full_text, edited_text)
                time_ranges = diff.get_time_ranges(transcription)
                total_duration = sum(end - start for start, end in time_ranges)
                
                st.caption(f"文字数: {len(edited_text)}文字 / 時間: {total_duration:.1f}秒（無音削除前）")
            
            # 更新ボタン
            if st.button("🔄 更新", type="primary"):
                st.session_state.edited_text = edited_text
                st.rerun()
        
        # 切り抜き処理
        if edited_text and 'edited_text' in st.session_state:
            st.header("🎬 切り抜き箇所の抽出")
            
            # 処理オプション
            st.markdown("### 処理オプション")
            process_type, output_format, timeline_fps, create_srt = show_export_settings()
            
            
            # SRT字幕の詳細設定
            if create_srt:
                chars_per_line, max_lines, subtitle_model_size = show_subtitle_settings()
            else:
                chars_per_line, max_lines, subtitle_model_size = 20, 2, "medium"
            
            if process_type == "無音削除付き":
                st.markdown("#### 無音削除の設定")
                st.info("現在の設定：\n"
                       f"- 無音検出の閾値: {noise_threshold}dB\n"
                       f"- 最小無音時間: {min_silence_duration}秒\n"
                       f"- 最小セグメント時間: {min_segment_duration}秒\n\n"
                       "設定を変更する場合は、左のサイドパネルの「基本設定」タブから変更してください。")
            
            # 処理実行ボタン
            if st.button("🚀 処理を実行", type="primary", use_container_width=True):
                # 差分からタイムスタンプを取得
                text_processor = TextProcessor()
                diff = text_processor.find_differences(full_text, edited_text)
                
                if diff.has_additions():
                    st.error("元の動画に存在しない部分が含まれています。赤いハイライト部分を確認してください。")
                    return
                
                time_ranges = diff.get_time_ranges(transcription)
                
                if not time_ranges:
                    st.error("切り抜き箇所が見つかりませんでした。")
                    return
                
                # 出力ディレクトリの設定
                video_name = Path(video_path).stem
                safe_name = get_safe_filename(video_name)
                
                if process_type == "切り抜きのみ":
                    project_dir = f"{output_dir}/{safe_name}_segments"
                else:
                    project_dir = f"{output_dir}/{safe_name}_no_fillers"
                
                # ディレクトリを作成（既存の場合はクリーン）
                project_path = ensure_directory(Path(project_dir), clean=True)
                
                # ProcessingContextで処理を実行（エラー時は自動クリーンアップ）
                with st.spinner("処理中..."), ProcessingContext(project_path) as temp_manager:
                    try:
                        video_processor = VideoProcessor(config)
                        fcpxml_exporter = FCPXMLExporter(config)
                        
                        # プログレスバーを初期化
                        progress_bar, status_text = show_progress(0, "処理を開始しています...")
                        
                        if process_type == "切り抜きのみ":
                            # セグメントを抽出
                            output_files = []
                            for i, (start, end) in enumerate(time_ranges):
                                output_file = project_path / f"segment_{i+1}.mp4"
                                
                                # 進捗を更新
                                progress = i / len(time_ranges)
                                status = f"セグメント {i+1}/{len(time_ranges)} を抽出中..."
                                show_progress(progress, status, progress_bar, status_text)
                                
                                success = video_processor.extract_segment(
                                    video_path,
                                    start,
                                    end,
                                    str(output_file)
                                )
                                
                                if success:
                                    output_files.append(str(output_file))
                            
                            # 成功メッセージ
                            st.success(f"切り出しが完了しました！ {len(output_files)}個の動画を生成しました。")
                            
                            # SRT字幕ファイルを生成
                            if create_srt:
                                generate_srt_from_combined_audio(
                                    video_path,
                                    time_ranges,
                                    project_path,
                                    safe_name,
                                    chars_per_line,
                                    max_lines,
                                    model_size,
                                    subtitle_model_size=subtitle_model_size
                                )
                            
                            # 中間ファイルをクリーンアップ（動画ファイル出力の場合）
                            if output_format == "動画ファイル":
                                cleanup_intermediate_files(project_path, keep_patterns=["*.mp4", "*.srt"])
                            
                        else:
                            # 無音削除付きで処理
                            segments = [
                                VideoSegment(
                                    start=start,
                                    end=end
                                )
                                for start, end in time_ranges
                            ]
                            
                            def progress_callback(progress, status):
                                show_progress(progress, status, progress_bar, status_text)
                            
                            # 無音を削除
                            output_files, segment_info = video_processor.remove_silence(
                                video_path,
                                str(project_path),
                                segments,
                                noise_threshold,
                                min_silence_duration,
                                min_segment_duration,
                                progress_callback=progress_callback
                            )
                            
                            
                            if output_format == "FCPXMLファイル":
                                # FCPXMLを生成
                                fcpxml_path = project_path / f"{safe_name}.fcpxml"
                                
                                # エクスポート用セグメントを構築
                                export_segments = []
                                for file_path, segment in segment_info.items():
                                    export_segments.append(ExportSegment(
                                        source_path=video_path,
                                        start_time=segment.start,
                                        end_time=segment.end,
                                        timeline_start=0
                                    ))
                                
                                # ソート
                                export_segments.sort(key=lambda s: s.start_time)
                                
                                success = fcpxml_exporter.export(
                                    export_segments,
                                    str(fcpxml_path),
                                    timeline_fps,
                                    f"{safe_name} Project"
                                )
                                
                                if success:
                                    st.success(f"FCPXMLファイルを生成しました！\n出力先: {fcpxml_path}")
                                    
                                    # SRT字幕ファイルを生成（FCPXMLの実際の長さに合わせる）
                                    if create_srt:
                                        # 無音削除後のセグメントを結合した動画を一時作成
                                        if output_files:
                                            temp_combined_path = project_path / "temp_combined_for_srt.mp4"
                                            video_processor = VideoProcessor(config)
                                            
                                            combine_success = video_processor.combine_videos(
                                                output_files,
                                                str(temp_combined_path),
                                                progress_callback=None
                                            )
                                            
                                            if combine_success:
                                                generate_srt_from_combined_audio(
                                                    video_path,
                                                    time_ranges,
                                                    project_path,
                                                    safe_name,
                                                    chars_per_line,
                                                    max_lines,
                                                    model_size,
                                                    use_combined_video=True,
                                                    combined_video_path=str(temp_combined_path),
                                                    subtitle_model_size=subtitle_model_size
                                                )
                                                
                                                # 一時ファイルを削除
                                                try:
                                                    temp_combined_path.unlink()
                                                except:
                                                    pass
                                            else:
                                                st.warning("字幕用結合動画の作成に失敗しました")
                                    
                                    # FCPXMLの場合は中間ファイルを全て削除
                                    cleanup_intermediate_files(project_path, keep_patterns=["*.fcpxml", "*.srt"])
                                else:
                                    st.error("FCPXMLファイルの生成に失敗しました。")
                            else:
                                # 動画を結合
                                if len(output_files) > 1:
                                    combined_path = project_path / "combined.mp4"
                                    
                                    # 結合前にファイルの存在を確認
                                    missing_files = []
                                    for file_path in output_files:
                                        if not Path(file_path).exists():
                                            missing_files.append(file_path)
                                    
                                    if missing_files:
                                        st.error("動画ファイルの結合に失敗しました")
                                        success = False
                                    else:
                                        show_progress(0.8, "動画を統合しています...", progress_bar, status_text)
                                        success = video_processor.combine_videos(
                                            output_files,
                                            str(combined_path),
                                            progress_callback
                                        )
                                    
                                    if success:
                                        st.success(f"処理が完了しました！\n出力先: {project_path}")
                                        st.video(str(combined_path))
                                        
                                        # SRT字幕ファイルを生成
                                        if create_srt:
                                            show_progress(0.9, "字幕ファイルを作成しています...", progress_bar, status_text)
                                            try:
                                                generate_srt_from_combined_audio(
                                                    video_path,
                                                    time_ranges,
                                                    project_path,
                                                    safe_name,
                                                    chars_per_line,
                                                    max_lines,
                                                    model_size,
                                                    use_combined_video=True,
                                                    combined_video_path=str(combined_path),
                                                    subtitle_model_size=subtitle_model_size
                                                )
                                            except Exception as e:
                                                st.error(f"字幕ファイルの作成に失敗しました")
                                        
                                        # 中間ファイルをクリーンアップ（結合ファイルは保持）
                                        cleanup_intermediate_files(project_path, keep_patterns=["combined.mp4", "*.srt"])
                                elif output_files:
                                    st.success(f"処理が完了しました！\n出力先: {project_path}")
                                    st.video(output_files[0])
                                    
                                    # SRT字幕ファイルを生成
                                    if create_srt:
                                        generate_srt_from_combined_audio(
                                            video_path,
                                            time_ranges,
                                            project_path,
                                            safe_name,
                                            chars_per_line,
                                            max_lines,
                                            model_size,
                                            subtitle_model_size=subtitle_model_size
                                        )
                                    
                                    # 中間ファイルをクリーンアップ
                                    cleanup_intermediate_files(project_path, keep_patterns=["*.mp4", "*.srt"])
                        
                        # セグメントプレビューを表示
                        if output_files and output_format == "動画ファイル":
                            segment_data = []
                            for i, ((start, end), file) in enumerate(zip(time_ranges[:len(output_files)], output_files)):
                                # 該当するテキストを探す
                                text = ""
                                for pos in diff.common_positions:
                                    pos_time_ranges = diff.get_time_ranges(transcription)
                                    for j, (t_start, t_end) in enumerate(pos_time_ranges):
                                        if abs(t_start - start) < 0.1 and abs(t_end - end) < 0.1:
                                            text = pos.text
                                            break
                                
                                segment_data.append({
                                    'start': start,
                                    'end': end,
                                    'text': text
                                })
                            
                        
                    except Exception as e:
                        st.error(f"処理中にエラーが発生しました: {str(e)}")


if __name__ == "__main__":
    # セッション終了時のクリーンアップを登録
    import atexit
    atexit.register(cleanup_temp_files)
    
    main()
>>>>>>> Stashed changes
