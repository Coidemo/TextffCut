"""
TranscriptionWorker - 文字起こしワーカーのクラスベース実装

worker_transcribe.pyの機能をクラスベースで再設計。
エラーハンドリング、状態管理、テスタビリティを改善。
"""

import json
import sys
from pathlib import Path
from typing import Any

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from core.constants import PerformanceSettings, ProcessingDefaults
from core.error_handling import ErrorHandler, ProcessingError, ResourceError, ValidationError
from core.models import TranscriptionSegmentV2
from core.transcription import Transcriber
from utils.cleanup import TempFileManager
from utils.logging import get_logger


class TranscriptionWorker:
    """文字起こしワーカークラス"""

    def __init__(self, config: Config) -> None:
        """初期化

        Args:
            config: 設定オブジェクト
        """
        self.config = config
        self.logger = get_logger("TranscriptionWorker")
        self.error_handler = ErrorHandler(self.logger)
        self.transcriber: Transcriber | None = None
        self.temp_manager = TempFileManager()

    def initialize_transcriber(
        self, model_size: str, language: str, device: str = "auto", compute_type: str = "int8"
    ) -> None:
        """文字起こしエンジンを初期化

        Args:
            model_size: モデルサイズ
            language: 言語コード
            device: デバイス（cpu/cuda/auto）
            compute_type: 計算精度

        Raises:
            ResourceError: リソース不足の場合
            ValidationError: 無効なパラメータの場合
        """
        try:
            self.logger.info(
                f"文字起こしエンジン初期化: "
                f"model={model_size}, lang={language}, "
                f"device={device}, compute={compute_type}"
            )

            # Transcriberはconfigのみで初期化
            self.transcriber = Transcriber(config=self.config)

            # モデルサイズなどは後で使用するため保存
            self.model_size = model_size
            self.language = language
            self.device = device
            self.compute_type = compute_type

        except Exception as e:
            error = ResourceError(f"文字起こしエンジンの初期化に失敗: {str(e)}", cause=e)
            self.error_handler.handle_error(error, "initialize_transcriber")
            raise

    def process_segment(
        self, segment_data: dict[str, Any], audio_path: str, chunk_duration: float | None = None
    ) -> dict[str, Any]:
        """単一セグメントを処理

        Args:
            segment_data: セグメント情報
            audio_path: 音声ファイルパス
            chunk_duration: チャンクサイズ（秒）

        Returns:
            処理結果の辞書

        Raises:
            ProcessingError: 処理エラーの場合
        """
        try:
            # セグメントの検証
            segment = self._validate_segment(segment_data)

            # 音声ファイルの検証
            audio_file = self._validate_audio_file(audio_path)

            # 文字起こし実行
            result = self._transcribe_segment(segment, audio_file, chunk_duration)

            return {
                "success": True,
                "segment_id": segment.id,
                "result": result.to_dict() if hasattr(result, "to_dict") else result,
            }

        except Exception as e:
            return self._handle_segment_error(segment_data.get("id", "unknown"), e)

    def process_all_segments(
        self,
        segments: list[dict[str, Any]],
        audio_path: str,
        chunk_duration: float | None = None,
        batch_size: int = PerformanceSettings.DEFAULT_NUM_WORKERS,
    ) -> list[dict[str, Any]]:
        """複数セグメントをバッチ処理

        Args:
            segments: セグメントリスト
            audio_path: 音声ファイルパス
            chunk_duration: チャンクサイズ（秒）
            batch_size: バッチサイズ

        Returns:
            処理結果のリスト
        """
        results = []

        # バッチ処理
        for i in range(0, len(segments), batch_size):
            batch = segments[i : i + batch_size]

            self.logger.info(f"バッチ処理: {i+1}-{min(i+batch_size, len(segments))}/{len(segments)}")

            # 並列処理
            batch_results = self._process_batch_parallel(batch, audio_path, chunk_duration)

            results.extend(batch_results)

        return results

    def _validate_segment(self, segment_data: dict[str, Any]) -> TranscriptionSegmentV2:
        """セグメントデータを検証

        Args:
            segment_data: セグメント辞書

        Returns:
            検証済みセグメントオブジェクト

        Raises:
            ValidationError: 無効なデータの場合
        """
        required_fields = ["id", "start", "end"]
        missing_fields = [f for f in required_fields if f not in segment_data]

        if missing_fields:
            raise ValidationError(f"必須フィールドが不足: {', '.join(missing_fields)}")

        # セグメントオブジェクトに変換
        segment = TranscriptionSegmentV2.from_dict(segment_data) if isinstance(segment_data, dict) else segment_data

        # 時間の妥当性チェック
        if segment.start < 0 or segment.end <= segment.start:
            raise ValidationError(f"無効な時間範囲: start={segment.start}, end={segment.end}")

        return segment

    def _validate_audio_file(self, audio_path: str) -> Path:
        """音声ファイルを検証

        Args:
            audio_path: ファイルパス

        Returns:
            検証済みPathオブジェクト

        Raises:
            ValidationError: ファイルが存在しない場合
        """
        audio_file = Path(audio_path)

        if not audio_file.exists():
            raise ValidationError(f"音声ファイルが見つかりません: {audio_path}")

        if not audio_file.is_file():
            raise ValidationError(f"パスがファイルではありません: {audio_path}")

        # ファイルサイズチェック（0バイトでないこと）
        if audio_file.stat().st_size == 0:
            raise ValidationError(f"音声ファイルが空です: {audio_path}")

        return audio_file

    def _transcribe_segment(
        self, segment: TranscriptionSegmentV2, audio_file: Path, chunk_duration: float | None
    ) -> dict[str, Any]:
        """セグメントの文字起こしを実行

        Args:
            segment: セグメントオブジェクト
            audio_file: 音声ファイル
            chunk_duration: チャンクサイズ

        Returns:
            文字起こし結果

        Raises:
            ProcessingError: 処理失敗の場合
        """
        if not self.transcriber:
            raise ProcessingError("文字起こしエンジンが初期化されていません")

        try:
            # 一時ファイルの作成
            temp_audio = self.temp_manager.create_temp_file(suffix=f"_{segment.id}.wav", prefix="segment_")

            # セグメント音声の抽出
            self._extract_segment_audio(audio_file, segment, temp_audio)

            # 文字起こし実行
            result = self.transcriber.transcribe(str(temp_audio), chunk_duration=chunk_duration)

            # 時間調整
            if hasattr(result, "segments"):
                for seg in result.segments:
                    seg.start += segment.start
                    seg.end += segment.start

            return result

        finally:
            # 一時ファイルのクリーンアップ
            self.temp_manager.cleanup_file(temp_audio)

    def _extract_segment_audio(self, audio_file: Path, segment: TranscriptionSegmentV2, output_path: Path) -> None:
        """音声セグメントを抽出

        Args:
            audio_file: 入力音声ファイル
            segment: セグメント情報
            output_path: 出力パス

        Raises:
            ProcessingError: 抽出失敗の場合
        """
        import subprocess

        cmd = [
            "ffmpeg",
            "-i",
            str(audio_file),
            "-ss",
            str(segment.start),
            "-to",
            str(segment.end),
            "-c",
            "copy",
            "-y",
            str(output_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=ProcessingDefaults.SUBPROCESS_TIMEOUT)

            if result.returncode != 0:
                raise ProcessingError(f"音声抽出に失敗: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise ProcessingError("音声抽出がタイムアウトしました") from None

    def _process_batch_parallel(
        self, batch: list[dict[str, Any]], audio_path: str, chunk_duration: float | None
    ) -> list[dict[str, Any]]:
        """バッチを並列処理

        Args:
            batch: セグメントのバッチ
            audio_path: 音声ファイルパス
            chunk_duration: チャンクサイズ

        Returns:
            処理結果リスト
        """
        # シンプルな実装（将来的にはマルチプロセシング化）
        results = []
        for segment in batch:
            result = self.process_segment(segment, audio_path, chunk_duration)
            results.append(result)

        return results

    def _handle_segment_error(self, segment_id: str, error: Exception) -> dict[str, Any]:
        """セグメントエラーをハンドリング

        Args:
            segment_id: セグメントID
            error: 発生したエラー

        Returns:
            エラー結果の辞書
        """
        # エラーをラップ
        if not isinstance(error, ProcessingError):
            error = ProcessingError(
                f"セグメント処理エラー: {str(error)}",
                stage="process_batch",
                details={"error_type": type(error).__name__, "error_message": str(error)},
            )

        # エラーハンドラで処理
        handled_error = self.error_handler.handle_error(error)

        return {
            "success": False,
            "segment_id": segment_id,
            "error": handled_error["user_message"],
            "error_details": handled_error,
        }

    def handle_error(self, error: Exception, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """エラーをハンドリング（互換性のため）

        Args:
            error: 発生したエラー
            context: エラーコンテキスト

        Returns:
            エラー情報の辞書
        """
        if context:
            self.logger.error(f"エラーコンテキスト: {context}")

        return self.error_handler.handle_error(error)

    def cleanup(self) -> None:
        """リソースのクリーンアップ"""
        self.temp_manager.cleanup()

        if self.transcriber:
            # 文字起こしエンジンのクリーンアップ
            try:
                # クリーンアップメソッドがあれば呼び出し
                if hasattr(self.transcriber, "cleanup"):
                    self.transcriber.cleanup()
            except Exception as e:
                self.logger.warning(f"クリーンアップエラー: {e}")


# worker_transcribe.pyとの互換性のためのエントリーポイント
def main() -> None:
    """メインエントリーポイント（互換性用）"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=str, required=True)
    parser.add_argument("--audio", type=str, required=True)
    parser.add_argument("--model", type=str, default="medium")
    parser.add_argument("--language", type=str, default="ja")
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--compute", type=str, default="int8")
    parser.add_argument("--chunk", type=float, default=None)

    args = parser.parse_args()

    # 設定とワーカーの初期化
    config = Config()
    worker = TranscriptionWorker(config)

    try:
        # 文字起こしエンジンの初期化
        worker.initialize_transcriber(
            model_size=args.model, language=args.language, device=args.device, compute_type=args.compute
        )

        # セグメントデータの読み込み
        segment_data = json.loads(args.segment)

        # 処理実行
        result = worker.process_segment(segment_data, args.audio, args.chunk)

        # 結果を出力
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        # エラー処理
        error_result = worker.handle_error(e)
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

    finally:
        # クリーンアップ
        worker.cleanup()


if __name__ == "__main__":
    main()
