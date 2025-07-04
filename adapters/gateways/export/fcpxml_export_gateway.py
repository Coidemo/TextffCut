"""
FCPXMLエクスポートゲートウェイの実装

レガシーのFCPXMLExporterを使用してFCPXMLファイルを生成します。
"""

import logging
from pathlib import Path

from config import Config
from core.export import FCPXMLExporter
from core.video import VideoProcessor
from domain.value_objects.file_path import FilePath
from use_cases.interfaces.export_gateways import IFCPXMLExportGateway

logger = logging.getLogger(__name__)


class FCPXMLExportGatewayAdapter(IFCPXMLExportGateway):
    """
    FCPXMLエクスポートゲートウェイのアダプター実装

    レガシーのFCPXMLExporterをラップしてクリーンアーキテクチャに適応させます。
    """

    def __init__(self, config: Config):
        """
        初期化

        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.video_processor = VideoProcessor(config)

    def export(
        self,
        video_path: FilePath,
        time_ranges: list[tuple[float, float]],
        output_path: str,
        with_gap_removal: bool = False,
    ) -> None:
        """
        FCPXMLファイルをエクスポート

        Args:
            video_path: 入力動画パス
            time_ranges: クリップの時間範囲リスト
            output_path: 出力XMLファイルパス
            with_gap_removal: 隙間を詰めて配置するかどうか
        """
        try:
            # FCPXMLExporterのインスタンスを作成
            exporter = FCPXMLExporter(self.config)

            # ExportSegmentのリストを作成
            from core.export import ExportSegment
            segments = []
            timeline_start = 0.0
            
            for start, end in time_ranges:
                segment = ExportSegment(
                    source_path=str(video_path),
                    start_time=start,
                    end_time=end,
                    timeline_start=timeline_start if with_gap_removal else start
                )
                segments.append(segment)
                if with_gap_removal:
                    timeline_start += (end - start)

            # FCPXMLを生成（exportメソッドが直接ファイルに書き込む）
            success = exporter.export(segments, output_path)
            
            if not success:
                raise RuntimeError("FCPXMLの生成に失敗しました")

            logger.info(f"FCPXMLファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"FCPXMLエクスポート中にエラーが発生しました: {e}")
            raise
