"""
StreamlitベースのUIコンポーネント
"""
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Callable

from config import Config
from utils.time_utils import format_time
from core.transcription import TranscriptionResult
from core.text_processor import TextDifference, TextProcessor




def show_api_key_manager():
    """
    APIキー管理UI（サイドバー用）
    """
    from utils.api_key_manager import api_key_manager
    from config import config
    
    st.markdown("#### 🔑 APIキー設定")
    
    # 保存されたAPIキーを確認
    saved_key = api_key_manager.load_api_key()
    
    if saved_key:
        # 保存されたキーがある場合
        masked_key = api_key_manager.mask_api_key(saved_key)
        st.success(f"✅ 保存されたAPIキー: {masked_key}")
        st.caption("🔒 APIキーは暗号化して保存されています")
        
        # 削除ボタンを保存済みキー情報の下に配置
        if st.button("🗑️ 保存済みキーを削除", use_container_width=True):
            if api_key_manager.delete_api_key():
                st.success("保存されたAPIキーを削除しました")
                st.rerun()
            else:
                st.error("APIキーの削除に失敗しました")
        
        # session_stateに保存
        st.session_state.api_key = saved_key
    else:
        # 保存されたキーがない場合のみ入力欄を表示
        api_key = st.text_input(
            "OpenAI APIキー",
            type="password",
            value=config.transcription.api_key or "",
            help="入力すると自動的に暗号化して保存されます"
        )
        
        # APIキーが入力されたら自動的に保存
        if api_key and api_key.startswith('sk-'):
            if api_key_manager.save_api_key(api_key):
                st.success("✅ APIキーを暗号化保存しました")
                st.rerun()
        
        # session_stateに保存
        st.session_state.api_key = api_key if api_key else ""






def show_transcription_controls(
    has_cache: bool = False,
    available_caches: List[Dict[str, Any]] = None
) -> Tuple[bool, bool, Optional[Dict[str, Any]]]:
    """
    文字起こしコントロールUI
    
    Args:
        has_cache: キャッシュが存在するか
        available_caches: 利用可能なキャッシュのリスト
        
    Returns:
        (キャッシュを使用するか, 新規実行するか, 選択されたキャッシュ情報)
    """
    use_cache = False
    run_new = False
    selected_cache = None
    
    # 利用可能なキャッシュがある場合は選択UI表示
    if available_caches:
        # 枠線で囲んで表示
        with st.container(border=True):
            st.markdown("#### 📝 過去の文字起こし結果を利用する")
            
            # キャッシュ選択用のセレクトボックス
            cache_options = []
            cache_map = {}
            
            for i, cache in enumerate(available_caches):
                from datetime import datetime
                modified_date = datetime.fromtimestamp(cache["modified_time"]).strftime("%Y-%m-%d %H:%M")
                
                option_text = f"{cache['mode']}モード - {cache['model_size']} | {modified_date}"
                cache_options.append(option_text)
                cache_map[option_text] = cache
            
            selected_option = st.selectbox(
                "保存済みの文字起こし結果",
                cache_options,
                help="使用する文字起こし結果を選択してください"
            )
            
            if selected_option:
                selected_cache = cache_map[selected_option]
            
            # キャッシュ使用ボタンを枠内に表示
            if selected_cache:
                if st.button("💾 選択した結果を使用", type="primary", use_container_width=True):
                    use_cache = True
    
    return use_cache, run_new, selected_cache


def show_silence_settings() -> Tuple[float, float, float, float, float]:
    """
    無音検出設定UI
    
    Returns:
        (noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end)
    """
    from utils import settings_manager
    
    st.markdown("#### 🔇 無音検出の設定")
    
    # デフォルト値
    DEFAULT_NOISE_THRESHOLD = -35
    DEFAULT_MIN_SILENCE_DURATION = 0.3
    DEFAULT_MIN_SEGMENT_DURATION = 0.3
    DEFAULT_PADDING_START = 0.1
    DEFAULT_PADDING_END = 0.1
    
    # 前回の設定を取得
    saved_threshold = settings_manager.get('noise_threshold', DEFAULT_NOISE_THRESHOLD)
    saved_silence = settings_manager.get('min_silence_duration', DEFAULT_MIN_SILENCE_DURATION)
    saved_segment = settings_manager.get('min_segment_duration', DEFAULT_MIN_SEGMENT_DURATION)
    saved_padding_start = settings_manager.get('padding_start', DEFAULT_PADDING_START)
    saved_padding_end = settings_manager.get('padding_end', DEFAULT_PADDING_END)
    
    # デフォルトに戻すボタン
    if st.button("🔧 パラメータをデフォルトに戻す", use_container_width=True):
        # 設定ファイルを更新
        settings_manager.set('noise_threshold', DEFAULT_NOISE_THRESHOLD)
        settings_manager.set('min_silence_duration', DEFAULT_MIN_SILENCE_DURATION)
        settings_manager.set('min_segment_duration', DEFAULT_MIN_SEGMENT_DURATION)
        settings_manager.set('padding_start', DEFAULT_PADDING_START)
        settings_manager.set('padding_end', DEFAULT_PADDING_END)
        
        # session_stateを更新
        st.session_state.noise_threshold = DEFAULT_NOISE_THRESHOLD
        st.session_state.min_silence_duration = DEFAULT_MIN_SILENCE_DURATION
        st.session_state.min_segment_duration = DEFAULT_MIN_SEGMENT_DURATION
        st.session_state.padding_start = DEFAULT_PADDING_START
        st.session_state.padding_end = DEFAULT_PADDING_END
        
        # 明示的に成功メッセージを表示
        st.success("パラメータをデフォルト値に戻しました")
        
        st.rerun()
    
    # session_stateにデフォルト値を設定（初回のみ）
    if 'noise_threshold' not in st.session_state:
        st.session_state.noise_threshold = saved_threshold
    if 'min_silence_duration' not in st.session_state:
        st.session_state.min_silence_duration = saved_silence
    if 'min_segment_duration' not in st.session_state:
        st.session_state.min_segment_duration = saved_segment
    if 'padding_start' not in st.session_state:
        st.session_state.padding_start = saved_padding_start
    if 'padding_end' not in st.session_state:
        st.session_state.padding_end = saved_padding_end
    
    # 無音検出設定を3カラムで横並び表示
    silence_col1, silence_col2, silence_col3 = st.columns(3)
    
    with silence_col1:
        noise_threshold = st.number_input(
            "無音検出の閾値 (dB)",
            min_value=-50,
            max_value=-20,
            value=st.session_state.noise_threshold,
            step=1,
            help="無音と判定する音量の閾値。値が小さいほど厳密に検出します。"
        )
    
    with silence_col2:
        min_silence_duration = st.number_input(
            "最小無音時間 (秒)",
            min_value=0.1,
            max_value=1.0,
            value=st.session_state.min_silence_duration,
            step=0.1,
            format="%.1f",
            help="無音と判定する最小の時間。値が大きいほど長い無音が必要です。"
        )
    
    with silence_col3:
        min_segment_duration = st.number_input(
            "最小セグメント時間 (秒)",
            min_value=0.1,
            max_value=1.0,
            value=st.session_state.min_segment_duration,
            step=0.1,
            format="%.1f",
            help="セグメントとして残す最小の時間。値が小さいほど細かく分割されます。"
        )
    
    st.markdown("**つなぎ部分の調整**")
    st.caption("セグメント前後に余白を追加して自然なつなぎにします")
    
    # パディング設定を2カラムで横並び表示
    padding_col1, padding_col2 = st.columns(2)
    
    with padding_col1:
        padding_start = st.number_input(
            "開始部分のパディング (秒)",
            min_value=0.0,
            max_value=0.5,
            value=st.session_state.padding_start,
            step=0.05,
            format="%.2f",
            help="各セグメントの開始前に追加する余白時間"
        )
    
    with padding_col2:
        padding_end = st.number_input(
            "終了部分のパディング (秒)",
            min_value=0.0,
            max_value=0.5,
            value=st.session_state.padding_end,
            step=0.05,
            format="%.2f",
            help="各セグメントの終了後に追加する余白時間"
        )
    
    # セッションと設定に保存
    st.session_state.noise_threshold = noise_threshold
    st.session_state.min_silence_duration = min_silence_duration
    st.session_state.min_segment_duration = min_segment_duration
    st.session_state.padding_start = padding_start
    st.session_state.padding_end = padding_end
    
    # 設定が変更されたら保存
    if noise_threshold != saved_threshold:
        settings_manager.set('noise_threshold', noise_threshold)
    if min_silence_duration != saved_silence:
        settings_manager.set('min_silence_duration', min_silence_duration)
    if min_segment_duration != saved_segment:
        settings_manager.set('min_segment_duration', min_segment_duration)
    if padding_start != saved_padding_start:
        settings_manager.set('padding_start', padding_start)
    if padding_end != saved_padding_end:
        settings_manager.set('padding_end', padding_end)
    
    return noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end


def show_export_settings() -> Tuple[str, str, int]:
    """
    エクスポート設定UI
    
    Returns:
        (process_type, output_format, timeline_fps)
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        process_type = st.radio(
            "処理方法",
            ["切り抜きのみ", "無音削除付き"],
            index=1,
            help="切り抜きのみ：指定した部分をそのまま切り出します\n無音削除付き：切り出した部分から無音を削除します"
        )
    
    with col2:
        output_format = st.radio(
            "出力形式",
            ["動画ファイル", "FCPXMLファイル", "Premiere Pro XML", "SRTファイル"],
            index=1,
            help="動画ファイル：MP4形式で出力\nFCPXMLファイル：Final Cut Pro用のXMLファイルを出力\nPremiere Pro XML：Premiere Pro用のXMEMLファイルを出力\nSRTファイル：字幕ファイル（SubRip形式）を出力"
        )
    
    with col3:
        timeline_fps = st.number_input(
            "タイムラインのフレームレート",
            min_value=24,
            max_value=60,
            value=30,
            step=1,
            help="FCPXMLファイルを生成する際のフレームレート"
        )
    
    return process_type, output_format, timeline_fps




def show_progress(
    progress: float,
    status: str,
    progress_bar: Optional[Any] = None,
    status_text: Optional[Any] = None
) -> Tuple[Any, Any]:
    """
    進捗表示UI
    
    Args:
        progress: 進捗率（0.0-1.0）
        status: ステータステキスト
        progress_bar: 既存のプログレスバー
        status_text: 既存のステータステキスト
        
    Returns:
        (progress_bar, status_text)
    """
    if progress_bar is None:
        progress_bar = st.progress(0)
    if status_text is None:
        status_text = st.empty()
    
    # 進捗を更新（1.0を超えないように）
    progress_bar.progress(min(progress, 1.0))
    
    # 完了時は成功メッセージとして表示
    if progress >= 1.0:
        status_text.success(status)
    else:
        status_text.info(status)
    
    return progress_bar, status_text


def show_separated_mode_status(container: Any = None):
    """
    分離モード用のステータス表示UI
    
    Args:
        container: 表示用コンテナ（Noneの場合は新規作成）
        
    Returns:
        status_container: ステータス表示用コンテナ
    """
    if container is None:
        container = st.container()
    
    with container:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("### 📝 ステップ 1/2: 文字起こし")
            transcribe_status = st.empty()
            transcribe_progress = st.progress(0)
            
        with col2:
            st.markdown("### 🔄 ステップ 2/2: アライメント")
            align_status = st.empty()
            align_progress = st.progress(0)
    
    return {
        'container': container,
        'transcribe_status': transcribe_status,
        'transcribe_progress': transcribe_progress,
        'align_status': align_status,
        'align_progress': align_progress
    }


def show_text_editor(
    initial_text: str = "",
    height: int = 400
) -> str:
    """
    テキスト編集UI
    
    Args:
        initial_text: 初期テキスト
        height: エディタの高さ
        
    Returns:
        編集されたテキスト
    """
    edited_text = st.text_area(
        label="切り抜き箇所",
        value=initial_text,
        height=height,
        label_visibility="collapsed",
        help="文字起こし結果から切り抜く文章をコピペしてください。\n\n**💡 複数セクション指定**\n区切り文字 `---` で分割すると、複数の箇所を個別に検索してマージできます。\n\n例:\n第1セクション\n---\n第2セクション\n---\n第3セクション"
    )
    
    return edited_text


def show_edited_text_with_highlights(
    edited_text: str,
    diff: Optional[TextDifference] = None,
    height: int = 400
):
    """
    編集テキストに赤ハイライト表示
    
    Args:
        edited_text: 編集されたテキスト
        diff: 差分情報
        height: ビューアの高さ
    """
    if not edited_text or diff is None:
        return
    
    # 編集テキストベースで赤ハイライトを生成
    html_content = f'<div class="edited-text-viewer" style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">'
    
    # シンプルな文字列検索ベースの方法
    # 既存の共通部分の情報を使用
    covered_positions = set()
    
    # 共通部分でカバーされている編集テキストの位置をマーク
    for common_pos in diff.common_positions:
        # 編集テキスト内でこの共通テキストを検索
        common_text = common_pos.text
        search_start = 0
        
        while True:
            found_pos = edited_text.find(common_text, search_start)
            if found_pos == -1:
                break
            
            # この位置がまだカバーされていない場合のみマーク
            if not any(pos in covered_positions for pos in range(found_pos, found_pos + len(common_text))):
                for i in range(found_pos, found_pos + len(common_text)):
                    covered_positions.add(i)
                break
            
            search_start = found_pos + 1
    
    # HTMLを生成
    for i, char in enumerate(edited_text):
        if i in covered_positions:
            html_content += char  # 元テキストに存在
        else:
            html_content += f'<span class="highlight-addition" style="background-color: #ffe6e6; color: #d00;">{char}</span>'  # 追加文字
    
    html_content += '</div>'
    
    st.markdown(html_content, unsafe_allow_html=True)


def show_edited_text_with_separators_highlights(
    edited_text: str,
    separator: str,
    height: int = 400
):
    """
    区切り文字を含むテキストの赤ハイライト表示
    
    Args:
        edited_text: 編集されたテキスト（区切り文字付き）
        separator: 区切り文字
        height: ビューアの高さ
    """
    from core.text_processor import TextProcessor
    text_processor = TextProcessor()
    
    # 元のテキストを取得
    full_text = ""
    if 'transcription_result' in st.session_state:
        full_text = st.session_state.transcription_result.get_full_text()
    
    # 編集テキストベースで赤ハイライトを生成
    html_content = f'<div class="edited-text-viewer" style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; white-space: pre-wrap; font-family: monospace;">'
    
    # セクションに分割
    sections = text_processor.split_text_by_separator(edited_text, separator)
    
    for i, section in enumerate(sections):
        # 各セクションの差分を計算
        section_diff = text_processor.find_differences(full_text, section)
        covered_positions = set()
        
        # 共通部分でカバーされている位置をマーク
        for common_pos in section_diff.common_positions:
            common_text = common_pos.text
            search_start = 0
            
            while True:
                found_pos = section.find(common_text, search_start)
                if found_pos == -1:
                    break
                
                if not any(pos in covered_positions for pos in range(found_pos, found_pos + len(common_text))):
                    for j in range(found_pos, found_pos + len(common_text)):
                        covered_positions.add(j)
                    break
                
                search_start = found_pos + 1
        
        # セクションのHTMLを生成
        for j, char in enumerate(section):
            if j in covered_positions:
                html_content += char  # 元テキストに存在
            else:
                html_content += f'<span class="highlight-addition" style="background-color: #ffe6e6; color: #d00;">{char}</span>'  # 追加文字
        
        # 区切り文字を追加（最後のセクション以外）
        if i < len(sections) - 1:
            html_content += f'\n<span style="color: #666; font-weight: bold;">{separator}</span>\n'
    
    html_content += '</div>'
    
    st.markdown(html_content, unsafe_allow_html=True)


@st.dialog("エラー箇所")
def show_red_highlight_modal(edited_text: str, diff: Optional[TextDifference] = None):
    """
    赤ハイライトのモーダル表示
    
    Args:
        edited_text: 編集されたテキスト
        diff: 差分情報
    """
    st.markdown("赤色の部分を削除してください。")
    
    # 元のテキスト（区切り文字付き）を取得
    original_edited_text = st.session_state.get('original_edited_text', edited_text)
    
    # 区切り文字があるかチェック
    separator_patterns = ["---", "——", "－－－"]
    found_separator = None
    for pattern in separator_patterns:
        if pattern in original_edited_text:
            found_separator = pattern
            break
    
    if found_separator:
        # 区切り文字がある場合：1つのエリアで区切り文字も含めて表示
        show_edited_text_with_separators_highlights(original_edited_text, found_separator, height=300)
    else:
        # 区切り文字がない場合：通常のプレビュー表示
        show_edited_text_with_highlights(edited_text, diff, height=300)
    
    if st.button("削除", type="primary", use_container_width=True, key="delete_highlights_modal"):
        # 区切り文字がある場合の処理
        original_edited_text = st.session_state.get('original_edited_text', edited_text)
        
        # 区切り文字パターンをチェック
        separator_patterns = ["---", "——", "－－－"]
        found_separator = None
        for pattern in separator_patterns:
            if pattern in original_edited_text:
                found_separator = pattern
                break
        
        if found_separator:
            # 区切り文字がある場合：各セクションから個別に赤ハイライト削除
            from core.text_processor import TextProcessor
            text_processor = TextProcessor()
            sections = text_processor.split_text_by_separator(original_edited_text, found_separator)
            
            # 元のテキストを取得（モーダル呼び出し元から）
            full_text = ""
            if 'transcription_result' in st.session_state:
                full_text = st.session_state.transcription_result.get_full_text()
            
            cleaned_sections = []
            for section in sections:
                section_diff = text_processor.find_differences(full_text, section)
                cleaned_section = "".join(pos.text for pos in section_diff.common_positions)
                if cleaned_section.strip():
                    cleaned_sections.append(cleaned_section)
            
            cleaned_text = f"\n{found_separator}\n".join(cleaned_sections)
        else:
            # 区切り文字がない場合：通常の処理
            cleaned_text = "".join(pos.text for pos in diff.common_positions)
        
        st.session_state.edited_text = cleaned_text
        st.session_state.show_modal = False
        st.session_state.show_error_and_delete = False  # エラー状態もクリア
        st.rerun()


def show_diff_viewer(
    original_text: str,
    diff: Optional[TextDifference] = None,
    height: int = 400
):
    """
    差分表示UI
    
    Args:
        original_text: 元のテキスト
        diff: 差分情報
        height: ビューアの高さ
    """
    if diff is None:
        # 差分がない場合は元のテキストを表示
        html_content = f'<div class="diff-viewer" style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">{original_text}</div>'
    else:
        # 差分をHTML形式で生成（従来通りシンプル版）
        html_content = '<div class="diff-viewer" style="height: ' + str(height) + 'px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">'
        
        current_pos = 0
        for pos in diff.common_positions:
            # 共通部分の前のテキスト（削除された部分）
            if current_pos < pos.start:
                html_content += original_text[current_pos:pos.start]
            
            # 共通部分（緑でハイライト - クラス名を追加）
            html_content += f'<span class="highlight-match" style="background-color: #e6ffe6;">{pos.text}</span>'
            current_pos = pos.end
        
        # 最後の部分
        if current_pos < len(original_text):
            html_content += original_text[current_pos:]
        
        html_content += '</div>'
    
    # HTMLコンテンツを表示
    st.markdown(html_content, unsafe_allow_html=True)





def show_help():
    """ヘルプ表示UI"""
    st.markdown("#### ❓ ヘルプ")
    
    st.markdown("""
    詳しい使い方はこちら：
    
    📖 **[TextffCutの使い方 - note](https://note.com/coidemo/n/n8250e4b95daa)**
    """)


def show_optimization_status():
    """自動最適化の状態表示（シンプル版）"""
    # 自動最適化が有効であることだけを表示
    st.info("🤖 自動最適化: 有効（診断フェーズ付き）")
    
    # 詳細を見たい人向け（折りたたみ、デフォルトで閉じている）
    with st.expander("処理状況", expanded=False):
        try:
            from core.memory_monitor import MemoryMonitor
            monitor = MemoryMonitor()
            
            current_memory = monitor.get_memory_usage()
            memory_stats = monitor.get_memory_stats()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("メモリ使用率", f"{current_memory:.0f}%")
            with col2:
                # 処理速度は実際の処理中のみ表示されるため、ここでは表示しない
                st.metric("利用可能メモリ", f"{memory_stats['available_gb']:.1f}GB")
            
            # 診断フェーズの説明
            st.caption("💡 最初の3チャンク（各30秒）で環境を診断し、最適なパラメータを自動設定します")
                
        except Exception as e:
            st.caption("メモリ情報を取得できませんでした")


