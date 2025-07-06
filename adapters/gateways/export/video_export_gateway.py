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
            import os
            import tempfile

            temp_paths = []
            total_ranges = len(time_ranges)

            # 一時ディレクトリを作成
            with tempfile.TemporaryDirectory() as temp_dir:
                # 各時間範囲を個別に切り出し（一時ファイルとして）
                for i, (start, end) in enumerate(time_ranges):
                    # プログレスコールバックのラッパー
                    def segment_progress(p: float, msg: str):
                        if progress_callback:
                            overall_progress = (i + p) / total_ranges * 0.8  # 80%まで
                            progress_callback(overall_progress, f"セグメント {i+1}/{total_ranges}: {msg}")

                    # 一時ファイル名を生成
                    temp_path = os.path.join(temp_dir, f"segment_{i:04d}.mp4")

                    # セグメントを抽出
                    success = self.video_processor.extract_segment(
                        str(video_path), start, end, temp_path, segment_progress
                    )

                    if success:
                        temp_paths.append(temp_path)
                    else:
                        logger.error(f"セグメント {i+1} の抽出に失敗しました: {start}s - {end}s")

                # 複数セグメントがある場合は結合
                if len(temp_paths) > 1:
                    if progress_callback:
                        progress_callback(0.8, "セグメントを結合中...")

                    # 最終出力ファイル名（連番付き）
                    final_output = f"{output_base}.mp4"

                    # 結合処理のプログレスコールバック
                    def combine_progress(p: float, msg: str):
                        if progress_callback:
                            progress_callback(0.8 + p * 0.2, msg)  # 80-100%

                    # セグメントを結合
                    success = self.video_processor.combine_videos(temp_paths, final_output, combine_progress)

                    if success:
                        return [final_output]
                    else:
                        logger.error("セグメントの結合に失敗しました")
                        return []

                # 単一セグメントの場合はそのまま移動
                elif len(temp_paths) == 1:
                    final_output = f"{output_base}.mp4"
                    # 一時ファイルを最終出力先にコピー
                    import shutil

                    shutil.copy2(temp_paths[0], final_output)
                    return [final_output]

                else:
                    logger.error("抽出できたセグメントがありません")
                    return []

        except Exception as e:
            logger.error(f"動画クリップのエクスポート中にエラーが発生しました: {e}")
            raise
