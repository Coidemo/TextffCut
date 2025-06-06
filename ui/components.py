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
            ["動画ファイル", "FCPXMLファイル", "Premiere Pro XML"],
            index=1,
            help="動画ファイル：MP4形式で出力\nFCPXMLファイル：Final Cut Pro用のXMLファイルを出力\nPremiere Pro XML：Premiere Pro用のXMEMLファイルを出力"
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


def show_advanced_settings():
    """高度な設定UI"""
    from config import config
    from utils import settings_manager
    
    st.markdown("#### ⚡ 高度な設定")
    st.caption("メモリとパフォーマンスに関する詳細設定")
    
    # 環境情報を取得
    try:
        import psutil
        mem_gb = psutil.virtual_memory().total / (1024**3)
        cpu_count = psutil.cpu_count(logical=False) or 4
        
        st.info(f"💻 検出された環境: メモリ{mem_gb:.0f}GB / CPU {cpu_count}コア")
    except:
        mem_gb = 16
        cpu_count = 4
        st.info("💻 環境情報を取得できませんでした")
    
    # 操作ボタン
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 環境に合わせて自動最適化", use_container_width=True):
            # メモリ容量に基づく最適化
            if mem_gb >= 64:  # エンタープライズ
                api_chunk_opt = 300  # 5分
                api_workers_opt = 5
                local_chunk_opt = 90  # 90秒（安定性重視）
                local_workers_opt = min(cpu_count - 2, 8)
                batch_size_opt = 8  # CPU環境では8が上限
            elif mem_gb >= 32:  # プロ
                api_chunk_opt = 240  # 4分
                api_workers_opt = 4
                local_chunk_opt = 60  # 60秒
                local_workers_opt = min(cpu_count - 2, 6)
                batch_size_opt = 8
            elif mem_gb >= 16:  # 高性能
                api_chunk_opt = 180  # 3分
                api_workers_opt = 3
                local_chunk_opt = 45  # 45秒
                local_workers_opt = min(cpu_count - 1, 4)
                batch_size_opt = 6
            elif mem_gb >= 8:  # 標準
                api_chunk_opt = 120  # 2分
                api_workers_opt = 2
                local_chunk_opt = 30  # 30秒
                local_workers_opt = 2
                batch_size_opt = 4
            else:  # 軽量
                api_chunk_opt = 60  # 1分
                api_workers_opt = 1
                local_chunk_opt = 20  # 20秒
                local_workers_opt = 1
                batch_size_opt = 2  # メモリ不足対策
            
            # 設定を保存
            settings_manager.set('api_chunk_seconds', api_chunk_opt)
            settings_manager.set('api_max_workers', api_workers_opt)
            settings_manager.set('api_retry_count', 3)
            settings_manager.set('api_align_chunk_seconds', min(api_chunk_opt * 2, 600))
            settings_manager.set('chunk_seconds', local_chunk_opt)
            settings_manager.set('max_workers', local_workers_opt)
            settings_manager.set('batch_size', batch_size_opt)
            # ローカルアライメントチャンクサイズも設定（文字起こしチャンクの2倍、最大300秒）
            settings_manager.set('local_align_chunk_seconds', min(local_chunk_opt * 2, 300))
            
            st.success(f"メモリ{mem_gb:.0f}GBの環境に最適化された設定を適用しました")
            st.rerun()
    
    with col2:
        if st.button("🛡️ 最も安定した設定にする", use_container_width=True):
            # 最も保守的な設定
            settings_manager.set('api_chunk_seconds', 60)  # 1分
            settings_manager.set('api_max_workers', 1)
            settings_manager.set('api_retry_count', 3)
            settings_manager.set('api_align_chunk_seconds', 120)
            settings_manager.set('chunk_seconds', 20)
            settings_manager.set('max_workers', 1)
            settings_manager.set('batch_size', 2)  # 最小値で安定性重視
            settings_manager.set('local_align_chunk_seconds', 60)  # 安定性重視で小さめ
            
            st.success("最も安定した設定（メモリ使用量最小）を適用しました")
            st.rerun()
    
    # APIモードとローカルモードの両方の設定を表示
    st.markdown("##### 🌐 APIモード設定")
    st.caption("APIを使用する場合の詳細設定")
    
    # 保存された設定を読み込み
    saved_api_chunk = settings_manager.get('api_chunk_seconds', config.transcription.api_chunk_seconds)
    saved_api_workers = settings_manager.get('api_max_workers', config.transcription.api_max_workers)
    saved_api_retry = settings_manager.get('api_retry_count', config.transcription.api_retry_count)
    saved_api_align_chunk = settings_manager.get('api_align_chunk_seconds', config.transcription.api_align_chunk_seconds)
    
    # APIチャンクサイズ（安全な範囲に制限）
    api_chunk = st.slider(
        "APIチャンクサイズ（秒）",
        min_value=30,
        max_value=480,  # 8分に制限（安全マージン）
        value=min(saved_api_chunk, 480),
        step=30,
        help="音声を分割する単位。OpenAI APIの25MB制限により最大8分に制限。推奨: 2-5分。"
    )
    
    # API並列リクエスト数（安全な範囲に制限）
    api_workers = st.slider(
        "API並列リクエスト数",
        min_value=1,
        max_value=5,  # 5に制限
        value=min(saved_api_workers, 5),
        step=1,
        help="同時にAPIに送信するリクエスト数。OpenAIのレート制限を考慮して最大5に制限。"
    )
    
    # リトライ回数
    retry_count = st.slider(
        "APIリトライ回数",
        min_value=0,
        max_value=5,
        value=saved_api_retry,
        step=1,
        help="APIエラー時の再試行回数。"
    )
    
    # アライメント処理のチャンクサイズ
    api_align_chunk = st.slider(
        "アライメントチャンクサイズ（秒）",
        min_value=60,
        max_value=600,
        value=saved_api_align_chunk,
        step=60,
        help="APIで取得した文字と音声の同期処理時の分割単位。大きいほど効率的ですが、メモリを多く使用します。"
    )
    
    # アライメント処理は常にサブプロセスで実行（メモリリーク対策）
    api_align_subprocess = True
    
    # 設定を保存
    config.transcription.api_chunk_seconds = api_chunk
    config.transcription.api_max_workers = api_workers
    config.transcription.api_retry_count = retry_count
    config.transcription.api_align_chunk_seconds = api_align_chunk
    config.transcription.api_align_in_subprocess = api_align_subprocess
    
    # 設定が変更されたら保存
    if api_chunk != saved_api_chunk:
        settings_manager.set('api_chunk_seconds', api_chunk)
    if api_workers != saved_api_workers:
        settings_manager.set('api_max_workers', api_workers)
    if retry_count != saved_api_retry:
        settings_manager.set('api_retry_count', retry_count)
    if api_align_chunk != saved_api_align_chunk:
        settings_manager.set('api_align_chunk_seconds', api_align_chunk)
    
    st.markdown("---")
    
    # ローカルモードの設定
    st.markdown("##### 🖥️ ローカルモード設定")
    st.caption("ローカルで処理する場合の詳細設定")
    
    # 保存された設定を読み込み
    saved_chunk_seconds = settings_manager.get('chunk_seconds', config.transcription.chunk_seconds)
    saved_max_workers = settings_manager.get('max_workers', config.transcription.max_workers)
    saved_batch_size = settings_manager.get('batch_size', config.transcription.batch_size)
    saved_local_align_chunk = settings_manager.get('local_align_chunk_seconds', config.transcription.local_align_chunk_seconds)
    saved_force_separated = settings_manager.get('force_separated_mode', config.transcription.force_separated_mode)
    
    # チャンクサイズ（現実的な範囲に調整）
    chunk_seconds = st.slider(
        "文字起こしチャンクサイズ（秒）",
        min_value=10,
        max_value=300,  # 5分まで（メモリと処理のバランス）
        value=saved_chunk_seconds,
        step=10,
        help="文字起こし処理を行う単位。長時間動画では分離モードが自動的に有効になり、文字起こしとアライメントを別々に処理します。推奨: 30-60秒。"
    )
    
    # アライメントチャンクサイズ（ローカルモード用）
    local_align_chunk = st.slider(
        "アライメントチャンクサイズ（秒）",
        min_value=30,
        max_value=600,
        value=saved_local_align_chunk,
        step=30,
        help="文字と音声の同期処理時の分割単位。文字起こしチャンクサイズより大きく設定することで、メモリ効率が向上します。推奨: 60-300秒。"
    )
    
    # 並列処理数（現実的な範囲に調整）
    max_workers = st.slider(
        "並列処理数",
        min_value=1,
        max_value=16,  # 16コアまで（多くの環境で十分）
        value=saved_max_workers or 2,
        step=1,
        help=f"同時に処理するプロセス数（CPUコア単位）。この環境のCPU: {cpu_count}コア。推奨: {max(1, cpu_count//2)}〜{cpu_count}。各プロセスがメモリを使用するため、メモリ容量も考慮してください。"
    )
    config.transcription.max_workers = max_workers
    
    # バッチサイズ（CPU環境用に範囲を制限）
    batch_size = st.slider(
        "バッチサイズ",
        min_value=1,
        max_value=8,  # CPU環境では8まで
        value=min(saved_batch_size, 8),
        step=1,
        help="WhisperXの内部バッチサイズ。CPU環境では大きな効果はありません。推奨: 4-8。メモリが少ない場合は1-4に下げてください。"
    )
    
    # 分離モードの強制設定
    force_separated = st.checkbox(
        "分離モードを強制的に使用",
        value=saved_force_separated,
        help="文字起こしとアライメントを常に分離して処理します。長時間動画や低メモリ環境で安定性が向上しますが、処理時間が長くなる場合があります。"
    )
    
    # 設定を保存
    config.transcription.chunk_seconds = chunk_seconds
    config.transcription.batch_size = batch_size
    config.transcription.local_align_chunk_seconds = local_align_chunk
    config.transcription.force_separated_mode = force_separated
    
    # 設定が変更されたら保存
    if chunk_seconds != saved_chunk_seconds:
        settings_manager.set('chunk_seconds', chunk_seconds)
    if max_workers != saved_max_workers:
        settings_manager.set('max_workers', max_workers)
    if batch_size != saved_batch_size:
        settings_manager.set('batch_size', batch_size)
    if local_align_chunk != saved_local_align_chunk:
        settings_manager.set('local_align_chunk_seconds', local_align_chunk)
    if force_separated != saved_force_separated:
        settings_manager.set('force_separated_mode', force_separated)
    
    # 共通の注意事項
    st.caption("⚠️ これらの設定はメモリ使用量とパフォーマンスに大きく影響します。")
    st.caption("💡 メモリ不足エラーが発生する場合は、値を小さくしてください。")


