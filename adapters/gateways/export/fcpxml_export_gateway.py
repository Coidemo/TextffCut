"""
FCPXMLエクスポートゲートウェイの実装

レガシーのFCPXMLExporterを使用してFCPXMLファイルを生成します。
"""

import logging

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
        logger.info("=== FCPXMLエクスポートゲートウェイ ===")
        logger.info(f"入力動画: {video_path}")
        logger.info(f"時間範囲数: {len(time_ranges)}")
        logger.info(f"with_gap_removal: {with_gap_removal}")
        logger.info(f"ズーム: {scale[0] * 100:.0f}% x {scale[1] * 100:.0f}%")
        logger.info(f"アンカー: ({anchor[0]:.1f}, {anchor[1]:.1f})")
        for i, (start, end) in enumerate(time_ranges):
            logger.info(f"  範囲 {i+1}: {start:.2f}秒 - {end:.2f}秒")

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
                    timeline_start=timeline_start if with_gap_removal else start,
                )
                segments.append(segment)
                if with_gap_removal:
                    timeline_start += end - start

            # FCPXMLを生成（exportメソッドが直接ファイルに書き込む）
            success = exporter.export(
                segments, 
                output_path, 
                scale=scale, 
                anchor=anchor, 
                timeline_resolution=timeline_resolution,
                overlay_settings=overlay_settings,
                bgm_settings=bgm_settings,
                additional_audio_settings=additional_audio_settings
            )

            if not success:
                raise RuntimeError("FCPXMLの生成に失敗しました")

            logger.info(f"FCPXMLファイルを出力しました: {output_path}")

        except Exception as e:
            logger.error(f"FCPXMLエクスポート中にエラーが発生しました: {e}")
            raise
