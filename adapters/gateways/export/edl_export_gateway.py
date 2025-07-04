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
            # 動画情報を取得
            video_info = self.video_processor.get_video_info(str(video_path))

            # EDLExporterのインスタンスを作成
            exporter = EDLExporter(str(video_path), video_info)

            # EDLを生成
            edl_content = exporter.export(time_ranges)

            # ファイルに書き出し
            Path(output_path).write_text(edl_content, encoding="utf-8")

            logger.info(f"EDLファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"EDLエクスポート中にエラーが発生しました: {e}")
            raise
