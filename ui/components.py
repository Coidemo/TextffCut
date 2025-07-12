"""
StreamlitベースのUIコンポーネント
"""

from typing import Any

import streamlit as st

from adapters.gateways.text_processing.simple_text_processor_gateway import SimpleTextProcessorGateway
from domain.entities.text_difference import TextDifference


def show_api_key_manager() -> None:
    """
    APIキー管理UI（サイドバー用）
    """
    from config import config
    from utils.api_key_manager import api_key_manager

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
                # セッション状態をクリア
                if "api_key" in st.session_state:
                    del st.session_state.api_key
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
            help="入力すると自動的に暗号化して保存されます",
        )

        # APIキーが入力されたら自動的に保存
        if api_key and api_key.startswith("sk-") and api_key_manager.save_api_key(api_key):
            st.success("✅ APIキーを暗号化保存しました")
            st.rerun()

        # session_stateに保存
        st.session_state.api_key = api_key if api_key else ""


def show_transcription_controls(
    _has_cache: bool = False, available_caches: list[dict[str, Any]] = None
) -> tuple[bool, bool, dict[str, Any] | None]:
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

            for _, cache in enumerate(available_caches):
                from datetime import datetime

                modified_date = datetime.fromtimestamp(cache["modified_time"]).strftime("%Y-%m-%d %H:%M")

                option_text = f"{cache['mode']}モード - {cache['model_size']} | {modified_date}"
                cache_options.append(option_text)
                cache_map[option_text] = cache

            # 最新のキャッシュをデフォルトで選択（最初の要素が最新）
            selected_option = st.selectbox(
                "保存済みの文字起こし結果", 
                cache_options, 
                index=0,  # 最初の要素（最新）を選択
                help="使用する文字起こし結果を選択してください"
            )

            if selected_option:
                selected_cache = cache_map[selected_option]

            # キャッシュ使用ボタンを枠内に表示（常に表示）
            if st.button("💾 選択した結果を使用", type="primary", use_container_width=True):
                if selected_cache:
                    use_cache = True

    return use_cache, run_new, selected_cache


def show_silence_settings() -> tuple[float, float, float, float, float]:
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
    saved_threshold = settings_manager.get("noise_threshold", DEFAULT_NOISE_THRESHOLD)
    saved_silence = settings_manager.get("min_silence_duration", DEFAULT_MIN_SILENCE_DURATION)
    saved_segment = settings_manager.get("min_segment_duration", DEFAULT_MIN_SEGMENT_DURATION)
    saved_padding_start = settings_manager.get("padding_start", DEFAULT_PADDING_START)
    saved_padding_end = settings_manager.get("padding_end", DEFAULT_PADDING_END)

    # デフォルトに戻すボタン
    if st.button("🔧 パラメータをデフォルトに戻す", use_container_width=True):
        # 設定ファイルを更新
        settings_manager.set("noise_threshold", DEFAULT_NOISE_THRESHOLD)
        settings_manager.set("min_silence_duration", DEFAULT_MIN_SILENCE_DURATION)
        settings_manager.set("min_segment_duration", DEFAULT_MIN_SEGMENT_DURATION)
        settings_manager.set("padding_start", DEFAULT_PADDING_START)
        settings_manager.set("padding_end", DEFAULT_PADDING_END)

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
    if "noise_threshold" not in st.session_state:
        st.session_state.noise_threshold = saved_threshold
    if "min_silence_duration" not in st.session_state:
        st.session_state.min_silence_duration = saved_silence
    if "min_segment_duration" not in st.session_state:
        st.session_state.min_segment_duration = saved_segment
    if "padding_start" not in st.session_state:
        st.session_state.padding_start = saved_padding_start
    if "padding_end" not in st.session_state:
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
            help="無音と判定する音量の閾値。値が小さいほど厳密に検出します。",
        )

    with silence_col2:
        min_silence_duration = st.number_input(
            "最小無音時間 (秒)",
            min_value=0.1,
            max_value=1.0,
            value=st.session_state.min_silence_duration,
            step=0.1,
            format="%.1f",
            help="無音と判定する最小の時間。値が大きいほど長い無音が必要です。",
        )

    with silence_col3:
        min_segment_duration = st.number_input(
            "最小セグメント時間 (秒)",
            min_value=0.1,
            max_value=1.0,
            value=st.session_state.min_segment_duration,
            step=0.1,
            format="%.1f",
            help="セグメントとして残す最小の時間。値が小さいほど細かく分割されます。",
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
            help="各セグメントの開始前に追加する余白時間",
        )

    with padding_col2:
        padding_end = st.number_input(
            "終了部分のパディング (秒)",
            min_value=0.0,
            max_value=0.5,
            value=st.session_state.padding_end,
            step=0.05,
            format="%.2f",
            help="各セグメントの終了後に追加する余白時間",
        )

    # セッションと設定に保存
    st.session_state.noise_threshold = noise_threshold
    st.session_state.min_silence_duration = min_silence_duration
    st.session_state.min_segment_duration = min_segment_duration
    st.session_state.padding_start = padding_start
    st.session_state.padding_end = padding_end

    # 設定が変更されたら保存
    if noise_threshold != saved_threshold:
        settings_manager.set("noise_threshold", noise_threshold)
    if min_silence_duration != saved_silence:
        settings_manager.set("min_silence_duration", min_silence_duration)
    if min_segment_duration != saved_segment:
        settings_manager.set("min_segment_duration", min_segment_duration)
    if padding_start != saved_padding_start:
        settings_manager.set("padding_start", padding_start)
    if padding_end != saved_padding_end:
        settings_manager.set("padding_end", padding_end)

    return noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end


def show_export_settings() -> tuple[str, str, bool, int]:
    """
    エクスポート設定UI（字幕オプション追加）

    Returns:
        (process_type, primary_format, export_srt, timeline_fps)
    """
    col1, col2, col3 = st.columns(3)

    with col1:
        process_type = st.radio(
            "処理方法",
            ["切り抜きのみ", "無音削除付き"],
            index=1,
            help="切り抜きのみ：指定した部分をそのまま切り出します\n無音削除付き：切り出した部分から無音を削除します",
        )

    with col2:
        # 主要な出力形式（SRT字幕を除外）
        primary_format = st.radio(
            "出力形式",
            ["動画ファイル", "FCPXMLファイル", "Premiere Pro XML"],
            index=1,
            help=(
                "動画ファイル：MP4形式で出力\n"
                "FCPXMLファイル：Final Cut Pro用のXMLファイルを出力\n"
                "Premiere Pro XML：Premiere Pro用のXMEMLファイルを出力"
            ),
        )

        # 字幕も同時出力するかのチェックボックス
        export_srt = st.checkbox(
            "SRT字幕も同時出力",
            value=True,
            help="動画またはXMLと同じタイミングでSRT字幕を出力します",
        )

    with col3:
        timeline_fps = st.number_input(
            "タイムラインのフレームレート",
            min_value=24,
            max_value=60,
            value=30,
            step=1,
            help="FCPXMLファイルを生成する際のフレームレート",
        )

    return process_type, primary_format, export_srt, timeline_fps


def show_progress(
    progress: float, status: str, progress_bar: Any | None = None, status_text: Any | None = None
) -> tuple[Any, Any]:
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


def show_separated_mode_status(container: Any = None) -> dict[str, Any]:
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
        "container": container,
        "transcribe_status": transcribe_status,
        "transcribe_progress": transcribe_progress,
        "align_status": align_status,
        "align_progress": align_progress,
    }


def show_text_editor(initial_text: str = "", height: int = 400) -> str:
    """
    テキスト編集UI（境界調整機能付き）

    Args:
        initial_text: 初期テキスト
        height: エディタの高さ

    Returns:
        編集されたテキスト
    """
    # テキストエディタ
    edited_text = st.text_area(
        label="切り抜き箇所",
        value=st.session_state.get("text_editor_value", initial_text),
        height=height,
        label_visibility="collapsed",
        key="text_editor_widget",
        help=(
            "文字起こし結果から切り抜く文章をコピペしてください。\n\n"
            "**💡 複数セクション指定**\n"
            "区切り文字 `---` で分割すると、複数の箇所を個別に検索してマージできます。\n\n"
            "例:\n第1セクション\n---\n第2セクション\n---\n第3セクション\n\n"
            "**🔍 文脈マーカー**\n"
            "検索に使いたいが出力には含めたくない文章を {} で囲むと、その部分は最終出力から除外されます。\n\n"
            "例: これは{検索のヒント}出力される部分です"
        ),
    )

    # エディタの値をセッション状態に保存
    if edited_text != st.session_state.get("text_editor_value", ""):
        st.session_state.text_editor_value = edited_text

    return edited_text


def show_edited_text_with_highlights(edited_text: str, diff: TextDifference | None = None, height: int = 400) -> None:
    """
    編集テキストに赤ハイライト表示（削除される部分のみ）

    削除ボタンで実際に削除される文字だけを赤くハイライトする
    """
    if not edited_text or diff is None:
        return

    html_content = (
        f'<div class="edited-text-viewer" style="height: {height}px; overflow-y: auto; '
        f'padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">'
    )
    
    # 文脈マーカーを検出
    import re
    context_markers = []
    for match in re.finditer(r'\{([^}]+)\}', edited_text):
        context_markers.append({
            'start': match.start(),
            'end': match.end(),
            'content': match.group(1)
        })

    # 削除ボタンを押した後のテキストを計算
    remaining_text = ""
    if hasattr(diff, "differences"):
        # ドメインエンティティの場合
        from domain.entities.text_difference import DifferenceType
        
        # UNCHANGEDの部分のみを結合（削除後に残る部分）
        remaining_text = "".join(
            diff_item[1] for diff_item in diff.differences 
            if len(diff_item) >= 3 and diff_item[0] == DifferenceType.UNCHANGED
        )
    
    # デバッグ情報をログ出力
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[show_edited_text_with_highlights] 元のテキスト長: {len(edited_text)}")
    logger.info(f"[show_edited_text_with_highlights] 削除後のテキスト長: {len(remaining_text)}")
    
    # 削除される文字を特定（元のテキストと削除後のテキストの差分）
    # シンプルなアプローチ：各文字が残るかどうかをチェック
    remaining_chars = list(remaining_text)
    remaining_index = 0
    
    # 文脈マーカー内かどうかを追跡
    in_context_marker = False
    skip_char = False
    
    for i, char in enumerate(edited_text):
        skip_char = False
        
        # 文脈マーカーの開始/終了をチェック
        for marker in context_markers:
            if i == marker['start']:
                in_context_marker = True
                # 開始の { も含める
                break
            elif i == marker['end'] - 1:
                # 終了の } の後で状態を戻す
                if char == '}':
                    in_context_marker = False
                break
        
        if skip_char:
            continue
        
        # 文脈マーカー内の文字もそのまま表示
        if in_context_marker:
            html_content += char
            continue
        
        # この文字が削除後のテキストに存在するかチェック
        if remaining_index < len(remaining_chars) and char == remaining_chars[remaining_index]:
            # この文字は残る（ハイライトしない）
            html_content += char
            remaining_index += 1
        else:
            # この文字は削除される（赤くハイライト）
            html_content += (
                f'<span class="highlight-deletion" style="background-color: #ffe6e6; '
                f'color: #d00; text-decoration: line-through;">{char}</span>'
            )
    
    logger.info(f"[show_edited_text_with_highlights] ハイライトされた文字数: {len(edited_text) - remaining_index}")

    html_content += "</div>"

    st.markdown(html_content, unsafe_allow_html=True)


def show_edited_text_with_separators_highlights(edited_text: str, separator: str, height: int = 400) -> None:
    """
    区切り文字を含むテキストの赤ハイライト表示（削除される部分のみ）

    Args:
        edited_text: 編集されたテキスト（区切り文字付き）
        separator: 区切り文字
        height: ビューアの高さ
    """

    text_processor = SimpleTextProcessorGateway()
    
    # 文脈マーカーを検出
    import re
    context_markers = []
    for match in re.finditer(r'\{([^}]+)\}', edited_text):
        context_markers.append({
            'start': match.start(),
            'end': match.end(),
            'content': match.group(1)
        })

    # 元のテキストを取得
    full_text = ""
    if "transcription_result" in st.session_state:
        # textプロパティを使用（get_full_text()は削除された）
        full_text = st.session_state.transcription_result.text

    # 編集テキストベースで赤ハイライトを生成
    html_content = (
        f'<div class="edited-text-viewer" style="height: {height}px; overflow-y: auto; '
        f"padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; "
        f'white-space: pre-wrap; font-family: monospace;">'
    )

    # セクションに分割
    sections = text_processor.split_text_by_separator(edited_text, separator)

    for i, section in enumerate(sections):
        # 文脈マーカーを検出
        section_context_markers = []
        for match in re.finditer(r'\{([^}]+)\}', section):
            section_context_markers.append({
                'start': match.start(),
                'end': match.end(),
                'content': match.group(1)
            })
        
        # 差分を計算（文脈マーカーは自動的に処理される）
        cleaned_section = section
        # 境界マーカーがある場合は正規化をスキップ
        has_markers = any(marker in section for marker in ["[<", "[>", "<]", ">]"])
        section_diff = text_processor.find_differences(full_text, cleaned_section, skip_normalization=has_markers)

        # マーカーの位置を記録（ハイライトから除外するため）
        marker_positions = set()
        import re

        marker_pattern = re.compile(r"\[(\d+(?:\.\d+)?)[<>]\]|\[[<>](\d+(?:\.\d+)?)\]")
        for match in marker_pattern.finditer(section):
            for pos in range(match.start(), match.end()):
                marker_positions.add(pos)

        # 削除後に残るテキストを計算
        remaining_text = ""
        from domain.entities.text_difference import DifferenceType
        if section_diff and hasattr(section_diff, "differences"):
            remaining_text = "".join(
                text for diff_item in section_diff.differences 
                if (diff_item[0] == DifferenceType.UNCHANGED if len(diff_item) >= 3 else False)
                for text in [diff_item[1]]
            )

        # セクションのHTMLを生成
        remaining_chars = list(remaining_text)
        remaining_index = 0
        in_context_marker = False
        
        for j, char in enumerate(section):
            # 文脈マーカーの開始/終了をチェック
            is_marker_boundary = False
            for marker in section_context_markers:
                if j == marker['start']:
                    in_context_marker = True
                    is_marker_boundary = True
                    break
                elif j == marker['end'] - 1:
                    if char == '}':
                        in_context_marker = False
                        is_marker_boundary = True
                        break
            
            # is_marker_boundaryのチェックを削除（文字を表示する必要があるため）
                
            if j in marker_positions:
                # 境界調整マーカー文字はそのまま表示（ハイライトなし）
                html_content += char
            elif in_context_marker:
                # 文脈マーカー内の文字もそのまま表示
                html_content += char
            else:
                # この文字が削除後のテキストに存在するかチェック
                if remaining_index < len(remaining_chars) and char == remaining_chars[remaining_index]:
                    # この文字は残る（ハイライトしない）
                    html_content += char
                    remaining_index += 1
                else:
                    # この文字は削除される（赤くハイライト）
                    html_content += (
                        f'<span class="highlight-deletion" style="background-color: #ffe6e6; '
                        f'color: #d00; text-decoration: line-through;">{char}</span>'
                    )

        # 区切り文字を追加（最後のセクション以外）
        if i < len(sections) - 1:
            html_content += f'\n<span style="color: #666; font-weight: bold;">{separator}</span>\n'

    html_content += "</div>"

    st.markdown(html_content, unsafe_allow_html=True)


@st.dialog("エラー箇所")
def show_red_highlight_modal(edited_text: str, diff: TextDifference | None = None) -> None:
    """
    赤ハイライトのモーダル表示

    Args:
        edited_text: 編集されたテキスト
        diff: 差分情報
    """
    st.markdown("赤色の部分を削除してください。")

    # 元のテキスト（区切り文字付き）を取得
    original_edited_text = st.session_state.get("original_edited_text", edited_text)

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

    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("削除", type="primary", use_container_width=True, key="delete_highlights_modal"):
        # 既に渡されたdiffオブジェクトを使用
        # これにより、ゲートウェイ経由で処理されたドメイン形式の差分が使われる

            # 区切り文字がある場合の処理
            original_edited_text = st.session_state.get("original_edited_text", edited_text)

            # 区切り文字パターンをチェック
            separator_patterns = ["---", "——", "－－－"]
            found_separator = None
            for pattern in separator_patterns:
                if pattern in original_edited_text:
                    found_separator = pattern
                    break

            if found_separator:
                # 区切り文字がある場合：各セクションの処理
                # シンプルなアプローチ：ADDED部分を除外して再結合
                if diff and hasattr(diff, "differences"):
                    from domain.entities.text_difference import DifferenceType
                    
                    # UNCHANGED部分と文脈マーカーを結合
                    result_parts = []
                    for diff_item in diff.differences:
                        if len(diff_item) >= 3 and diff_item[0] == DifferenceType.UNCHANGED:
                            # 文脈マーカーかどうかチェック
                            if len(diff_item) >= 4 and diff_item[3] and diff_item[3].get('is_context_marker'):
                                # 文脈マーカー内のテキストの場合、{} で囲んで復元
                                result_parts.append('{' + diff_item[1] + '}')
                            else:
                                result_parts.append(diff_item[1])
                    
                    # セクション間に区切り文字を挿入
                    sections = []
                    current_section = ""
                    for part in result_parts:
                        # 区切り文字が含まれていたら分割
                        if found_separator in original_edited_text:
                            # 元のテキストの区切り位置を参考にする
                            current_section += part
                    
                    # TODO: より正確な区切り文字の位置復元が必要
                    cleaned_text = "".join(result_parts)
                else:
                    cleaned_text = edited_text  # フォールバック
            else:
                # 区切り文字がない場合：元のテキストから追加された文字だけを削除
                if diff and hasattr(diff, "differences"):
                    # ドメインエンティティ形式
                    from domain.entities.text_difference import DifferenceType
                    
                    # 元のテキストから開始
                    cleaned_text = original_edited_text
                    
                    # ADDED部分を特定して削除
                    added_texts = []
                    for diff_item in diff.differences:
                        if len(diff_item) >= 3 and diff_item[0] == DifferenceType.ADDED:
                            added_texts.append(diff_item[1])
                    
                    # 追加されたテキストを削除（文脈マーカー内のテキストは除外）
                    import re
                    for added_text in added_texts:
                        # 文脈マーカー内のテキストかどうかチェック
                        pattern = re.escape(added_text)
                        # 文脈マーカー内でない場合のみ削除
                        if not re.search(r'\{[^}]*' + pattern + r'[^}]*\}', cleaned_text):
                            cleaned_text = cleaned_text.replace(added_text, '', 1)
                elif diff and hasattr(diff, "common_positions"):
                    # レガシー形式
                    cleaned_text = "".join(pos.text for pos in diff.common_positions)
                else:
                    # diffがない場合は元のテキストを返す
                    cleaned_text = edited_text

            st.session_state.edited_text = cleaned_text
            st.session_state.text_editor_value = cleaned_text  # テキストエディタの値も更新
            st.session_state.show_modal = False
            st.session_state.show_error_and_delete = False  # エラー状態もクリア
            st.rerun()
    
    with col2:
        if st.button("編集を続ける", use_container_width=True, key="continue_editing_modal"):
            # モーダルを閉じるだけで、テキストは変更しない
            st.session_state.show_modal = False
            st.session_state.show_error_and_delete = False  # エラー状態もクリア
            st.rerun()


def show_diff_viewer(original_text: str, diff: TextDifference | None = None, height: int = 400) -> None:
    """
    差分表示UI

    Args:
        original_text: 元のテキスト
        diff: 差分情報
        height: ビューアの高さ
    """
    if diff is None:
        # 差分がない場合は元のテキストを表示
        html_content = (
            f'<div class="diff-viewer" style="height: {height}px; overflow-y: auto; '
            f'padding: 10px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box;">{original_text}</div>'
        )
    else:
        # 差分をHTML形式で生成（従来通りシンプル版）
        html_content = (
            '<div class="diff-viewer" style="height: '
            + str(height)
            + 'px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box;">'
        )

        # ドメインエンティティ形式の場合
        if hasattr(diff, "differences"):
            # DifferenceTypeのインポート
            from domain.entities.text_difference import DifferenceType

            # 元のテキスト全体を表示しつつ、共通部分（UNCHANGED）をハイライト
            # diff.differencesには位置情報が含まれているはずなので、それを使用
            highlight_positions = []
            
            # 複数のUNCHANGEDブロックから位置情報を取得
            for diff_item in diff.differences:
                # タプルの長さをチェック
                if len(diff_item) >= 4:
                    diff_type, text, positions, extra_attrs = diff_item
                else:
                    diff_type, text, positions = diff_item
                    extra_attrs = None
                if diff_type == DifferenceType.UNCHANGED and positions:
                    # 文脈マーカーフラグが付いているものは除外
                    if extra_attrs and extra_attrs.get('is_context_marker'):
                        continue
                    # positionsは[(start, end), ...]の形式
                    for pos in positions:
                        if isinstance(pos, tuple) and len(pos) >= 2:
                            start_pos, end_pos = pos[0], pos[1]
                            # 元のテキストの該当部分を取得
                            actual_text = original_text[start_pos:end_pos] if start_pos < len(original_text) else text
                            highlight_positions.append((start_pos, end_pos, actual_text))

            # 元のテキストを表示しながらハイライト
            current_pos = 0
            for start, end, text in sorted(highlight_positions):
                # ハイライト前の部分
                if current_pos < start:
                    html_content += original_text[current_pos:start]
                # ハイライト部分（緑）
                html_content += f'<span class="highlight-match" style="background-color: #e6ffe6;">{text}</span>'
                current_pos = end

            # 残りの部分
            if current_pos < len(original_text):
                html_content += original_text[current_pos:]

        # レガシー形式の場合
        elif hasattr(diff, "common_positions"):
            current_pos = 0
            for pos in diff.common_positions:
                # 共通部分の前のテキスト（削除された部分）
                if current_pos < pos.start:
                    html_content += original_text[current_pos : pos.start]

                # 共通部分（緑でハイライト - クラス名を追加）
                html_content += f'<span class="highlight-match" style="background-color: #e6ffe6;">{pos.text}</span>'
                current_pos = pos.end

            # 最後の部分
            if current_pos < len(original_text):
                html_content += original_text[current_pos:]

        html_content += "</div>"

    # HTMLコンテンツを表示
    st.markdown(html_content, unsafe_allow_html=True)


def show_help() -> None:
    """ヘルプ表示UI"""
    st.markdown("#### ❓ ヘルプ")

    st.markdown(
        """
    詳しい使い方はこちら：

    📖 **[TextffCutの使い方 - note](https://note.com/coidemo/n/n8250e4b95daa)**
    """
    )


def show_optimization_status() -> None:
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

        except Exception:
            st.caption("メモリ情報を取得できませんでした")
