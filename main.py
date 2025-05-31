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
from utils.time_utils import format_time
from utils import ProcessingContext, cleanup_intermediate_files
from ui import (
    show_video_input,
    show_api_key_manager,
    show_transcription_mode_selector,
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
        st.title("⚙️ 設定")
        
        # タブで設定を整理
        tab1, tab2, tab3 = st.tabs(["🔑 APIキー", "🔇 無音検出", "❓ ヘルプ"])
        
        with tab1:
            # APIキー管理のみ
            show_api_key_manager()
        
        with tab2:
            # 無音検出のパラメータ
            noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end = show_silence_settings()
        
        with tab3:
            show_help()
    
    # 動画ファイル選択（新しい入力方式）
    video_input = show_video_input()
    if not video_input:
        return
    
    video_path, output_dir = video_input
    
    # 動画パス変更の検知とクリア処理
    previous_video_path = st.session_state.get('current_video_path', '')
    if previous_video_path != video_path:
        # 動画が変更された場合、前の文字起こし結果と関連状態をクリア
        session_keys_to_clear = [
            'transcription_result',      # 文字起こし結果
            'edited_text',              # 編集されたテキスト
            'original_edited_text',     # 元の編集テキスト
            'show_modal',               # モーダル表示状態
            'show_error_and_delete',    # エラー表示状態
            'transcription_confirmed',  # 文字起こし設定確認状態
            'should_run_transcription', # 文字起こし実行フラグ
            'show_confirmation_modal',  # 確認モーダル状態
            'confirmation_info',        # 確認情報
            'last_modal_settings',      # 最後のモーダル設定
            'modal_dismissed',          # モーダル閉じられたフラグ
            'modal_button_pressed',     # モーダルボタン押下フラグ
            'transcription_in_progress', # 文字起こし処理中フラグ
            'cancel_transcription',     # 文字起こし中止フラグ
            'previous_transcription_mode', # 前回の文字起こしモード
            'previous_transcription_model' # 前回の文字起こしモデル
        ]
        
        for key in session_keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # 現在の動画パスを保存
        st.session_state.current_video_path = video_path
    
    # 文字起こし処理
    st.markdown("---")
    st.subheader("📝 文字起こし")
    
    # モード・モデル変更の検知と処理中止（確認画面で選択される前なので一時的にコメントアウト）
    # current_mode = st.session_state.get('use_api', False)
    # current_model = model_size
    # previous_mode = st.session_state.get('previous_transcription_mode', None)
    # previous_model = st.session_state.get('previous_transcription_model', None)
    
    # モードまたはモデルが変更された場合の処理中止（確認画面で選択されるまでコメントアウト）
    # mode_changed = previous_mode is not None and previous_mode != current_mode
    # model_changed = previous_model is not None and previous_model != current_model
    
    # if mode_changed or model_changed:
        # # モーダル関連のフラグをリセット
        # if 'last_modal_settings' in st.session_state:
        #     del st.session_state.last_modal_settings
        # if 'modal_dismissed' in st.session_state:
        #     del st.session_state.modal_dismissed
        # if 'show_confirmation_modal' in st.session_state:
        #     del st.session_state.show_confirmation_modal
        # if 'transcription_confirmed' in st.session_state:
        #     del st.session_state.transcription_confirmed
        # if 'should_run_transcription' in st.session_state:
        #     del st.session_state.should_run_transcription
        # if 'modal_button_pressed' in st.session_state:
        #     del st.session_state.modal_button_pressed
        #     
        # # 処理中の場合は中止
        # if st.session_state.get('transcription_in_progress', False):
        #     st.session_state.cancel_transcription = True
        #     st.session_state.transcription_in_progress = False
        #     
        #     if mode_changed:
        #         st.warning("⚠️ モードが変更されました。文字起こし処理を中止しました。")
        #     elif model_changed:
        #         st.warning("⚠️ モデルが変更されました。文字起こし処理を中止しました。")
    
    # 現在のモードとモデルを保存（確認画面で決定されるまでコメントアウト）
    # st.session_state.previous_transcription_mode = current_mode
    # st.session_state.previous_transcription_model = current_model
    
    transcriber = Transcriber(config)
    
    # 利用可能なキャッシュを取得
    available_caches = transcriber.get_available_caches(video_path)
    
    # キャッシュ選択UIを表示（設定が決まる前なので、全キャッシュを表示）
    use_cache, run_new, selected_cache = show_transcription_controls(False, available_caches)
    
    if use_cache and selected_cache:
        # 選択されたキャッシュを読み込み
        result = transcriber.load_from_cache(selected_cache['file_path'])
        if result:
            st.session_state.transcription_result = result
            
            # 選択されたキャッシュの設定をセッションに反映
            if selected_cache['is_api']:
                st.success(f"✅ APIモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")
            else:
                st.success(f"✅ ローカルモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")
            
            st.rerun()
    
    # 文字起こし実行の確認画面を常に表示（キャッシュがない場合、または新規実行したい場合）
    if True:  # 常に表示
        # 動画情報を取得
        try:
            from core.video import VideoInfo
            video_info = VideoInfo.from_file(video_path)
            duration_minutes = video_info.duration / 60
            
            # 確認画面を表示（過去の結果がある場合のみ区切り線とタイトルを表示）
            if available_caches:
                st.markdown("---")
                st.markdown("#### 🚀 新たに文字起こしする")
                # 常に上書き警告を表示
                st.warning("⚠️ 同じ設定の過去の文字起こし結果は上書きされます")
            
            # モードとモデル選択を表示
            use_api, model_size = show_transcription_mode_selector()
            
            # 動画時間情報の表示
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("📊 **動画時間**")
                st.markdown(f"{duration_minutes:.1f}分 ({format_time(video_info.duration)})")
            
            with col2:
                # 空白列（レイアウト調整）
                pass
            
            # APIモードの場合は料金情報表示
            if use_api:
                estimated_cost_usd = duration_minutes * 0.006
                estimated_cost_jpy = estimated_cost_usd * 150
                
                st.markdown("💰 **推定料金**")
                cost_col1, cost_col2 = st.columns(2)
                with cost_col1:
                    st.markdown(f"USD: ${estimated_cost_usd:.3f}")
                with cost_col2:
                    st.markdown(f"日本円: 約{estimated_cost_jpy:.0f}円")
                
                # 注意事項
                st.info("""
**注意事項:**
• OpenAI Whisper API料金: $0.006/動画1分あたり（2025年5月時点）  
• 為替レート変動: 円換算は概算です  
• 失敗時課金: 処理に失敗した場合も課金される可能性があります  
• 最新料金: [OpenAI公式サイト](https://openai.com/pricing)で必ずご確認ください
                """)
            
            # GPU/CPU情報はタブ内で表示されるため、ここでは削除
            
            # 実行ボタン（保存済みの文字起こしがあるかどうかで表示を変更）
            if available_caches:
                # 保存済みの文字起こしがある場合
                if use_api:
                    button_text = "💳 新たにAPIで文字起こしを実行する"
                else:
                    button_text = "🖥️ 新たにローカルで文字起こしを実行する"
                button_type = "secondary"  # 白塗り
            else:
                # 保存済みの文字起こしがない場合
                if use_api:
                    button_text = "💳 APIで文字起こしを実行する"
                else:
                    button_text = "🖥️ ローカルで文字起こしを実行する"
                button_type = "primary"  # 赤塗り
            
            if st.button(button_text, type=button_type, use_container_width=True):
                # APIモードでAPIキーチェック
                if use_api and not st.session_state.get('api_key'):
                    st.error("⚠️ APIキーが設定されていません。サイドバーのAPIキー設定で設定してください。")
                    return
                
                # 確認情報を保存
                st.session_state.confirmation_info = {
                    'mode': 'api' if use_api else 'local',
                    'model_size': model_size,
                    'duration_minutes': duration_minutes,
                    'formatted_time': format_time(video_info.duration)
                }
                if use_api:
                    st.session_state.confirmation_info.update({
                        'estimated_cost_usd': estimated_cost_usd,
                        'estimated_cost_jpy': estimated_cost_jpy
                    })
                
                # 実行フラグを設定
                st.session_state.should_run_transcription = True
                
                # 現在のモードとモデルを保存（変更検知用）
                st.session_state.previous_transcription_mode = use_api
                st.session_state.previous_transcription_model = model_size
                
                st.rerun()
                    
        except Exception as e:
            st.error(f"動画情報の取得に失敗: {e}")
            return
    
    # 文字起こし実行の判定
    should_run_transcription = st.session_state.get('should_run_transcription', False)
    
    if should_run_transcription:
        # 実行フラグをリセット（次回実行時のため）
        if 'should_run_transcription' in st.session_state:
            del st.session_state.should_run_transcription
        
        # 処理中止フラグをリセット
        st.session_state.cancel_transcription = False
        st.session_state.transcription_in_progress = True
        
        # キャンセルボタンを表示
        cancel_placeholder = st.empty()
        with cancel_placeholder.container():
            if st.button("❌ 処理を中止", type="secondary", use_container_width=True):
                st.session_state.cancel_transcription = True
                st.session_state.transcription_in_progress = False
                st.warning("文字起こし処理を中止しました。")
                return
        
        with st.spinner("文字起こし中..."):
            try:
                # キャンセルチェック
                if st.session_state.get('cancel_transcription', False):
                    st.session_state.transcription_in_progress = False
                    st.warning("文字起こし処理が中止されました。")
                    return
                
                # 実行前にAPI設定を反映（確認モーダルの情報を使用）
                confirmation_info = st.session_state.get('confirmation_info', {})
                if confirmation_info.get('mode') == 'api':
                    config.transcription.use_api = True
                    config.transcription.api_key = st.session_state.get('api_key', '')
                else:
                    config.transcription.use_api = False
                
                # 設定を反映したTranscriberを再初期化
                transcriber = Transcriber(config)
                
                # シンプルなプログレスコールバック
                progress_bar = st.progress(0)
                progress_text = st.empty()
                
                def cancellable_progress_callback(progress: float, status: str):
                    """キャンセル可能なプログレスコールバック"""
                    if st.session_state.get('cancel_transcription', False):
                        raise InterruptedError("処理が中止されました")
                    progress_bar.progress(min(progress, 1.0))
                    progress_text.info(status)
                
                progress_callback = cancellable_progress_callback
                
                # 文字起こし実行（新規実行：キャッシュ読み込みせず、結果は保存）
                model_to_use = confirmation_info.get('model_size', 'base')
                result = transcriber.transcribe(
                    video_path, 
                    model_to_use,
                    progress_callback=progress_callback,
                    use_cache=False,
                    save_cache=True
                )
                
                if result:
                    st.session_state.transcription_result = result
                    st.session_state.transcription_in_progress = False
                    # UI要素をクリーンアップ
                    cancel_placeholder.empty()
                    progress_bar.empty()
                    progress_text.empty()
                    st.success("✅ 文字起こし完了！")
                    st.rerun()
                    
            except InterruptedError as e:
                # キャンセルされた場合
                st.session_state.transcription_in_progress = False
                cancel_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()
                st.warning(f"⚠️ {str(e)}")
            except Exception as e:
                # その他のエラー
                st.session_state.transcription_in_progress = False
                cancel_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()
                st.error(f"❌ エラー: {str(e)}")
    
    # 文字起こし結果の処理
    if 'transcription_result' in st.session_state and st.session_state.transcription_result:
        transcription = st.session_state.transcription_result
        
        st.markdown("---")
        st.subheader("✂️ 切り抜き箇所の指定")
        
        # 現在表示中の文字起こし情報を表示
        model_info = transcription.model_size
        
        # APIモードかどうかの判定を改善
        # whisper-1_apiまたはwhisper-1のようなAPIモデル名を判定
        if "_api" in model_info or model_info == "whisper-1":
            mode_text = "API"
            model_text = model_info.replace("_api", "")
        else:
            mode_text = "ローカル"
            model_text = model_info
        
        st.caption(f"📝 現在の文字起こし結果: {mode_text}モード・{model_text}")
        
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
            st.markdown("---")
            st.subheader("🎬 切り抜き箇所の抽出")
            
            # 処理オプション
            st.markdown("#### ⚙️ 処理オプション")
            process_type, output_format, timeline_fps = show_export_settings()
            
            if process_type == "無音削除付き":
                st.markdown("##### 🔇 無音削除の設定")
                st.info("現在の設定：\n"
                       f"- 無音検出の閾値: {noise_threshold}dB\n"
                       f"- 最小無音時間: {min_silence_duration}秒\n"
                       f"- 最小セグメント時間: {min_segment_duration}秒\n"
                       f"- 開始パディング: {padding_start}秒\n"
                       f"- 終了パディング: {padding_end}秒\n\n"
                       "設定を変更する場合は、左のサイドパネルの「基本設定」タブから変更してください。")
            
            # 出力先の表示
            st.markdown("#### 📁 出力先")
            import os
            is_docker = os.path.exists('/.dockerenv')
            if is_docker:
                st.info("作業フォルダの videos/ ディレクトリ（動画と同じ場所）")
            else:
                video_name = Path(video_path).stem
                st.info(f"動画と同じ場所に {video_name}_TextffCut フォルダを作成して出力します。")
            
            # 処理実行ボタン
            if st.button("🚀 処理を実行", type="primary", use_container_width=True):
                # 実行前にAPI設定を反映
                if st.session_state.get('use_api', False):
                    config.transcription.use_api = True
                    config.transcription.api_key = st.session_state.get('api_key', '')
                else:
                    config.transcription.use_api = False
                
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
                
                # 出力ディレクトリの設定（動画と同じ場所にTextffCutフォルダ作成）
                video_name = Path(video_path).stem
                safe_name = get_safe_filename(video_name)
                video_parent = Path(video_path).parent
                
                # 動画と同じ場所にTextffCutフォルダを作成
                project_dir = video_parent / f"{safe_name}_TextffCut"
                
                # ディレクトリを作成（XMLファイル保護のためクリーンしない）
                project_path = ensure_directory(Path(project_dir), clean=False)
                
                # 処理タイプに応じたサフィックス（アルファベット表現）
                if process_type == "切り抜きのみ":
                    type_suffix = "Clip"
                else:
                    type_suffix = "NoSilence"
                
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
                            fcpxml_path = project_path / f"{safe_name}_TextffCut_{type_suffix}.fcpxml"
                            
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
                                # 100%完了を表示
                                show_progress(1.0, f"処理が完了しました！ 出力先: {fcpxml_path} | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒", progress_bar, status_text)
                                
                                # FCPXMLの場合は中間ファイルを削除（TextffCutファイルと文字起こしを保護）
                                cleanup_intermediate_files(project_path, keep_patterns=[f"{safe_name}_TextffCut_*.fcpxml", f"{safe_name}_TextffCut_*.mp4", "transcriptions/"])
                            else:
                                st.error("FCPXMLファイルの生成に失敗しました。")
                        else:
                            # 動画ファイル出力（時間範囲から抽出）
                            show_progress(0.0, "動画セグメントを抽出中...", progress_bar, status_text)
                            
                            output_files = []
                            total_ranges = len(keep_ranges)
                            
                            for i, (start, end) in enumerate(keep_ranges):
                                progress = (i + 1) / total_ranges * 0.8  # 最大80%まで
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
                                # 統一された命名規則で出力
                                combined_path = project_path / f"{safe_name}_TextffCut_{type_suffix}.mp4"
                                show_progress(0.8, "動画を統合しています...", progress_bar, status_text)
                                
                                success = video_processor.combine_videos(
                                    output_files,
                                    str(combined_path),
                                    lambda p, s: show_progress(0.8 + p * 0.2, s, progress_bar, status_text)
                                )
                                
                                if success:
                                    # 100%完了を表示
                                    show_progress(1.0, f"処理が完了しました！ 出力先: {project_path} | 📊 {len(keep_ranges)}個のセグメントを結合", progress_bar, status_text)
                                    
                                    # 動画プレビュー
                                    st.video(str(combined_path))
                                    
                                    # 中間ファイルをクリーンアップ（TextffCutファイルと文字起こしは保持）
                                    cleanup_intermediate_files(project_path, keep_patterns=[f"{safe_name}_TextffCut_*.mp4", f"{safe_name}_TextffCut_*.fcpxml", "transcriptions/"])
                                else:
                                    st.error("動画の結合に失敗しました")
                                    
                            elif output_files:
                                # 100%完了を表示
                                show_progress(1.0, f"処理が完了しました！ 出力先: {project_path}", progress_bar, status_text)
                                
                                # 動画プレビュー
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
    
    # モーダル表示は削除（メイン画面で確認表示に変更）


# モーダル関数は削除（メイン画面表示に変更）


if __name__ == "__main__":
    # セッション終了時のクリーンアップを登録
    import atexit
    atexit.register(cleanup_temp_files)
    
    main()