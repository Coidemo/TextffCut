"""
SRT字幕エクスポートゲートウェイの実装

レガシーのSRTDiffExporterを使用してSRT字幕ファイルを生成します。
"""

import logging
from typing import Any

from config import Config
from core.srt_diff_exporter import SRTDiffExporter
from core.text_processor import TextProcessor
from use_cases.interfaces.export_gateways import ISRTExportGateway

logger = logging.getLogger(__name__)


class SRTExportGatewayAdapter(ISRTExportGateway):
    """
    SRT字幕エクスポートゲートウェイのアダプター実装

    レガシーのSRTDiffExporterをラップしてクリーンアーキテクチャに適応させます。
    """

    def __init__(self, config: Config):
        """
        初期化

        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.srt_exporter = SRTDiffExporter(self.config)
        self.text_processor = TextProcessor()

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
        try:
            # デフォルト設定
            if settings is None:
                settings = {"max_line_length": 40, "max_lines": 2}

            # SRT設定を更新
            if "max_line_length" in settings:
                self.srt_exporter.max_line_length = settings["max_line_length"]
            if "max_lines" in settings:
                self.srt_exporter.max_lines = settings["max_lines"]

            # 時間範囲が指定されている場合は差分検出ベースでエクスポート
            if time_ranges:
                # テキストプロセッサーで差分を作成
                full_text = transcription_result.get("text", "")

                # time_rangesから差分オブジェクトを作成（簡易実装）
                # 実際にはもっと複雑な処理が必要だが、ここでは簡易的に実装
                success = self.srt_exporter.export_with_silence_removal(
                    transcription_result=transcription_result,
                    output_path=output_path,
                    keep_ranges=time_ranges,
                    encoding="utf-8",
                    srt_settings=settings,
                )
            else:
                # 全体をエクスポート（差分なし）
                # SRTExporterの基本エクスポート機能を使用
                from core.srt_exporter import SRTExporter

                basic_exporter = SRTExporter(self.config)
                segments = transcription_result.get("segments", [])
                success = basic_exporter.export(segments=segments, output_path=output_path, encoding="utf-8")

            if not success:
                raise Exception("SRT字幕の生成に失敗しました")

            logger.info(f"SRT字幕ファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"SRT字幕エクスポート中にエラーが発生しました: {e}")
            raise
