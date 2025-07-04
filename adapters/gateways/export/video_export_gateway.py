"""
動画エクスポートゲートウェイの実装

レガシーのVideoProcessorを使用して動画クリップをエクスポートします。
"""

import logging
from collections.abc import Callable

from config import Config
from core.video import VideoProcessor
from domain.value_objects.file_path import FilePath
from use_cases.interfaces.export_gateways import IVideoExportGateway

logger = logging.getLogger(__name__)


class VideoExportGatewayAdapter(IVideoExportGateway):
    """
    動画エクスポートゲートウェイのアダプター実装

    レガシーのVideoProcessorをラップしてクリーンアーキテクチャに適応させます。
    """

    def __init__(self, config: Config):
        """
        初期化

        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.video_processor = VideoProcessor(config)

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
        try:
            # レガシー実装を呼び出し
            output_paths = self.video_processor.extract_and_save_clips(
                str(video_path), time_ranges, output_base, progress_callback
            )

            return output_paths

        except Exception as e:
            logger.error(f"動画クリップのエクスポート中にエラーが発生しました: {e}")
            raise
