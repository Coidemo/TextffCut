"""
エクスポート設定のPresenter

エクスポート機能のビジネスロジックを担当します。
"""

import logging
from collections.abc import Callable
from pathlib import Path

from domain.interfaces.error_handler import IErrorHandler
from domain.value_objects.file_path import FilePath
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.base import BasePresenter
from presentation.view_models.export_settings import ExportSettingsViewModel
from use_cases.interfaces.export_gateways import (
    IEDLExportGateway,
    IFCPXMLExportGateway,
    ISRTExportGateway,
    IVideoExportGateway,
)
from use_cases.interfaces.video_processor_gateway import IVideoProcessorGateway

logger = logging.getLogger(__name__)


class ExportSettingsPresenter(BasePresenter[ExportSettingsViewModel]):
    """
    エクスポート設定のPresenter

    ViewModelの状態管理とエクスポート処理の実行を担当します。
    """

    def __init__(
        self,
        view_model: ExportSettingsViewModel,
        video_processor_gateway: IVideoProcessorGateway,
        video_export_gateway: IVideoExportGateway,
        fcpxml_export_gateway: IFCPXMLExportGateway,
        edl_export_gateway: IEDLExportGateway,
        srt_export_gateway: ISRTExportGateway,
        session_manager: SessionManager,
        error_handler: IErrorHandler,
    ):
        """
        初期化

        Args:
            view_model: エクスポート設定ViewModel
            video_processor_gateway: 動画処理ゲートウェイ
            video_export_gateway: 動画エクスポートゲートウェイ
            fcpxml_export_gateway: FCPXMLエクスポートゲートウェイ
            edl_export_gateway: EDLエクスポートゲートウェイ（将来の削除予定）
            srt_export_gateway: SRTエクスポートゲートウェイ
            session_manager: セッション管理
            error_handler: エラーハンドラー
        """
        super().__init__(view_model)
        self.video_processor_gateway = video_processor_gateway
        self.video_export_gateway = video_export_gateway
        self.fcpxml_export_gateway = fcpxml_export_gateway
        # EDLは使用しないが、インターフェースの互換性のため保持
        # self.edl_export_gateway = edl_export_gateway
        self.srt_export_gateway = srt_export_gateway
        self.session_manager = session_manager
        self.error_handler = error_handler

    def initialize(self) -> None:
        """初期化処理"""
        # SessionManagerから必要なデータを取得
        self.view_model.video_path = (
            Path(self.session_manager.get_video_path()) if self.session_manager.get_video_path() else None
        )
        self.view_model.transcription_result = self.session_manager.get_transcription_result()
        self.view_model.edited_text = self.session_manager.get_edited_text()
        
        # time_rangesを取得（タプル形式の可能性があるので変換）
        time_ranges = self.session_manager.get_time_ranges()
        if time_ranges:
            # タプル形式の場合はTimeRangeオブジェクトに変換
            if time_ranges and isinstance(time_ranges[0], tuple):
                from domain.value_objects.time_range import TimeRange
                self.view_model.time_ranges = [TimeRange(start=r[0], end=r[1]) for r in time_ranges]
            else:
                self.view_model.time_ranges = time_ranges
        else:
            self.view_model.time_ranges = []

        # 調整済み時間範囲を取得（もしあれば）
        adjusted_ranges = self.session_manager.get("adjusted_time_ranges")
        if adjusted_ranges:
            # タプル形式の場合はTimeRangeオブジェクトに変換
            if adjusted_ranges and isinstance(adjusted_ranges[0], tuple):
                from domain.value_objects.time_range import TimeRange
                self.view_model.adjusted_time_ranges = [TimeRange(start=r[0], end=r[1]) for r in adjusted_ranges]
            else:
                self.view_model.adjusted_time_ranges = adjusted_ranges

    def set_remove_silence(self, enabled: bool) -> None:
        """無音削除の有効/無効を設定"""
        self.view_model.remove_silence = enabled
        self.view_model.notify()

    def set_silence_threshold(self, threshold: float) -> None:
        """無音検出閾値を設定"""
        self.view_model.silence_threshold = threshold
        self.view_model.notify()

    def set_min_silence_duration(self, duration: float) -> None:
        """最小無音時間を設定"""
        self.view_model.min_silence_duration = duration
        self.view_model.notify()

    def set_silence_padding(self, start: float, end: float) -> None:
        """無音パディングを設定"""
        self.view_model.silence_pad_start = start
        self.view_model.silence_pad_end = end
        self.view_model.notify()

    def set_export_format(self, format: str) -> None:
        """エクスポート形式を設定"""
        self.view_model.export_format = format
        self.view_model.notify()

    def set_include_srt(self, enabled: bool) -> None:
        """SRT字幕の同時出力を設定"""
        self.view_model.include_srt = enabled
        self.view_model.notify()

    def set_srt_settings(self, max_line_length: int, max_lines: int) -> None:
        """SRT字幕設定"""
        self.view_model.srt_max_line_length = max_line_length
        self.view_model.srt_max_lines = max_lines
        self.view_model.notify()

    def start_export(self, progress_callback: Callable[[float, str], None] | None = None) -> bool:
        """
        エクスポートを開始

        Args:
            progress_callback: 進捗コールバック

        Returns:
            成功したかどうか
        """
        if not self.view_model.is_ready_to_export:
            self.view_model.set_error("エクスポートに必要な情報が不足しています")
            return False

        try:
            self.view_model.start_processing()

            # 進捗コールバックのラッパー
            def wrapped_progress(progress: float, message: str, operation: str = "") -> None:
                self.view_model.update_progress(progress, message, operation)
                if progress_callback:
                    progress_callback(progress, message)

            # エクスポート形式に応じて処理を実行
            results = []

            if self.view_model.export_format == "video":
                results = self._export_video(wrapped_progress)
            elif self.view_model.export_format == "fcpxml":
                results = self._export_fcpxml(wrapped_progress)
            elif self.view_model.export_format == "xmeml":
                results = self._export_xmeml(wrapped_progress)
            elif self.view_model.export_format == "srt":
                results = self._export_srt(wrapped_progress)

            if results:
                self.view_model.complete_processing(results)
                return True
            else:
                self.view_model.set_error("エクスポートに失敗しました")
                return False

        except Exception as e:
            self.handle_error(e, "エクスポート処理")
            return False

    def _export_video(self, progress_callback: Callable[[float, str, str], None]) -> list[str]:
        """動画エクスポート"""
        try:
            # 出力パスを生成（拡張子なし）
            output_base = self._generate_output_base()

            # 時間範囲を取得
            time_ranges = self.view_model.effective_time_ranges

            if self.view_model.remove_silence:
                # 無音削除処理
                progress_callback(0.1, "無音を検出中...", "silence_detection")

                # 無音削除のパラメータ設定
                silence_params = {
                    "threshold": self.view_model.silence_threshold,
                    "min_duration": self.view_model.min_silence_duration,
                    "pad_start": self.view_model.silence_pad_start,
                    "pad_end": self.view_model.silence_pad_end,
                }

                # レガシー形式に変換（一時的）
                legacy_ranges = [(r.start, r.end) for r in time_ranges]

                # 無音削除処理を実行
                keep_ranges = self.video_processor_gateway.remove_silence(
                    FilePath(str(self.view_model.video_path)),
                    legacy_ranges,
                    silence_params,
                    lambda p, m: progress_callback(0.1 + p * 0.8, m, "video_processing"),
                )

                # 動画を出力
                output_paths = self.video_export_gateway.export_clips(
                    FilePath(str(self.view_model.video_path)),
                    keep_ranges,
                    str(output_base),
                    lambda p, m: progress_callback(0.9 + p * 0.1, m, "video_export"),
                )
            else:
                # 通常の切り出し
                legacy_ranges = [(r.start, r.end) for r in time_ranges]
                output_paths = self.video_export_gateway.export_clips(
                    FilePath(str(self.view_model.video_path)),
                    legacy_ranges,
                    str(output_base),
                    lambda p, m: progress_callback(p, m, "video_export"),
                )

            # SRT字幕も出力する場合
            if self.view_model.include_srt:
                self._export_srt_for_video(output_paths, progress_callback)

            return output_paths

        except Exception as e:
            logger.error(f"動画エクスポートエラー: {e}")
            raise

    def _export_fcpxml(self, progress_callback: Callable[[float, str, str], None]) -> list[str]:
        """FCPXMLエクスポート"""
        try:
            output_path = self._generate_output_path("fcpxml")

            # 時間範囲を取得
            time_ranges = self.view_model.effective_time_ranges
            legacy_ranges = [(r.start, r.end) for r in time_ranges]

            # FCPXMLを生成
            self.fcpxml_export_gateway.export(
                FilePath(str(self.view_model.video_path)),
                legacy_ranges,
                str(output_path),
                self.view_model.remove_silence,
            )

            progress_callback(1.0, "FCPXML出力完了", "complete")
            return [str(output_path)]

        except Exception as e:
            logger.error(f"FCPXMLエクスポートエラー: {e}")
            raise
    
    def _export_xmeml(self, progress_callback: Callable[[float, str, str], None]) -> list[str]:
        """XMEMLエクスポート（Premiere Pro用）"""
        try:
            output_path = self._generate_output_path("xml")

            # 時間範囲を取得
            time_ranges = self.view_model.effective_time_ranges
            legacy_ranges = [(r.start, r.end) for r in time_ranges]

            # XMEMLExporterを使用
            from core.export import XMEMLExporter, ExportSegment
            from config import Config
            
            exporter = XMEMLExporter(Config())
            
            # ExportSegmentのリストを作成
            segments = []
            timeline_start = 0.0
            
            for r in time_ranges:
                segment = ExportSegment(
                    source_path=str(self.view_model.video_path),
                    start_time=r.start,
                    end_time=r.end,
                    timeline_start=timeline_start
                )
                segments.append(segment)
                timeline_start += (r.end - r.start)
            
            # XMEMLを生成
            success = exporter.export(segments, str(output_path))
            
            if not success:
                raise RuntimeError("XMEMLの生成に失敗しました")

            progress_callback(1.0, "Premiere Pro XML出力完了", "complete")
            return [str(output_path)]

        except Exception as e:
            logger.error(f"XMEMLエクスポートエラー: {e}")
            raise


    def _export_srt(self, progress_callback: Callable[[float, str, str], None]) -> list[str]:
        """SRT字幕エクスポート"""
        try:
            output_path = self._generate_output_path("srt")

            # SRT設定
            srt_params = {
                "max_line_length": self.view_model.srt_max_line_length,
                "max_lines": self.view_model.srt_max_lines,
            }

            # 時間範囲を取得
            time_ranges = self.view_model.effective_time_ranges
            legacy_ranges = [(r.start, r.end) for r in time_ranges] if time_ranges else None

            # SRTを生成
            self.srt_export_gateway.export(
                self.view_model.transcription_result, str(output_path), legacy_ranges, srt_params
            )

            progress_callback(1.0, "SRT字幕出力完了", "complete")
            return [str(output_path)]

        except Exception as e:
            logger.error(f"SRT字幕エクスポートエラー: {e}")
            raise

    def _export_srt_for_video(
        self, video_paths: list[str], progress_callback: Callable[[float, str, str], None]
    ) -> None:
        """動画に対応するSRT字幕を出力"""
        # TODO: 各動画クリップに対応するSRT字幕を生成
        pass

    def _generate_output_path(self, extension: str) -> Path:
        """出力パスを生成"""
        video_name = self.view_model.video_path.stem
        video_dir = self.view_model.video_path.parent

        # TextffCutフォルダ内に出力
        output_dir = video_dir / f"{video_name}_TextffCut"
        output_dir.mkdir(exist_ok=True)

        # ファイル名を生成
        suffix = "_NoSilence" if self.view_model.remove_silence else "_Clip"
        base_name = f"{video_name}_TextffCut{suffix}"

        return output_dir / f"{base_name}.{extension}"
    
    def _generate_output_base(self) -> Path:
        """出力ベースパスを生成（拡張子なし）"""
        video_name = self.view_model.video_path.stem
        video_dir = self.view_model.video_path.parent

        # TextffCutフォルダ内に出力
        output_dir = video_dir / f"{video_name}_TextffCut"
        output_dir.mkdir(exist_ok=True)

        # セッション連番を取得または生成
        session_number = self._get_or_create_session_number()
        
        # ファイル名を生成
        suffix = "_NoSilence" if self.view_model.remove_silence else "_Clip"
        base_name = f"{video_name}_TextffCut_{session_number:04d}{suffix}"

        return output_dir / base_name
    
    def _get_or_create_session_number(self) -> int:
        """セッション連番を取得または生成"""
        import streamlit as st
        
        # 編集されたテキストのハッシュを計算（同じテキストなら同じ連番）
        text_hash = hash(self.view_model.edited_text) if self.view_model.edited_text else 0
        
        # セッション状態に保存されている連番マップを取得
        if "export_session_numbers" not in st.session_state:
            st.session_state.export_session_numbers = {}
        
        # このテキストハッシュに対応する連番があるか確認
        if text_hash in st.session_state.export_session_numbers:
            return st.session_state.export_session_numbers[text_hash]
        
        # 新しい連番を生成（既存の最大値+1）
        existing_numbers = list(st.session_state.export_session_numbers.values())
        next_number = max(existing_numbers) + 1 if existing_numbers else 1
        
        # 連番を保存
        st.session_state.export_session_numbers[text_hash] = next_number
        
        return next_number

    def handle_error(self, error: Exception, context: str) -> None:
        """
        エラーをハンドリング

        Args:
            error: エラー
            context: コンテキスト
        """
        try:
            error_info = self.error_handler.handle_error(error, context=context, raise_after=False)
            if error_info:
                self.view_model.set_error(error_info["user_message"], error_info.get("details"))
            else:
                self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")
        except Exception as e:
            logger.error(f"Error handler failed: {e}")
            self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")
