"""
文字起こしゲートウェイの実装

既存のTranscriberクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

import time
from collections.abc import Callable
from typing import Any

from adapters.converters.transcription_converter import TranscriptionConverter
from config import Config
from core.transcription import Transcriber as LegacyTranscriber
from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.interfaces import ITranscriptionGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class TranscriptionGatewayAdapter(ITranscriptionGateway):
    """
    文字起こしゲートウェイのアダプター実装

    既存のTranscriberクラスをラップし、ドメイン層のインターフェースに適合させます。
    """

    def __init__(self, config: Config | None = None):
        """
        Args:
            config: 設定オブジェクト（省略時はデフォルト設定）
        """
        self.config = config or Config()
        self._legacy_transcriber = LegacyTranscriber(self.config)
        self._converter = TranscriptionConverter()

    def transcribe(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        language: str | None = None,
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """
        動画ファイルを文字起こし

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            language: 言語コード（省略時は自動検出）
            use_cache: キャッシュを使用するか
            progress_callback: 進捗コールバック

        Returns:
            文字起こし結果

        Raises:
            TranscriptionError: 文字起こしに失敗
        """
        try:
            # ドメイン型をレガシー型に変換
            legacy_path = str(video_path)

            # 開始時間を記録
            start_time = time.time()

            # APIモードの設定を再確認（動的に設定が変更される可能性があるため）
            current_use_api = self.config.transcription.use_api
            logger.info(f"TranscriptionGatewayAdapter.transcribe - APIモード: {current_use_api}")
            logger.info(f"model_size: {model_size}, video_path: {legacy_path}")
            
            # 現在の設定に基づいてTranscriberを再作成（設定が変更されている可能性があるため）
            if current_use_api != getattr(self._legacy_transcriber, '_last_use_api', None):
                logger.info(f"APIモード設定が変更されました。Transcriberを再作成します。")
                from core.transcription import Transcriber as LegacyTranscriber
                self._legacy_transcriber = LegacyTranscriber(self.config)
                # 最後の設定を記録
                self._legacy_transcriber._last_use_api = current_use_api
            
            # レガシーメソッドを呼び出し
            legacy_result = self._legacy_transcriber.transcribe(
                video_path=legacy_path,
                model_size=model_size,
                # progressパラメータ名の違いに注意
                progress_callback=progress_callback,
                use_cache=use_cache,  # use_cacheパラメータを追加
            )

            # 処理時間を計算
            processing_time = time.time() - start_time

            # レガシー結果をドメインエンティティに変換
            domain_result = self._converter.legacy_to_domain(legacy_result, processing_time=processing_time)

            # 変換の妥当性を検証（デバッグモードのみ）
            # TextffCutLoggerではisEnabledForが使えないため、環境変数でチェック
            import os

            if os.getenv("DEBUG", "").lower() in ("true", "1", "yes"):
                if not self._converter.validate_conversion(legacy_result, domain_result):
                    logger.warning("Conversion validation failed")

            logger.info(f"Transcription completed: {len(domain_result.segments)} segments, " f"{processing_time:.1f}s")

            return domain_result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            # レガシーエラーをユースケース層の例外に変換
            from use_cases.exceptions import TranscriptionError

            raise TranscriptionError(f"Failed to transcribe {video_path}: {str(e)}", cause=e)

    def load_from_cache(self, video_path: FilePath, model_size: str) -> TranscriptionResult | None:
        """
        キャッシュから文字起こし結果を読み込み

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ

        Returns:
            キャッシュされた結果（存在しない場合はNone）
        """
        try:
            # キャッシュパスを取得
            logger.info(f"キャッシュ読み込み開始: video_path={video_path}, model_size={model_size}")
            logger.info(f"Gateway APIモード設定: {self.config.transcription.use_api}")
            cache_path = self._legacy_transcriber.get_cache_path(str(video_path), model_size)
            logger.info(f"キャッシュパス: {cache_path}")
            logger.info(f"キャッシュパス存在確認: {cache_path.exists()}")
            
            # キャッシュが存在しない場合、APIモードのキャッシュも確認
            if not cache_path.exists() and not self.config.transcription.use_api:
                # _apiサフィックス付きのパスを試す
                api_cache_path = cache_path.parent / f"{model_size}_api.json"
                logger.info(f"APIモードキャッシュを確認: {api_cache_path}")
                if api_cache_path.exists():
                    logger.info("APIモードのキャッシュが見つかりました。これを使用します。")
                    cache_path = api_cache_path

            # キャッシュを読み込み
            legacy_result = self._legacy_transcriber.load_from_cache(cache_path)

            if legacy_result is None:
                logger.warning("キャッシュファイルが見つからないか、読み込みに失敗しました")
                return None

            logger.info(f"レガシー結果を読み込みました: {type(legacy_result)}")

            # ドメインエンティティに変換
            domain_result = self._converter.legacy_to_domain(legacy_result)

            logger.info(f"ドメインエンティティに変換しました: {cache_path}")
            return domain_result

        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {e}", exc_info=True)
            logger.error(f"エラーの型: {type(e).__name__}")
            logger.error(f"エラーの詳細: {str(e)}")
            import traceback
            logger.error(f"スタックトレース:\n{traceback.format_exc()}")
            return None

    def save_to_cache(self, video_path: FilePath, model_size: str, result: TranscriptionResult) -> None:
        """
        文字起こし結果をキャッシュに保存

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            result: 文字起こし結果
        """
        try:
            # キャッシュパスを取得
            cache_path = self._legacy_transcriber.get_cache_path(str(video_path), model_size)

            # ドメインエンティティをレガシー辞書形式に変換
            legacy_dict = self._converter.domain_to_legacy_dict(result)

            # レガシーのTranscriptionResultオブジェクトを作成
            from core.transcription import TranscriptionResult as LegacyResult

            legacy_result = LegacyResult.from_dict(legacy_dict)

            # キャッシュに保存
            self._legacy_transcriber.save_to_cache(legacy_result, cache_path)

            logger.info(f"Saved transcription to cache: {cache_path}")

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            # キャッシュ保存の失敗は致命的ではないので、例外は投げない

    def get_video_info(self, video_path: str) -> Any:
        """
        動画情報を取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            動画情報オブジェクト
        """
        try:
            from core.video import VideoInfo

            return VideoInfo.from_file(video_path)
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            raise

    def get_available_caches(self, video_path: str) -> list[dict[str, Any]]:
        """
        利用可能なキャッシュのリストを取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            キャッシュ情報のリスト
        """
        try:
            return self._legacy_transcriber.get_available_caches(video_path)
        except Exception as e:
            logger.error(f"Failed to get available caches: {e}")
            return []

    def is_model_available(self, model_size: str) -> bool:
        """
        指定されたモデルが利用可能かチェック

        Args:
            model_size: モデルサイズ

        Returns:
            利用可能かどうか
        """
        # APIモードの場合は常にTrue
        if self.config.transcription.use_api:
            return True

        # ローカルモードの場合は、サポートされているモデルサイズをチェック
        supported_models = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
        return model_size in supported_models

    def estimate_processing_time(self, video_duration: float, model_size: str) -> float:
        """
        処理時間の推定

        Args:
            video_duration: 動画の長さ（秒）
            model_size: モデルサイズ

        Returns:
            推定処理時間（秒）
        """
        # モデルサイズによる処理速度の係数（概算）
        speed_factors = {
            "tiny": 0.1,
            "base": 0.15,
            "small": 0.2,
            "medium": 0.3,
            "large": 0.5,
            "large-v2": 0.6,
            "large-v3": 0.7,
        }

        factor = speed_factors.get(model_size, 0.5)

        # APIモードの場合は高速
        if self.config.transcription.use_api:
            factor *= 0.3

        return video_duration * factor

    def supports_parallel_processing(self) -> bool:
        """並列処理をサポートしているか"""
        # APIモードまたはGPU使用時は並列処理可能
        if self.config.transcription.use_api:
            return True

        # device属性の確認
        device = getattr(self._legacy_transcriber, "device", "cpu")
        return device == "cuda"

    def transcribe_parallel(
        self,
        video_path: FilePath,
        model_size: str,
        language: str | None = None,
        chunk_duration: float = 600.0,
        num_workers: int = 2,
        progress_callback: Callable[[str], None] | None = None,
    ) -> TranscriptionResult:
        """
        動画を並列で文字起こし
        
        現在は通常のtranscribeメソッドを呼び出します。
        将来的に並列処理を実装予定。
        """
        logger.info("transcribe_parallel called, falling back to regular transcribe")
        return self.transcribe(
            video_path=video_path,
            model_size=model_size,
            language=language,
            progress_callback=lambda p: progress_callback(f"Progress: {p:.0%}") if progress_callback else None,
        )

    def is_api_mode(self) -> bool:
        """APIモードかどうか"""
        return self.config.transcription.use_api

    def get_available_models(self) -> list[str]:
        """利用可能なモデルサイズのリストを取得"""
        if self.config.transcription.use_api:
            # APIモードでは固定のモデル
            return ["whisper-1"]
        else:
            # ローカルモードでサポートされているモデル
            return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]

    def list_available_caches(self, video_path: FilePath) -> list[dict]:
        """
        利用可能なキャッシュの一覧を取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            キャッシュ情報のリスト
        """
        try:
            # get_available_cachesの実装を使用
            return self.get_available_caches(str(video_path))
        except Exception as e:
            logger.error(f"Failed to list available caches: {e}")
            return []
