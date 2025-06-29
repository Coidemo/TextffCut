"""
文字起こしゲートウェイの実装

既存のTranscriberクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.interfaces import ITranscriptionGateway
from core.transcription import Transcriber as LegacyTranscriber
from adapters.converters.transcription_converter import TranscriptionConverter
from utils.logging import get_logger
from config import Config

logger = get_logger(__name__)


class TranscriptionGatewayAdapter(ITranscriptionGateway):
    """
    文字起こしゲートウェイのアダプター実装
    
    既存のTranscriberクラスをラップし、ドメイン層のインターフェースに適合させます。
    """
    
    def __init__(self, config: Optional[Config] = None):
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
        language: Optional[str] = None,
        use_cache: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
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
            
            # レガシーメソッドを呼び出し
            legacy_result = self._legacy_transcriber.transcribe(
                video_path=legacy_path,
                model_size=model_size,
                # progressパラメータ名の違いに注意
                progress_callback=progress_callback
            )
            
            # 処理時間を計算
            processing_time = time.time() - start_time
            
            # レガシー結果をドメインエンティティに変換
            domain_result = self._converter.legacy_to_domain(
                legacy_result,
                processing_time=processing_time
            )
            
            # 変換の妥当性を検証（デバッグモードのみ）
            # BuzzClipLoggerではisEnabledForが使えないため、環境変数でチェック
            import os
            if os.getenv("DEBUG", "").lower() in ("true", "1", "yes"):
                if not self._converter.validate_conversion(legacy_result, domain_result):
                    logger.warning("Conversion validation failed")
            
            logger.info(
                f"Transcription completed: {len(domain_result.segments)} segments, "
                f"{processing_time:.1f}s"
            )
            
            return domain_result
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            # レガシーエラーをユースケース層の例外に変換
            from use_cases.exceptions import TranscriptionError
            raise TranscriptionError(
                f"Failed to transcribe {video_path}: {str(e)}",
                cause=e
            )
    
    def load_cache(
        self,
        video_path: FilePath,
        model_size: str
    ) -> Optional[TranscriptionResult]:
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
            cache_path = self._legacy_transcriber.get_cache_path(
                str(video_path),
                model_size
            )
            
            # キャッシュを読み込み
            legacy_result = self._legacy_transcriber.load_from_cache(cache_path)
            
            if legacy_result is None:
                return None
            
            # ドメインエンティティに変換
            domain_result = self._converter.legacy_to_domain(legacy_result)
            
            logger.info(f"Loaded transcription from cache: {cache_path}")
            return domain_result
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None
    
    def save_cache(
        self,
        result: TranscriptionResult,
        video_path: FilePath,
        model_size: str
    ) -> None:
        """
        文字起こし結果をキャッシュに保存
        
        Args:
            result: 文字起こし結果
            video_path: 動画ファイルパス
            model_size: モデルサイズ
        """
        try:
            # キャッシュパスを取得
            cache_path = self._legacy_transcriber.get_cache_path(
                str(video_path),
                model_size
            )
            
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
    
    def get_available_caches(self, video_path: str) -> List[Dict[str, Any]]:
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
        supported_models = [
            "tiny", "base", "small", "medium", 
            "large", "large-v2", "large-v3"
        ]
        return model_size in supported_models
    
    def estimate_processing_time(
        self,
        video_duration: float,
        model_size: str
    ) -> float:
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
            "large-v3": 0.7
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
        device = getattr(self._legacy_transcriber, 'device', 'cpu')
        return device == 'cuda'