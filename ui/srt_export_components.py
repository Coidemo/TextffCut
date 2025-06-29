"""
SRT字幕エクスポート用UIコンポーネント

SRT字幕エクスポートの設定UIを提供。
"""

from typing import Any

import streamlit as st


def show_srt_export_settings() -> dict[str, Any]:
    """
    SRT字幕エクスポート設定UI

    Returns:
        設定値の辞書
    """
    from utils import settings_manager

    settings: dict[str, Any] = {}

    st.markdown("#### 🎬 SRT字幕設定")

    # 基本設定
    col1, col2 = st.columns(2)

    with col1:
        # 保存された設定を取得（デフォルト値も定義）
        saved_adjust_timing = settings_manager.get("srt_adjust_timing", True)
        saved_max_line_length = settings_manager.get("srt_max_line_length", 42)
        saved_max_lines = settings_manager.get("srt_max_lines", 2)

        settings["adjust_timing"] = st.checkbox(
            "タイミング自動調整", value=saved_adjust_timing, help="字幕の表示時間を読みやすさに合わせて自動調整します"
        )

        settings["max_line_length"] = st.number_input(
            "1行の最大文字数",
            min_value=10,
            max_value=60,
            value=saved_max_line_length,
            step=1,
            help="字幕1行あたりの最大文字数",
        )

        settings["max_lines"] = st.number_input(
            "最大行数", min_value=1, max_value=4, value=saved_max_lines, step=1, help="1つの字幕の最大行数"
        )

        # 設定が変更されたら保存
        if settings["adjust_timing"] != saved_adjust_timing:
            settings_manager.set("srt_adjust_timing", settings["adjust_timing"])
        if settings["max_line_length"] != saved_max_line_length:
            settings_manager.set("srt_max_line_length", settings["max_line_length"])
        if settings["max_lines"] != saved_max_lines:
            settings_manager.set("srt_max_lines", settings["max_lines"])

    with col2:
        # 保存された設定を取得
        saved_min_duration = settings_manager.get("srt_min_duration", 0.5)
        saved_max_duration = settings_manager.get("srt_max_duration", 7.0)
        saved_gap_threshold = settings_manager.get("srt_gap_threshold", 0.1)

        settings["min_duration"] = st.number_input(
            "最小表示時間（秒）",
            min_value=0.3,
            max_value=2.0,
            value=saved_min_duration,
            step=0.1,
            format="%.1f",
            help="字幕の最小表示時間",
        )

        settings["max_duration"] = st.number_input(
            "最大表示時間（秒）",
            min_value=3.0,
            max_value=10.0,
            value=saved_max_duration,
            step=0.5,
            format="%.1f",
            help="字幕の最大表示時間",
        )

        settings["gap_threshold"] = st.number_input(
            "字幕間の最小間隔（秒）",
            min_value=0.05,
            max_value=0.5,
            value=saved_gap_threshold,
            step=0.05,
            format="%.2f",
            help="字幕と字幕の間の最小間隔",
        )

        # 設定が変更されたら保存
        if settings["min_duration"] != saved_min_duration:
            settings_manager.set("srt_min_duration", settings["min_duration"])
        if settings["max_duration"] != saved_max_duration:
            settings_manager.set("srt_max_duration", settings["max_duration"])
        if settings["gap_threshold"] != saved_gap_threshold:
            settings_manager.set("srt_gap_threshold", settings["gap_threshold"])

    # 高度な設定（折りたたみ）
    with st.expander("高度な設定", expanded=False):
        # 保存された設定を取得
        saved_chars_per_second = settings_manager.get("srt_chars_per_second", 15.0)
        saved_prefer_sentence_breaks = settings_manager.get("srt_prefer_sentence_breaks", True)
        saved_encoding = settings_manager.get("srt_encoding", "utf-8")

        settings["chars_per_second"] = st.number_input(
            "読取速度（文字/秒）",
            min_value=10.0,
            max_value=25.0,
            value=saved_chars_per_second,
            step=0.5,
            format="%.1f",
            help="1秒あたりの読める文字数（読みやすさの基準）",
        )

        settings["prefer_sentence_breaks"] = st.checkbox(
            "文の区切りで分割", value=saved_prefer_sentence_breaks, help="長い字幕を分割する際、文の区切りを優先します"
        )

        encoding_options = ["utf-8", "utf-8-sig", "shift-jis"]
        encoding_index = encoding_options.index(saved_encoding) if saved_encoding in encoding_options else 0
        settings["encoding"] = st.selectbox(
            "文字エンコーディング",
            options=encoding_options,
            index=encoding_index,
            help="SRTファイルの文字エンコーディング",
        )

        # 設定が変更されたら保存
        if settings["chars_per_second"] != saved_chars_per_second:
            settings_manager.set("srt_chars_per_second", settings["chars_per_second"])
        if settings["prefer_sentence_breaks"] != saved_prefer_sentence_breaks:
            settings_manager.set("srt_prefer_sentence_breaks", settings["prefer_sentence_breaks"])
        if settings["encoding"] != saved_encoding:
            settings_manager.set("srt_encoding", settings["encoding"])

    return settings


def show_srt_timing_adjuster_settings() -> dict[str, Any] | None:
    """
    SRTタイミング調整の詳細設定UI

    Returns:
        設定値の辞書（使用しない場合はNone）
    """
    use_advanced = st.checkbox(
        "高度なタイミング調整を使用", value=False, help="ショット変更検出など、高度なタイミング調整機能を使用します"
    )

    if not use_advanced:
        return None

    settings: dict[str, Any] = {}

    # タイミング調整設定
    st.markdown("##### ⏱️ タイミング調整")

    col1, col2 = st.columns(2)

    with col1:
        settings["snap_to_shot_change"] = st.checkbox(
            "ショット変更にスナップ", value=True, help="字幕の開始・終了をショット変更に合わせます"
        )

        if settings["snap_to_shot_change"]:
            settings["shot_change_threshold"] = st.number_input(
                "スナップ許容範囲（秒）",
                min_value=0.05,
                max_value=0.5,
                value=0.1,
                step=0.05,
                format="%.2f",
                help="ショット変更から何秒以内ならスナップするか",
            )

    with col2:
        settings["words_per_minute"] = st.number_input(
            "1分あたりの単語数", min_value=120, max_value=240, value=180, step=10, help="英語の場合の読取速度基準"
        )

    return settings


def show_srt_export_preview(segments: list[Any], settings: dict[str, Any]) -> None:
    """
    SRTエクスポートのプレビュー表示

    Args:
        segments: 文字起こしセグメント
        settings: エクスポート設定
    """
    if not segments:
        st.warning("プレビューするセグメントがありません")
        return

    st.markdown("#### 👁️ SRT字幕プレビュー")

    # 最初の5つのセグメントをプレビュー
    preview_count = min(5, len(segments))

    preview_text = ""
    for i, segment in enumerate(segments[:preview_count]):
        # 簡易的なSRT形式でプレビュー
        from utils.time_utils import seconds_to_srt_time

        start_str = seconds_to_srt_time(segment.start)
        end_str = seconds_to_srt_time(segment.end)

        # テキストを設定に基づいて調整
        text = segment.text.strip()
        if len(text) > settings["max_line_length"]:
            # 簡易的な行分割
            words = text.split()
            lines = []
            current_line = ""

            for word in words:
                if not current_line:
                    current_line = word
                elif len(current_line + " " + word) <= settings["max_line_length"]:
                    current_line += " " + word
                else:
                    lines.append(current_line)
                    current_line = word
                    if len(lines) >= settings["max_lines"]:
                        break

            if current_line and len(lines) < settings["max_lines"]:
                lines.append(current_line)

            text = "\n".join(lines)

        preview_text += f"{i + 1}\n{start_str} --> {end_str}\n{text}\n\n"

    # プレビュー表示
    st.text_area(
        "プレビュー",
        value=preview_text,
        height=300,
        disabled=True,
        help=f"最初の{preview_count}個の字幕をプレビュー表示しています",
    )

    if len(segments) > preview_count:
        st.caption(f"他に{len(segments) - preview_count}個の字幕があります")


def show_srt_export_info() -> None:
    """
    SRT字幕エクスポートの説明表示
    """
    with st.expander("SRT字幕について", expanded=False):
        st.markdown(
            """
        **SRT (SubRip Text)** は最も広く使われている字幕フォーマットです。

        **特徴:**
        - ✅ ほぼすべての動画プレーヤーで再生可能
        - ✅ 編集ソフトでの読み込みサポート
        - ✅ YouTubeやVimeoなどへのアップロード対応
        - ✅ テキストエディタで編集可能

        **使用例:**
        - 動画に字幕を追加
        - 多言語字幕の作成
        - アクセシビリティ向上
        - 動画の検索性向上

        **エクスポート後の使い方:**
        1. 動画プレーヤーで字幕ファイルを選択
        2. 動画編集ソフトにインポート
        3. 動画配信サービスにアップロード
        """
        )
