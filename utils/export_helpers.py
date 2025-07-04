"""
エクスポート関連のヘルパー関数

XML（FCPXML、Premiere Pro）、SRT字幕のエクスポート処理を
整理して提供する。
"""

from pathlib import Path
from typing import Any

import streamlit as st

from core import TranscriptionSegment
from core.srt_diff_exporter import SRTDiffExporter
from services import ExportService
from utils.file_utils import get_unique_path
from utils.logging import get_logger

logger = get_logger(__name__)


def get_default_srt_settings() -> dict[str, Any]:
    """
    デフォルトのSRT設定を取得

    Returns:
        Dict[str, Any]: SRTエクスポート設定
    """
    return {
        "min_duration": 0.5,
        "max_duration": 7.0,
        "gap_threshold": 0.1,
        "chars_per_second": 15.0,
        "max_line_length": 42,
        "max_lines": 2,
        "encoding": "utf-8",
    }


def get_srt_settings_from_session() -> dict[str, Any]:
    """
    セッション状態からSRT設定を取得

    存在しない場合はデフォルト設定を返す。

    Returns:
        Dict[str, Any]: SRT設定
    """
    return st.session_state.get("srt_settings", get_default_srt_settings())


def determine_export_format(primary_format: str) -> tuple[str, str]:
    """
    選択された形式からエクスポート形式と拡張子を決定

    Args:
        primary_format: ユーザーが選択した出力形式

    Returns:
        Tuple[str, str]: (エクスポート形式, ファイル拡張子)
    """
    format_mapping = {
        "FCPXMLファイル": ("fcpxml", ".fcpxml"),
        "Premiere Pro XML": ("xmeml", ".xml"),
    }

    return format_mapping.get(primary_format, ("fcpxml", ".fcpxml"))


def create_export_segments(keep_ranges: list[tuple[float, float]]) -> list[TranscriptionSegment]:
    """
    時間範囲リストからエクスポート用セグメントを作成

    Args:
        keep_ranges: (開始時間, 終了時間)のタプルのリスト

    Returns:
        List[TranscriptionSegment]: エクスポート用セグメントのリスト
    """
    export_segments = []
    for start, end in keep_ranges:
        export_segments.append(TranscriptionSegment(start=start, end=end, text="", words=[]))
    return export_segments


def export_xml(
    config: Any,
    video_path: Path,
    keep_ranges: list[tuple[float, float]],
    output_path: Path,
    export_format: str,
    timeline_fps: int = 30,
    remove_silence: bool = False,
) -> tuple[bool, str | None, float | None]:
    """
    XMLファイル（FCPXMLまたはPremiere Pro XML）をエクスポート

    Args:
        config: 設定オブジェクト
        video_path: 入力動画のパス
        keep_ranges: 出力する時間範囲のリスト
        output_path: 出力ファイルのパス
        export_format: エクスポート形式（"fcpxml"または"xmeml"）
        timeline_fps: タイムラインのFPS設定

    Returns:
        Tuple[bool, Optional[str], Optional[float]]:
            (成功フラグ, エラーメッセージ, 使用したタイムライン長)
    """
    try:
        export_service = ExportService(config)
        export_segments = create_export_segments(keep_ranges)

        export_result = export_service.execute(
            format=export_format,
            video_path=str(video_path),
            segments=export_segments,
            output_path=str(output_path),
            project_name=f"{video_path.stem} Project",
            event_name="TextffCut",
            timeline_fps=timeline_fps,
            remove_silence=remove_silence,
        )

        if export_result.success:
            timeline_duration = export_result.metadata.get("used_duration", 0)
            return True, None, timeline_duration
        else:
            return False, "XMLエクスポートに失敗しました", None

    except Exception as e:
        logger.error(f"XMLエクスポートエラー: {str(e)}")
        return False, str(e), None


def export_srt_with_diff(
    config: Any,
    video_path: Path,
    output_path: Path,
    diff_data: Any,
    transcription_result: Any,
    time_mapper: Any | None = None,
    remove_silence: bool = False,
) -> tuple[bool, str | None]:
    """
    差分検出ベースでSRT字幕をエクスポート

    Args:
        config: 設定オブジェクト
        video_path: 入力動画のパス
        output_path: 出力ファイルのパス
        diff_data: テキスト差分データ
        transcription_result: 文字起こし結果
        time_mapper: 時間マッピングオブジェクト（無音削除時に使用）
        remove_silence: 無音削除の有無

    Returns:
        Tuple[bool, Optional[str]]: (成功フラグ, エラーメッセージ)
    """
    try:
        srt_exporter = SRTDiffExporter(config)

        if remove_silence and time_mapper:
            success = srt_exporter.export_from_diff_with_silence_removal(
                diff=diff_data,
                transcription_result=transcription_result,
                output_path=str(output_path),
                time_mapper=time_mapper,
                srt_settings=get_srt_settings_from_session(),
            )
        else:
            success = srt_exporter.export_from_diff(
                diff=diff_data,
                transcription_result=transcription_result,
                output_path=str(output_path),
                max_chars_per_subtitle=get_srt_settings_from_session()["max_line_length"]
                * get_srt_settings_from_session()["max_lines"],
            )

        if success:
            return True, None
        else:
            return False, "SRTエクスポートに失敗しました"

    except Exception as e:
        logger.error(f"SRTエクスポートエラー: {str(e)}")
        return False, str(e)


def generate_export_paths(
    project_path: Path, base_name: str, type_suffix: str, export_srt: bool = False, xml_ext: str = ".fcpxml"
) -> dict[str, Path]:
    """
    エクスポート用のファイルパスを生成

    Args:
        project_path: プロジェクトディレクトリのパス
        base_name: ベースファイル名
        type_suffix: ファイルタイプのサフィックス
        export_srt: SRTも出力するかどうか
        xml_ext: XMLファイルの拡張子

    Returns:
        Dict[str, Path]: 各種出力ファイルのパス辞書
    """
    paths = {}

    # XMLファイルのパス
    paths["xml"] = get_unique_path(project_path / f"{base_name}_TextffCut_{type_suffix}{xml_ext}")

    # SRTファイルのパス（必要な場合）
    if export_srt:
        # XMLと同じ連番を使用
        xml_stem = paths["xml"].stem
        if xml_stem.endswith(")"):
            # 連番付きの場合、それを抽出
            import re

            match = re.search(r"\((\d+)\)$", xml_stem)
            if match:
                number = match.group(1)
                srt_stem = f"{base_name}_TextffCut_{type_suffix}({number})"
            else:
                srt_stem = f"{base_name}_TextffCut_{type_suffix}"
        else:
            srt_stem = xml_stem

        paths["srt"] = project_path / f"{srt_stem}.srt"

    return paths


def format_export_success_message(
    format_name: str,
    output_path: Path,
    timeline_duration: float | None = None,
    srt_path: Path | None = None,
    srt_success: bool = True,
) -> str:
    """
    エクスポート成功時のメッセージをフォーマット

    Args:
        format_name: エクスポート形式の表示名
        output_path: 出力ファイルのパス
        timeline_duration: タイムライン長（秒）
        srt_path: SRTファイルのパス（オプション）
        srt_success: SRT出力の成功フラグ

    Returns:
        str: フォーマットされたメッセージ
    """
    from utils.path_helpers import get_display_path
    from utils.time_utils import format_time

    message_parts = [f"✅ {format_name}を生成しました"]
    message_parts.append(f"{format_name}: {get_display_path(output_path)}")

    if timeline_duration:
        message_parts.append(f"タイムライン長: {format_time(timeline_duration)}")

    if srt_path:
        if srt_success:
            message_parts.append(f"SRT字幕: {get_display_path(srt_path)}")
        else:
            message_parts.append("⚠️ SRT字幕の生成に失敗")

    return " | ".join(message_parts)
