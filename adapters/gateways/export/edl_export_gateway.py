"""
EDLエクスポートゲートウェイの実装

レガシーのEDLExporterを使用してEDLファイルを生成します。
"""

import logging
from pathlib import Path

from config import Config
from core.export import EDLExporter
from core.video import VideoProcessor
from domain.value_objects.file_path import FilePath
from use_cases.interfaces.export_gateways import IEDLExportGateway

logger = logging.getLogger(__name__)


class EDLExportGatewayAdapter(IEDLExportGateway):
    """
    EDLエクスポートゲートウェイのアダプター実装

    レガシーのEDLExporterをラップしてクリーンアーキテクチャに適応させます。
    """

    def __init__(self, config: Config):
        """
        初期化

        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.video_processor = VideoProcessor(config)

    def export(self, video_path: FilePath, time_ranges: list[tuple[float, float]], output_path: str) -> None:
        """
        EDLファイルをエクスポート

        Args:
            video_path: 入力動画パス
            time_ranges: クリップの時間範囲リスト
            output_path: 出力EDLファイルパス
        """
        try:
            # EDLExporterのインスタンスを作成
            exporter = EDLExporter(self.config)

            # ExportSegmentのリストを作成
            from core.export import ExportSegment
            segments = []
            timeline_start = 0.0
            
            for start, end in time_ranges:
                segment = ExportSegment(
                    source_path=str(video_path),
                    start_time=start,
                    end_time=end,
                    timeline_start=timeline_start
                )
                segments.append(segment)
                timeline_start += (end - start)

            # EDLを生成（exportメソッドが直接ファイルに書き込む）
            success = exporter.export(segments, output_path)
            
            if not success:
                raise RuntimeError("EDLの生成に失敗しました")

            logger.info(f"EDLファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"EDLエクスポート中にエラーが発生しました: {e}")
            raise
