#!/usr/bin/env python
"""
アライメント処理用ワーカープロセス

文字起こし結果に対してアライメント処理を実行し、
処理完了後に自動的に終了してメモリを解放する。

2段階処理アーキテクチャ対応:
- TranscriptionSegmentV2形式のデータ処理
- 堅牢なエラーハンドリング
- 詳細な進捗報告
"""

import json
import logging
import os
import sys
from typing import Any

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def send_progress(progress: float, message: str = ""):
    """プログレス情報を親プロセスに送信"""
    print(f"PROGRESS:{progress}|{message}", flush=True)


def process_alignment(config_data: dict[str, Any]) -> dict[str, Any]:
    """
    アライメント処理を実行

    Args:
        config_data: 処理設定

    Returns:
        処理結果
    """
    try:
        # 設定の復元
        from config import Config
        from core.alignment_processor import AlignmentProcessor
        from core.memory_monitor import MemoryMonitor
        from core.models import TranscriptionSegmentV2

        config = Config()

        # モデルサイズ情報を取得（APIモードの場合はwhisper-1）
        model_size = config_data.get("model_size", "base")

        # TranscriptionConfigを更新
        transcription_config = config_data["config"]["transcription"]
        config.transcription.language = transcription_config["language"]
        config.transcription.compute_type = transcription_config["compute_type"]
        # batch_sizeは自動最適化で管理されるため、ここでは設定しない

        # セグメントの復元
        segments = []
        for seg_data in config_data["segments"]:
            segment = TranscriptionSegmentV2.from_dict(seg_data)
            segments.append(segment)

        audio_path = config_data["audio_path"]
        language = config_data["language"]

        logger.info(f"アライメント処理開始: {len(segments)}セグメント")
        send_progress(0.0, "アライメント処理を開始しています...")

        # アライメント診断を実行
        from core.alignment_diagnostics import AlignmentDiagnostics

        logger.info("アライメント診断フェーズを開始")
        diagnostics = AlignmentDiagnostics(model_size, config)

        # メモリに余裕がある場合のみ実際のモデルロードテストを実行
        memory_monitor = MemoryMonitor()
        initial_memory = memory_monitor.get_memory_usage()
        test_alignment = len(segments) > 20 and initial_memory < 70

        # 診断を実行
        diagnostic_result = diagnostics.run_diagnostics(
            segment_count=len(segments), language=language, test_alignment=test_alignment
        )

        # 診断結果から最適なバッチサイズを取得
        optimal_batch_size = diagnostic_result.optimal_batch_size

        # 警告があれば表示
        for warning in diagnostic_result.warnings:
            logger.warning(warning)

        # 推奨事項があれば表示
        for recommendation in diagnostic_result.recommendations:
            logger.info(f"推奨: {recommendation}")

        # 最適化されたバッチサイズでアライメントプロセッサーを初期化
        processor = AlignmentProcessor(config, batch_size=optimal_batch_size)

        # プログレスコールバック
        def progress_callback(progress: float, message: str):
            logger.info(f"進捗: {progress:.1%} - {message}")
            send_progress(progress, message)

        # アライメント実行
        aligned_segments = processor.align(segments, audio_path, language, progress_callback)

        # 結果の検証
        success_count = sum(1 for s in aligned_segments if s.has_valid_alignment())
        failed_count = sum(1 for s in aligned_segments if s.alignment_error is not None)

        logger.info(f"アライメント完了: 成功={success_count}, " f"失敗={failed_count}, 総数={len(aligned_segments)}")

        # 結果を辞書形式に変換
        result_segments = []
        for segment in aligned_segments:
            result_segments.append(segment.to_dict())

        return {
            "success": True,
            "segments": result_segments,
            "statistics": {"total": len(aligned_segments), "success": success_count, "failed": failed_count},
        }

    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        logger.error(f"アライメント処理エラー: {str(e)}\n{error_traceback}")

        # エラー詳細を標準エラー出力にも出力
        print(f"ERROR:アライメント処理エラー: {str(e)}", file=sys.stderr, flush=True)
        print(f"TRACEBACK:\n{error_traceback}", file=sys.stderr, flush=True)

        return {"success": False, "error": str(e), "traceback": error_traceback, "segments": []}


def main():
    """ワーカーメイン処理"""
    try:
        # コマンドライン引数から設定ファイルパスを取得
        if len(sys.argv) < 2:
            logger.error("設定ファイルパスが指定されていません")
            sys.exit(1)

        config_path = sys.argv[1]

        if not os.path.exists(config_path):
            logger.error(f"設定ファイルが見つかりません: {config_path}")
            sys.exit(1)

        # 設定を読み込み
        with open(config_path) as f:
            config_data = json.load(f)

        logger.info("アライメントワーカーを開始")

        # 初期メモリ使用量を記録
        try:
            import psutil

            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"初期メモリ使用量: {mem_mb:.1f}MB")
        except:
            pass

        # アライメント処理を実行
        result = process_alignment(config_data)

        # 結果ファイルのパスを設定ファイルと同じディレクトリに
        result_path = os.path.join(os.path.dirname(config_path), "align_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        if result["success"]:
            logger.info("アライメント処理が正常に完了しました")
            send_progress(1.0, "アライメント処理が完了しました")

            # メモリ使用量を記録
            try:
                import psutil

                process = psutil.Process()
                mem_info = process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                logger.info(f"最終メモリ使用量: {mem_mb:.1f}MB")
            except:
                pass

            sys.exit(0)
        else:
            logger.error(f"アライメント処理に失敗: {result.get('error', '不明なエラー')}")
            print(f"ERROR:{result.get('error', '不明なエラー')}", flush=True)
            sys.exit(1)

    except Exception as e:
        logger.error(f"ワーカー処理でエラー: {str(e)}", exc_info=True)
        print(f"ERROR:{str(e)}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
