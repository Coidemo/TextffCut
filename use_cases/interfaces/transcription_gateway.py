"""
文字起こしゲートウェイインターフェース
"""

from collections.abc import Callable
from typing import Protocol

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath


class ITranscriptionGateway(Protocol):
    """文字起こし機能へのゲートウェイ"""

    def transcribe(
        self,
        video_path: FilePath,
        model_size: str,
        language: str | None = None,
        use_cache: bool = True,
        skip_alignment: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> TranscriptionResult:
        """
        動画を文字起こし

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ（tiny, base, small, medium, large等）
            language: 言語コード（Noneの場合は自動検出）
            use_cache: キャッシュを使用するか
            skip_alignment: アライメント処理をスキップするか
            progress_callback: 進捗通知用コールバック

        Returns:
            文字起こし結果

        Raises:
            TranscriptionError: 文字起こし失敗
        """
        ...

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

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            language: 言語コード
            chunk_duration: チャンクの長さ（秒）
            num_workers: ワーカー数
            progress_callback: 進捗通知用コールバック

        Returns:
            文字起こし結果

        Raises:
            TranscriptionError: 文字起こし失敗
        """
        ...

    def load_from_cache(self, video_path: FilePath, model_size: str) -> TranscriptionResult | None:
        """
        キャッシュから文字起こし結果を読み込み

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ

        Returns:
            キャッシュされた結果（なければNone）
        """
        ...

    def save_to_cache(self, video_path: FilePath, model_size: str, result: TranscriptionResult) -> None:
        """
        文字起こし結果をキャッシュに保存

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            result: 保存する結果
        """
        ...

    def list_available_caches(self, video_path: FilePath) -> list[dict]:
        """
        利用可能なキャッシュの一覧を取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            キャッシュ情報のリスト（パス、モデル、更新日時等）
        """
        ...

    def is_api_mode(self) -> bool:
        """APIモードかどうか"""
        ...

    def get_available_models(self) -> list[str]:
        """利用可能なモデルサイズのリストを取得"""
        ...
