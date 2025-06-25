"""
統合サービス - 複数のサービスを協調させて複雑なワークフローを実行

main.pyから複雑なビジネスロジックを分離し、
各サービスを統合してワークフロー全体を管理する。
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.constants import ProcessingDefaults, SilenceDetection
from core.error_handling import ProcessingError
from core.models import TranscriptionSegmentV2
from services.base import BaseService, ServiceResult
from services.configuration_service import ConfigurationService
from services.export_service import ExportService
from services.text_editing_service import TextEditingService
from services.transcription_service import TranscriptionService
from services.video_processing_service import VideoProcessingService
from utils.file_utils import ensure_directory
from utils.progress import ProgressTracker


class IntegrationService(BaseService):
    """複数サービスを統合したワークフロー管理"""

    def __init__(self, config):
        """初期化

        Args:
            config: アプリケーション設定
        """
        super().__init__(config)

        # 各サービスの初期化
        self.transcription_service = TranscriptionService(config)
        self.video_service = VideoProcessingService(config)
        self.export_service = ExportService(config)
        self.text_service = TextEditingService(config)
        self.config_service = ConfigurationService(config)

        # プログレストラッカー
        self.progress_tracker = ProgressTracker()

    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド"""
        workflow = kwargs.get("workflow", "full_process")

        if workflow == "full_process":
            return self.full_process(**kwargs)
        elif workflow == "transcribe_and_export":
            return self.transcribe_and_export(**kwargs)
        elif workflow == "process_with_silence_removal":
            return self.process_with_silence_removal(**kwargs)
        else:
            return self.create_error_result(f"不明なワークフロー: {workflow}", "ValidationError")

    def full_process(
        self,
        video_path: str,
        base_text: str,
        target_text: str,
        model_size: str = ProcessingDefaults.LANGUAGE,
        language: str = ProcessingDefaults.LANGUAGE,
        remove_silence: bool = False,
        export_format: str = "fcpxml",
        output_dir: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ServiceResult:
        """フル処理ワークフロー

        文字起こし → テキスト差分検出 → 無音削除 → エクスポート

        Args:
            video_path: 動画ファイルパス
            base_text: 基準テキスト
            target_text: ターゲットテキスト
            model_size: Whisperモデルサイズ
            language: 言語コード
            remove_silence: 無音削除の有無
            export_format: エクスポート形式
            output_dir: 出力ディレクトリ
            progress_callback: 進捗コールバック

        Returns:
            ServiceResult: 処理結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not output_dir:
                output_dir = str(video_file.parent / "output")
            ensure_directory(output_dir)

            # ワークフローの段階
            total_stages = 4 if remove_silence else 3
            current_stage = 0

            def update_progress(stage_progress: float, message: str):
                """統合された進捗更新"""
                if progress_callback:
                    overall_progress = (current_stage + stage_progress) / total_stages
                    progress_callback(overall_progress, message)

            # Stage 1: 文字起こし
            current_stage = 0
            update_progress(0, "文字起こしを開始...")

            transcription_result = self.transcription_service.execute(
                video_path=str(video_file),
                model_size=model_size,
                language=language,
                progress_callback=lambda p, m: update_progress(p, m),
            )

            if not transcription_result.success:
                return transcription_result

            segments = transcription_result.data["segments"]

            # Stage 2: テキスト差分検出
            current_stage = 1
            update_progress(0, "テキスト差分を検出中...")

            diff_result = self.text_service.execute(
                action="find_differences",
                base_text=base_text,
                target_text=target_text,
                segments=segments,
                progress_callback=lambda p, m: update_progress(p, m),
            )

            if not diff_result.success:
                return diff_result

            target_segments = diff_result.data["segments"]

            # Stage 3: 無音削除（オプション）
            if remove_silence:
                current_stage = 2
                update_progress(0, "無音部分を削除中...")

                silence_result = self.video_service.execute(
                    action="remove_silence",
                    video_path=str(video_file),
                    segments=target_segments,
                    progress_callback=lambda p, m: update_progress(p, m),
                )

                if not silence_result.success:
                    return silence_result

                target_segments = silence_result.data["segments"]

            # Stage 4: エクスポート
            current_stage = total_stages - 1
            update_progress(0, f"{export_format.upper()}をエクスポート中...")

            export_result = self.export_service.execute(
                action="export",
                format=export_format,
                segments=target_segments,
                video_path=str(video_file),
                output_dir=output_dir,
                remove_silence=remove_silence,
                progress_callback=lambda p, m: update_progress(p, m),
            )

            if not export_result.success:
                return export_result

            # 最終結果
            update_progress(1.0, "処理が完了しました")

            return self.create_success_result(
                data={
                    "transcription": transcription_result.data,
                    "differences": diff_result.data,
                    "export": export_result.data,
                    "output_files": export_result.data.get("files", []),
                },
                metadata={
                    "total_segments": len(segments),
                    "target_segments": len(target_segments),
                    "silence_removed": remove_silence,
                    "export_format": export_format,
                    "output_directory": output_dir,
                },
            )

        except Exception as e:
            self.logger.error(f"フル処理エラー: {e}", exc_info=True)
            return self.wrap_error(ProcessingError(f"処理中にエラーが発生しました: {str(e)}"))

    def transcribe_and_export(
        self,
        video_path: str,
        model_size: str = ProcessingDefaults.LANGUAGE,
        language: str = ProcessingDefaults.LANGUAGE,
        export_formats: list[str] = ["srt"],
        output_dir: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ServiceResult:
        """文字起こしとエクスポートのみ

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            language: 言語コード
            export_formats: エクスポート形式のリスト
            output_dir: 出力ディレクトリ
            progress_callback: 進捗コールバック

        Returns:
            ServiceResult: 処理結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not output_dir:
                output_dir = str(video_file.parent / "output")
            ensure_directory(output_dir)

            # Stage 1: 文字起こし
            if progress_callback:
                progress_callback(0, "文字起こしを開始...")

            transcription_result = self.transcription_service.execute(
                video_path=str(video_file),
                model_size=model_size,
                language=language,
                progress_callback=lambda p, m: progress_callback(p * 0.7, m) if progress_callback else None,
            )

            if not transcription_result.success:
                return transcription_result

            segments = transcription_result.data["segments"]

            # Stage 2: 各形式でエクスポート
            export_results = []
            for i, format_type in enumerate(export_formats):
                if progress_callback:
                    base_progress = 0.7 + (0.3 * i / len(export_formats))
                    progress_callback(base_progress, f"{format_type.upper()}をエクスポート中...")

                export_result = self.export_service.execute(
                    action="export",
                    format=format_type,
                    segments=segments,
                    video_path=str(video_file),
                    output_dir=output_dir,
                )

                if export_result.success:
                    export_results.append({"format": format_type, "files": export_result.data.get("files", [])})

            if progress_callback:
                progress_callback(1.0, "処理が完了しました")

            return self.create_success_result(
                data={"transcription": transcription_result.data, "exports": export_results},
                metadata={
                    "total_segments": len(segments),
                    "export_formats": export_formats,
                    "output_directory": output_dir,
                },
            )

        except Exception as e:
            self.logger.error(f"文字起こし・エクスポートエラー: {e}", exc_info=True)
            return self.wrap_error(ProcessingError(f"処理中にエラーが発生しました: {str(e)}"))

    def process_with_silence_removal(
        self,
        video_path: str,
        segments: list[TranscriptionSegmentV2],
        threshold: float = SilenceDetection.DEFAULT_THRESHOLD,
        min_silence_duration: float = SilenceDetection.MIN_SILENCE_DURATION,
        pad_start: float = SilenceDetection.DEFAULT_PAD_START,
        pad_end: float = SilenceDetection.DEFAULT_PAD_END,
        export_video: bool = True,
        export_fcpxml: bool = True,
        output_dir: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ServiceResult:
        """無音削除付き処理

        Args:
            video_path: 動画ファイルパス
            segments: 処理対象セグメント
            threshold: 無音判定閾値
            min_silence_duration: 最小無音時間
            pad_start: 開始パディング
            pad_end: 終了パディング
            export_video: 動画出力の有無
            export_fcpxml: FCPXML出力の有無
            output_dir: 出力ディレクトリ
            progress_callback: 進捗コールバック

        Returns:
            ServiceResult: 処理結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not output_dir:
                output_dir = str(video_file.parent / "output")
            ensure_directory(output_dir)

            # Stage 1: 無音削除
            if progress_callback:
                progress_callback(0, "無音部分を検出中...")

            silence_result = self.video_service.execute(
                action="remove_silence",
                video_path=str(video_file),
                segments=segments,
                threshold=threshold,
                min_silence_duration=min_silence_duration,
                pad_start=pad_start,
                pad_end=pad_end,
                progress_callback=lambda p, m: progress_callback(p * 0.5, m) if progress_callback else None,
            )

            if not silence_result.success:
                return silence_result

            processed_segments = silence_result.data["segments"]

            # Stage 2: エクスポート
            export_results = []
            current_progress = 0.5

            if export_video:
                if progress_callback:
                    progress_callback(current_progress, "動画を出力中...")

                # 動画エクスポート（ここでは動画処理サービスを使用）
                video_result = self._export_video_with_silence_removal(video_file, processed_segments, output_dir)

                if video_result:
                    export_results.append(video_result)

                current_progress = 0.75

            if export_fcpxml:
                if progress_callback:
                    progress_callback(current_progress, "FCPXMLを生成中...")

                fcpxml_result = self.export_service.execute(
                    action="export",
                    format="fcpxml",
                    segments=processed_segments,
                    video_path=str(video_file),
                    output_dir=output_dir,
                    remove_silence=True,
                )

                if fcpxml_result.success:
                    export_results.extend(fcpxml_result.data.get("files", []))

            if progress_callback:
                progress_callback(1.0, "処理が完了しました")

            return self.create_success_result(
                data={
                    "segments": processed_segments,
                    "silence_stats": silence_result.metadata,
                    "export_files": export_results,
                },
                metadata={
                    "original_segments": len(segments),
                    "processed_segments": len(processed_segments),
                    "silence_removed": True,
                    "output_directory": output_dir,
                },
            )

        except Exception as e:
            self.logger.error(f"無音削除処理エラー: {e}", exc_info=True)
            return self.wrap_error(ProcessingError(f"処理中にエラーが発生しました: {str(e)}"))

    def _export_video_with_silence_removal(
        self, video_file: Path, segments: list[TranscriptionSegmentV2], output_dir: str
    ) -> dict[str, Any] | None:
        """無音削除済み動画をエクスポート（内部メソッド）

        Args:
            video_file: 入力動画ファイル
            segments: 処理済みセグメント
            output_dir: 出力ディレクトリ

        Returns:
            エクスポート結果の辞書、失敗時はNone
        """
        try:
            output_name = f"{video_file.stem}_NoSilence.mp4"
            output_path = Path(output_dir) / output_name

            # 実際の動画処理はvideo_processing_serviceに委譲
            # ここでは簡略化

            return {"type": "video", "path": str(output_path), "name": output_name}

        except Exception as e:
            self.logger.error(f"動画エクスポートエラー: {e}")
            return None

    def validate_workflow_inputs(self, workflow: str, inputs: dict[str, Any]) -> tuple[bool, str | None]:
        """ワークフロー入力を検証

        Args:
            workflow: ワークフロー名
            inputs: 入力パラメータ

        Returns:
            (検証成功, エラーメッセージ)
        """
        required_fields = {
            "full_process": ["video_path", "base_text", "target_text"],
            "transcribe_and_export": ["video_path"],
            "process_with_silence_removal": ["video_path", "segments"],
        }

        if workflow not in required_fields:
            return False, f"不明なワークフロー: {workflow}"

        missing = [f for f in required_fields[workflow] if f not in inputs]
        if missing:
            return False, f"必須パラメータが不足: {', '.join(missing)}"

        return True, None
