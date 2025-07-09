"""
StreamlitベースのUIコンポーネント
"""

from typing import Any

import streamlit as st

from adapters.gateways.text_processing.simple_text_processor_gateway import SimpleTextProcessorGateway
from core.text_processor import TextDifference


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

            selected_option = st.selectbox(
                "保存済みの文字起こし結果", cache_options, help="使用する文字起こし結果を選択してください"
            )

            if selected_option:
                selected_cache = cache_map[selected_option]

            # キャッシュ使用ボタンを枠内に表示
            if selected_cache and st.button("💾 選択した結果を使用", type="primary", use_container_width=True):
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
            "**🎯 境界調整マーカー**\n"
            "[数値<] = 前のクリップを縮める\n"
            "[数値>] = 前のクリップを延ばす\n"
            "[<数値] = 後のクリップを早める\n"
            "[>数値] = 後のクリップを遅らせる"
        ),
    )

    # エディタの値をセッション状態に保存
    if edited_text != st.session_state.get("text_editor_value", ""):
        st.session_state.text_editor_value = edited_text

    return edited_text


def show_edited_text_with_highlights(edited_text: str, diff: TextDifference | None = None, height: int = 400) -> None:
    """
    編集テキストに赤ハイライト表示（シンプル版）

    追加文字（ADDED）だけを赤くハイライトする簡易実装
    """
    if not edited_text or diff is None:
        return

    html_content = (
        f'<div class="edited-text-viewer" style="height: {height}px; overflow-y: auto; '
        f'padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">'
    )

    # 追加文字を取得
    added_chars = set()
    if hasattr(diff, "differences"):
        # ドメインエンティティの場合
        from domain.entities.text_difference import DifferenceType

        for diff_type, text, _ in diff.differences:
            if diff_type == DifferenceType.ADDED:
                # 各文字を追加文字セットに追加
                for char in text:
                    added_chars.add(char)
    elif hasattr(diff, "added_chars"):
        # レガシー形式の場合
        added_chars = diff.added_chars if diff.added_chars else set()

    # デバッグ情報をログ出力
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"[show_edited_text_with_highlights] diffの型: {type(diff)}")
    logger.info(f"[show_edited_text_with_highlights] hasattr(differences): {hasattr(diff, 'differences')}")
    logger.info(f"[show_edited_text_with_highlights] hasattr(added_chars): {hasattr(diff, 'added_chars')}")
    logger.info(f"[show_edited_text_with_highlights] 追加文字数: {len(added_chars)}")
    logger.info(f"[show_edited_text_with_highlights] 追加文字: {added_chars}")

    # HTMLを生成
    highlighted_count = 0
    for char in edited_text:
        if char in added_chars:
            html_content += (
                f'<span class="highlight-addition" style="background-color: #ffe6e6; ' f'color: #d00;">{char}</span>'
            )
            highlighted_count += 1
        else:
            html_content += char

    html_content += "</div>"

    logger.info(f"[show_edited_text_with_highlights] ハイライトされた文字数: {highlighted_count}/{len(edited_text)}")

    st.markdown(html_content, unsafe_allow_html=True)


def show_edited_text_with_separators_highlights(edited_text: str, separator: str, height: int = 400) -> None:
    """
    区切り文字を含むテキストの赤ハイライト表示

    Args:
        edited_text: 編集されたテキスト（区切り文字付き）
        separator: 区切り文字
        height: ビューアの高さ
    """

    text_processor = SimpleTextProcessorGateway()

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
        # マーカーを除去してから差分を計算
        cleaned_section = text_processor.remove_boundary_markers(section)
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

        covered_positions = set()

        # 共通部分でカバーされている位置をマーク（cleaned_sectionベース）
        from domain.entities.text_difference import DifferenceType

        for diff_type, text, _ in section_diff.differences:
            if diff_type == DifferenceType.UNCHANGED:
                common_text = text
                search_start = 0

                while True:
                    found_pos = cleaned_section.find(common_text, search_start)
                    if found_pos == -1:
                        break

                    if not any(pos in covered_positions for pos in range(found_pos, found_pos + len(common_text))):
                        for j in range(found_pos, found_pos + len(common_text)):
                            covered_positions.add(j)
                        break

                    search_start = found_pos + 1

        # セクションのHTMLを生成
        # マーカーを除外した位置での対応付けが必要
        cleaned_pos = 0  # cleaned_section内での位置
        for j, char in enumerate(section):
            if j in marker_positions:
                # マーカー文字はそのまま表示（ハイライトなし）
                html_content += char
            else:
                # 非マーカー文字の処理
                if cleaned_pos in covered_positions:
                    html_content += char  # 元テキストに存在
                else:
                    html_content += (
                        f'<span class="highlight-addition" style="background-color: #ffe6e6; '
                        f'color: #d00;">{char}</span>'
                    )  # 追加文字
                cleaned_pos += 1

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

    # デバッグ情報を表示
    with st.expander("🔍 デバッグ情報", expanded=False):
        st.write(f"差分オブジェクトの型: {type(diff)}")
        st.write(f"hasattr(diff, 'differences'): {hasattr(diff, 'differences') if diff else 'None'}")
        if diff and hasattr(diff, "differences"):
            st.write(f"differences数: {len(diff.differences) if diff.differences else 0}")
            if diff.differences:
                from domain.entities.text_difference import DifferenceType

                unchanged_count = sum(1 for d in diff.differences if d[0] == DifferenceType.UNCHANGED)
                added_count = sum(1 for d in diff.differences if d[0] == DifferenceType.ADDED)
                st.write(f"UNCHANGED: {unchanged_count}個, ADDED: {added_count}個")

                # UNCHANGEDの合計長さを計算
                unchanged_total = sum(len(d[1]) for d in diff.differences if d[0] == DifferenceType.UNCHANGED)
                st.write(f"UNCHANGEDの合計長さ: {unchanged_total}")

                # 全ての差分を表示
                for i, (diff_type, text, _) in enumerate(diff.differences):
                    st.write(f"差分{i+1}: {diff_type.value}, 長さ={len(text)}, 内容='{repr(text[:30])}...'")
        st.write(f"edited_text長さ: {len(edited_text)}")
        st.write(f"edited_text内容: {repr(edited_text[:50])}...")

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
            # TODO: 区切り文字ありの場合の処理を実装
            cleaned_text = edited_text  # 一旦元のテキストを返す
        else:
            # 区切り文字がない場合：単純に共通部分を結合
            if diff and hasattr(diff, "differences"):
                # ドメインエンティティ形式
                from domain.entities.text_difference import DifferenceType

                cleaned_text = "".join(
                    text for diff_type, text, _ in diff.differences if diff_type == DifferenceType.UNCHANGED
                )
            elif diff and hasattr(diff, "common_positions"):
                # レガシー形式
                cleaned_text = "".join(pos.text for pos in diff.common_positions)
            else:
                # diffがない場合は元のテキストを返す
                cleaned_text = edited_text

        st.session_state.edited_text = cleaned_text
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
            # 共通部分の位置を特定
            highlight_positions = []
            for diff_type, text, _ in diff.differences:
                if diff_type == DifferenceType.UNCHANGED:
                    # 元のテキストから該当箇所を探す
                    start_pos = diff.original_text.find(text)
                    if start_pos != -1:
                        highlight_positions.append((start_pos, start_pos + len(text), text))

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
