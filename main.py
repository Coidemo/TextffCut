"""
TextffCut - メインアプリケーション
リファクタリング版：モジュール化された構造を使用
"""
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional
import subprocess
from datetime import datetime

from config import config
from core import Transcriber, TextProcessor, VideoProcessor, FCPXMLExporter, ExportSegment, VideoSegment
from utils.file_utils import ensure_directory, get_safe_filename
from utils import ProcessingContext, cleanup_intermediate_files
from ui import (
    show_video_input,
    show_model_selector,
    show_transcription_controls,
    show_silence_settings,
    show_export_settings,
    show_progress,
    show_text_editor,
    show_diff_viewer,
    show_edited_text_with_highlights,
    show_red_highlight_modal,
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




def main():
    """メインアプリケーション"""
    
    # サイドバー
    with st.sidebar:
        # タブで設定を整理
        tab1, tab2, tab3 = st.tabs(["⚙️ 基本設定", "💾 保存設定", "❓ ヘルプ"])
        
        with tab1:
            st.header("基本設定")
            
            # モデル選択
            model_size = show_model_selector(config)
            
            # 無音検出のパラメータ
            noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end = show_silence_settings()
        
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
                from utils.progress import create_simple_progress
                progress_callback = create_simple_progress("文字起こし処理中...")
                
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
        
        # エラー表示（2カラムの上に表示）
        if st.session_state.get('show_error_and_delete', False):
            st.error("⚠️ 元動画に存在しない文字が切り抜き箇所に入力されています。削除してください。")
        
        # 全テキストを取得
        full_text = transcription.get_full_text()
        
        
        # 2カラムレイアウト
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した箇所が緑色でハイライトされます")
            
            # 編集されたテキストがある場合は差分を表示
            saved_edited_text = st.session_state.get('edited_text', '')
            if saved_edited_text:
                text_processor = TextProcessor()
                
                # 区切り文字がある場合は区切り文字対応の差分表示
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None
                for pattern in separator_patterns:
                    if pattern in saved_edited_text:
                        found_separator = pattern
                        break
                
                if found_separator:
                    # 区切り文字がある場合：区切り文字を除去して差分計算
                    text_without_separator = saved_edited_text.replace(found_separator, ' ')  # スペースで置換
                    diff = text_processor.find_differences(full_text, text_without_separator)
                    show_diff_viewer(full_text, diff)
                else:
                    # 区切り文字がない場合：従来通り
                    diff = text_processor.find_differences(full_text, saved_edited_text)
                    show_diff_viewer(full_text, diff)
            else:
                show_diff_viewer(full_text)
        
        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く箇所を入力してください")
            
            
            # テキストエディタ
            edited_text = show_text_editor(
                st.session_state.get('edited_text', ''),
                height=400
            )
            
# モーダル表示の処理を削除（更新ボタンでのみ表示するため）
            
            # 文字数と時間の表示
            display_text = edited_text
            
            # 保存されたテキストがあれば、それを優先
            saved_edited_text = st.session_state.get('edited_text', '')
            if saved_edited_text:
                display_text = saved_edited_text
            
            
            if display_text:
                # 時間計算
                text_processor = TextProcessor()
                
                # 区切り文字パターンをチェック
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None
                
                for pattern in separator_patterns:
                    if pattern in display_text:
                        found_separator = pattern
                        break
                
                if found_separator:
                    time_ranges = text_processor.find_differences_with_separator(full_text, display_text, transcription, found_separator)
                    sections = text_processor.split_text_by_separator(display_text, found_separator)
                    separator_info = f" / セクション数: {len(sections)}"
                else:
                    diff = text_processor.find_differences(full_text, display_text)
                    time_ranges = diff.get_time_ranges(transcription)
                    separator_info = ""
                
                total_duration = sum(end - start for start, end in time_ranges)
                st.caption(f"文字数: {len(display_text)}文字 / 時間: {total_duration:.1f}秒（無音削除前）{separator_info}")
            
            # ボタンを横並びに配置
            button_col1, button_col2 = st.columns([1, 2])
            
            with button_col1:
                # 更新ボタン
                if st.button("🔄 更新", type="primary", use_container_width=True):
                    st.session_state.edited_text = edited_text
                    
                    # 赤ハイライトがあるかチェック
                    if edited_text:
                        text_processor = TextProcessor()
                        
                        # 区切り文字対応
                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in edited_text:
                                found_separator = pattern
                                break
                        
                        has_additions = False
                        if found_separator:
                            # 区切り文字がある場合：各セクションで追加文字をチェック
                            sections = text_processor.split_text_by_separator(edited_text, found_separator)
                            for section in sections:
                                diff = text_processor.find_differences(full_text, section)
                                if diff.has_additions():
                                    has_additions = True
                                    break
                            
                            # 区切り文字がある場合は、区切り文字を除去した全体テキストを渡す
                            if has_additions:
                                text_without_separator = edited_text.replace(found_separator, ' ')
                                diff = text_processor.find_differences(full_text, text_without_separator)
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = text_without_separator
                                st.session_state.original_edited_text = edited_text  # 元のテキスト（区切り文字付き）も保存
                        else:
                            # 区切り文字がない場合：通常のチェック
                            diff = text_processor.find_differences(full_text, edited_text)
                            if diff.has_additions():
                                has_additions = True
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = edited_text
                                st.session_state.original_edited_text = edited_text
                        
                        if has_additions:
                            # エラー表示と削除ボタンを表示状態にする
                            st.session_state.show_error_and_delete = True
                            st.rerun()
                        else:
                            # エラー状態をクリア
                            st.session_state.show_error_and_delete = False
                            st.rerun()
            
            with button_col2:
                # 削除ボタン（エラーがある場合のみ表示）
                if st.session_state.get('show_error_and_delete', False):
                    if st.button("エラー箇所を確認して削除", key="delete_highlights_main", use_container_width=True):
                        st.session_state.show_modal = True
                        st.rerun()
        
        # 切り抜き処理
        if edited_text and 'edited_text' in st.session_state:
            st.header("🎬 切り抜き箇所の抽出")
            
            # 処理オプション
            st.subheader("処理オプション")
            process_type, output_format, timeline_fps = show_export_settings()
            
            if process_type == "無音削除付き":
                st.markdown("**無音削除の設定**")
                st.info("現在の設定：\n"
                       f"- 無音検出の閾値: {noise_threshold}dB\n"
                       f"- 最小無音時間: {min_silence_duration}秒\n"
                       f"- 最小セグメント時間: {min_segment_duration}秒\n"
                       f"- 開始パディング: {padding_start}秒\n"
                       f"- 終了パディング: {padding_end}秒\n\n"
                       "設定を変更する場合は、左のサイドパネルの「基本設定」タブから変更してください。")
            
            # 処理実行ボタン
            if st.button("🚀 処理を実行", type="primary", use_container_width=True):
                # 区切り文字対応の差分検索を使用
                text_processor = TextProcessor()
                
                # 区切り文字の様々なパターンをチェック（処理実行時）
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None
                
                for pattern in separator_patterns:
                    if pattern in edited_text:
                        found_separator = pattern
                        break
                
                if found_separator:
                    # 区切り文字対応処理
                    time_ranges = text_processor.find_differences_with_separator(full_text, edited_text, transcription, found_separator)
                    
                    # 各セクションで追加文字チェック
                    sections = text_processor.split_text_by_separator(edited_text, found_separator)
                    has_additions = False
                    for section in sections:
                        diff = text_processor.find_differences(full_text, section)
                        if diff.has_additions():
                            has_additions = True
                            break
                    
                    if has_additions:
                        st.error("元の動画に存在しない部分が含まれています。各セクションを確認してください。")
                        return
                        
                    st.info(f"区切り文字 '{found_separator}' により {len(sections)} セクションに分割して処理します。")
                        
                else:
                    # 従来の処理
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
                        
                        # 残す時間範囲を決定
                        if process_type == "切り抜きのみ":
                            # 切り抜きのみの場合はtime_rangesをそのまま使用
                            keep_ranges = time_ranges
                            show_progress(0.5, "切り抜き箇所を処理中...", progress_bar, status_text)
                            
                        else:
                            # 無音削除付きで処理（新フロー）
                            def progress_callback(progress, status):
                                show_progress(progress, status, progress_bar, status_text)
                            
                            # 無音を検出して残す時間範囲を取得
                            keep_ranges = video_processor.remove_silence_new(
                                video_path,
                                time_ranges,
                                str(project_path),
                                noise_threshold,
                                min_silence_duration,
                                min_segment_duration,
                                padding_start=padding_start,
                                padding_end=padding_end,
                                progress_callback=progress_callback
                            )
                        
                        # 出力形式に応じて処理
                        if output_format == "FCPXMLファイル":
                            # FCPXMLを生成（時間範囲から直接）
                            fcpxml_path = project_path / f"{safe_name}.fcpxml"
                            
                            # エクスポート用セグメントを構築（隙間を詰めて配置）
                            export_segments = []
                            timeline_pos = 0.0
                            
                            for start, end in keep_ranges:
                                export_segments.append(ExportSegment(
                                    source_path=video_path,
                                    start_time=start,
                                    end_time=end,
                                    timeline_start=timeline_pos
                                ))
                                timeline_pos += (end - start)  # 隙間を詰める
                            
                            success = fcpxml_exporter.export(
                                export_segments,
                                str(fcpxml_path),
                                timeline_fps,
                                f"{safe_name} Project"
                            )
                            
                            if success:
                                st.success(f"FCPXMLファイルを生成しました！\n出力先: {fcpxml_path}")
                                st.info(f"📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒")
                                
                                # FCPXMLの場合は中間ファイルを全て削除
                                cleanup_intermediate_files(project_path, keep_patterns=["*.fcpxml"])
                            else:
                                st.error("FCPXMLファイルの生成に失敗しました。")
                        else:
                            # 動画ファイル出力（時間範囲から抽出）
                            show_progress(0.0, "動画セグメントを抽出中...", progress_bar, status_text)
                            
                            output_files = []
                            total_ranges = len(keep_ranges)
                            
                            for i, (start, end) in enumerate(keep_ranges):
                                progress = i / total_ranges
                                show_progress(progress, f"セグメント {i+1}/{total_ranges} を抽出中...", progress_bar, status_text)
                                
                                segment_file = project_path / f"segment_{i+1}.mp4"
                                success = video_processor.extract_segment(
                                    video_path,
                                    start,
                                    end,
                                    str(segment_file)
                                )
                                
                                if success:
                                    output_files.append(str(segment_file))
                            
                            # 結合処理
                            if len(output_files) > 1:
                                combined_path = project_path / "combined.mp4"
                                show_progress(0.8, "動画を統合しています...", progress_bar, status_text)
                                
                                success = video_processor.combine_videos(
                                    output_files,
                                    str(combined_path),
                                    lambda p, s: show_progress(0.8 + p * 0.2, s, progress_bar, status_text)
                                )
                                
                                if success:
                                    st.success(f"処理が完了しました！\n出力先: {project_path}")
                                    st.video(str(combined_path))
                                    st.info(f"📊 {len(keep_ranges)}個のセグメントを結合")
                                    
                                    # 中間ファイルをクリーンアップ（結合ファイルは保持）
                                    cleanup_intermediate_files(project_path, keep_patterns=["combined.mp4"])
                                else:
                                    st.error("動画の結合に失敗しました")
                                    
                            elif output_files:
                                st.success(f"処理が完了しました！\n出力先: {project_path}")
                                st.video(output_files[0])
                                
                                # 中間ファイルをクリーンアップ
                                cleanup_intermediate_files(project_path, keep_patterns=["*.mp4"])
                            else:
                                st.error("動画の抽出に失敗しました")
                        
                        
                    except Exception as e:
                        st.error(f"処理中にエラーが発生しました: {str(e)}")

    # モーダル表示
    if st.session_state.get('show_modal', False):
        show_red_highlight_modal(
            st.session_state.get('current_edited_text', ''),
            st.session_state.get('current_diff', None)
        )


if __name__ == "__main__":
    # セッション終了時のクリーンアップを登録
    import atexit
    atexit.register(cleanup_temp_files)
    
    main()