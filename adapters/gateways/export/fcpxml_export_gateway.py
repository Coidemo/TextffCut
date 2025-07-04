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
            # 動画情報を取得
            video_info = self.video_processor.get_video_info(str(video_path))

            # FCPXMLExporterのインスタンスを作成
            exporter = FCPXMLExporter(str(video_path), video_info)

            # FCPXMLを生成
            fcpxml_content = exporter.export(time_ranges, with_gap_removal)

            # ファイルに書き出し
            Path(output_path).write_text(fcpxml_content, encoding="utf-8")

            logger.info(f"FCPXMLファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"FCPXMLエクスポート中にエラーが発生しました: {e}")
            raise
