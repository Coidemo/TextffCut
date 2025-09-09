"""
エクスポート関連のゲートウェイインターフェース

各種エクスポート形式（FCPXML、EDL、SRT、動画）のゲートウェイインターフェースを定義します。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from domain.value_objects.file_path import FilePath


class IVideoExportGateway(ABC):
    """
    動画エクスポートゲートウェイのインターフェース

    動画クリップの切り出しと出力を行います。
    """

    @abstractmethod
    def export_clips(
        self,
        video_path: FilePath,
        time_ranges: list[tuple[float, float]],
        output_base: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> list[str]:
        """
        動画クリップをエクスポート

        Args:
            video_path: 入力動画パス
            time_ranges: 切り出す時間範囲のリスト [(start, end), ...]
            output_base: 出力ファイルのベース名
            progress_callback: 進捗コールバック

        Returns:
            出力されたファイルパスのリスト
        """
        pass


class IFCPXMLExportGateway(ABC):
    """
    FCPXMLエクスポートゲートウェイのインターフェース

    Final Cut Pro XMLファイルの生成を行います。
    """

    @abstractmethod
    def export(
        self,
        video_path: FilePath,
        time_ranges: list[tuple[float, float]],
        output_path: str,
        with_gap_removal: bool = False,
        scale: tuple[float, float] = (1.0, 1.0),
        anchor: tuple[float, float] = (0.0, 0.0),
        timeline_resolution: str = "horizontal",
        overlay_settings: dict | None = None,
        bgm_settings: dict | None = None,
        additional_audio_settings: dict | None = None,
    ) -> None:
        """
        FCPXMLファイルをエクスポート

        Args:
            video_path: 入力動画パス
            time_ranges: クリップの時間範囲リスト
            output_path: 出力XMLファイルパス
            with_gap_removal: 隙間を詰めて配置するかどうか
            scale: ズーム倍率（x, y）
            anchor: アンカー位置（x, y）
        """
        pass


class IEDLExportGateway(ABC):
    """
    EDLエクスポートゲートウェイのインターフェース

    EDL (Edit Decision List)ファイルの生成を行います。
    """

    @abstractmethod
    def export(self, video_path: FilePath, time_ranges: list[tuple[float, float]], output_path: str) -> None:
        """
        EDLファイルをエクスポート

        Args:
            video_path: 入力動画パス
            time_ranges: クリップの時間範囲リスト
            output_path: 出力EDLファイルパス
        """
        pass


class ISRTExportGateway(ABC):
    """
    SRT字幕エクスポートゲートウェイのインターフェース

    SRT字幕ファイルの生成を行います。
    """

    @abstractmethod
    def export(
        self,
        transcription_result: Any,
        output_path: str,
        time_ranges: list[tuple[float, float]] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        """
        SRT字幕ファイルをエクスポート

        Args:
            transcription_result: 文字起こし結果
            output_path: 出力SRTファイルパス
            time_ranges: 出力対象の時間範囲（省略時は全体）
            settings: SRT設定（max_line_length、max_linesなど）
        """
        pass
