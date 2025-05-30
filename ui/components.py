"""
StreamlitベースのUIコンポーネント
"""
import streamlit as st
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Callable

from config import Config
from utils.file_utils import get_video_files
from utils.time_utils import format_time
from core.transcription import TranscriptionResult
from core.text_processor import TextDifference, TextProcessor


def show_video_selector(video_dir: Path) -> Optional[Path]:
    """
    動画ファイル選択UI
    
    Args:
        video_dir: 動画ディレクトリ
        
    Returns:
        選択された動画ファイルのパス
    """
    video_files = get_video_files(video_dir)
    
    if not video_files:
        st.warning(f"📁 {video_dir} に動画ファイルがありません。")
        st.info("動画ファイルを以下のフォルダに配置してください: " + str(video_dir))
        return None
    
    selected_video = st.selectbox(
        "🎬 動画ファイルを選択",
        options=video_files,
        format_func=lambda x: x.name
    )
    
    return selected_video


def show_model_selector(config: Config) -> str:
    """
    Whisperモデル選択UI
    
    Args:
        config: アプリケーション設定
        
    Returns:
        選択されたモデル名
    """
    from utils import settings_manager
    
    # 前回の設定を取得
    saved_model = settings_manager.get('model_size', config.transcription.whisper_models[0])
    default_index = config.transcription.whisper_models.index(saved_model) if saved_model in config.transcription.whisper_models else 0
    
    model_size = st.selectbox(
        "Whisperモデル",
        options=config.transcription.whisper_models,
        index=default_index,
        help="large-v3: 最高精度（メモリ使用量大）\nmedium: バランスが良い\nsmall/base: 軽量"
    )
    
    # 設定が変更されたら保存
    if model_size != saved_model:
        settings_manager.set('model_size', model_size)
    
    # メモリ使用量の警告
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if model_size == "large-v3" and device == "cpu":
        st.warning("⚠️ large-v3モデルはCPUで実行すると非常に時間がかかります")
    
    return model_size


def show_transcription_controls(
    has_cache: bool = False
) -> Tuple[bool, bool]:
    """
    文字起こしコントロールUI
    
    Args:
        has_cache: キャッシュが存在するか
        
    Returns:
        (キャッシュを使用するか, 新規実行するか)
    """
    use_cache = False
    run_new = False
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 保存済み結果がある場合は新規実行をsecondary、ない場合はprimary
        button_type = "secondary" if has_cache else "primary"
        if st.button("🚀 新しく文字起こし実行", type=button_type, use_container_width=True):
            run_new = True
    
    with col2:
        if has_cache:
            if st.button("💾 保存済み結果を使用", type="primary", use_container_width=True):
                use_cache = True
    
    return use_cache, run_new


def show_silence_settings() -> Tuple[float, float, float, float, float]:
    """
    無音検出設定UI
    
    Returns:
        (noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end)
    """
    from utils import settings_manager
    
    st.subheader("無音検出の設定")
    
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
        settings_manager.set('noise_threshold', DEFAULT_NOISE_THRESHOLD)
        settings_manager.set('min_silence_duration', DEFAULT_MIN_SILENCE_DURATION)
        settings_manager.set('min_segment_duration', DEFAULT_MIN_SEGMENT_DURATION)
        settings_manager.set('padding_start', DEFAULT_PADDING_START)
        settings_manager.set('padding_end', DEFAULT_PADDING_END)
        st.session_state.noise_threshold = DEFAULT_NOISE_THRESHOLD
        st.session_state.min_silence_duration = DEFAULT_MIN_SILENCE_DURATION
        st.session_state.min_segment_duration = DEFAULT_MIN_SEGMENT_DURATION
        st.session_state.padding_start = DEFAULT_PADDING_START
        st.session_state.padding_end = DEFAULT_PADDING_END
        st.rerun()
    
    noise_threshold = st.slider(
        "無音検出の閾値 (dB)",
        min_value=-50,
        max_value=-20,
        value=st.session_state.get('noise_threshold', saved_threshold),
        step=1,
        help="無音と判定する音量の閾値。値が小さいほど厳密に検出します。"
    )
    
    min_silence_duration = st.slider(
        "最小無音時間 (秒)",
        min_value=0.1,
        max_value=1.0,
        value=st.session_state.get('min_silence_duration', saved_silence),
        step=0.1,
        help="無音と判定する最小の時間。値が大きいほど長い無音が必要です。"
    )
    
    min_segment_duration = st.slider(
        "最小セグメント時間 (秒)",
        min_value=0.1,
        max_value=1.0,
        value=st.session_state.get('min_segment_duration', saved_segment),
        step=0.1,
        help="セグメントとして残す最小の時間。値が小さいほど細かく分割されます。"
    )
    
    st.markdown("**つなぎ部分の調整**")
    st.caption("セグメント前後に余白を追加して自然なつなぎにします")
    
    padding_start = st.slider(
        "開始部分のパディング (秒)",
        min_value=0.0,
        max_value=0.5,
        value=st.session_state.get('padding_start', saved_padding_start),
        step=0.05,
        help="各セグメントの開始前に追加する余白時間"
    )
    
    padding_end = st.slider(
        "終了部分のパディング (秒)",
        min_value=0.0,
        max_value=0.5,
        value=st.session_state.get('padding_end', saved_padding_end),
        step=0.05,
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
            ["動画ファイル", "FCPXMLファイル"],
            index=1,
            help="動画ファイル：MP4形式で出力\nFCPXMLファイル：Final Cut Pro用のXMLファイルを出力"
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
    html_content = f'<div style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">'
    
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
            html_content += f'<span style="background-color: #ffe6e6; color: #d00;">{char}</span>'  # 追加文字
    
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
    html_content = f'<div style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; white-space: pre-wrap; font-family: monospace;">'
    
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
                html_content += f'<span style="background-color: #ffe6e6; color: #d00;">{char}</span>'  # 追加文字
        
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
        html_content = f'<div style="height: {height}px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">{original_text}</div>'
    else:
        # 差分をHTML形式で生成（従来通りシンプル版）
        html_content = '<div style="height: ' + str(height) + 'px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">'
        
        current_pos = 0
        for pos in diff.common_positions:
            # 共通部分の前のテキスト（削除された部分）
            if current_pos < pos.start:
                html_content += original_text[current_pos:pos.start]
            
            # 共通部分（緑でハイライト）
            html_content += f'<span style="background-color: #e6ffe6;">{pos.text}</span>'
            current_pos = pos.end
        
        # 最後の部分
        if current_pos < len(original_text):
            html_content += original_text[current_pos:]
        
        html_content += '</div>'
    
    # HTMLコンテンツを表示
    st.markdown(html_content, unsafe_allow_html=True)



def show_segment_preview(
    segments: List[Dict[str, Any]],
    video_files: Optional[List[str]] = None
):
    """
    セグメントプレビューUI
    
    Args:
        segments: セグメント情報のリスト
        video_files: 動画ファイルのリスト
    """
    with st.expander("抽出部分と生成された動画", expanded=False):
        for i, segment in enumerate(segments):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**{segment['start']:.1f}s - {segment['end']:.1f}s**")
                if 'text' in segment:
                    st.markdown(segment['text'])
            
            with col2:
                if video_files and i < len(video_files):
                    st.video(video_files[i])
            
            st.markdown("---")


def show_help():
    """ヘルプ表示UI"""
    st.header("ヘルプ")
    st.markdown("""
    ### 使い方
    1. 動画ファイルを`videos`フォルダに配置
    2. 動画を選択して文字起こしを実行
    3. テキストを編集して必要な部分を抽出
    4. 動画の切り出しや無音部分の削除を実行
    
    ### 区切り文字機能
    複数の箇所を一括で切り抜きたい場合は、区切り文字 `---` を使用できます：
    
    ```
    第1セクション
    ---
    第2セクション
    ---
    第3セクション
    ```
    
    **メリット**：
    - 長い文章で意図しない箇所が選択される問題を解決
    - 複数の離れた箇所を一括で切り抜き可能
    - セクション毎に個別に検索してマージ
    
    ### よくある質問
    Q: 対応している動画形式は？  
    A: MP4, MOV, AVI, MKV, WMVに対応しています。
    
    Q: 文字起こしの精度は？  
    A: Whisperモデルのサイズによって異なります。large-v3が最も高精度です。
    
    Q: 無音部分の削除とは？  
    A: 指定した閾値以下の音量が一定時間続く部分を削除します。
    """)