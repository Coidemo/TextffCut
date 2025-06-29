"""
TextffCut 2段階処理アーキテクチャ用インターフェース定義

このモジュールは、文字起こしとアライメントの処理を
統一的に扱うためのインターフェースを定義します。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import (
    CacheEntry,
    ProcessingRequest,
    TranscriptionResultV2,
    TranscriptionSegmentV2,
)


class ITranscriptionProcessor(ABC):
    """文字起こし処理のインターフェース"""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str | Path,
        language: str,
        model_size: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> list[TranscriptionSegmentV2]:
        """
        音声ファイルから文字起こしを実行

        Args:
            audio_path: 音声ファイルのパス
            language: 言語コード（例: "ja"）
            model_size: モデルサイズ
            progress_callback: 進捗報告用コールバック

        Returns:
            文字起こしセグメントのリスト（アライメント情報なし）

        Raises:
            TranscriptionError: 文字起こしに失敗した場合
        """
        pass

    @abstractmethod
    def validate_requirements(self) -> bool:
        """
        処理に必要な要件（モデル、メモリなど）を検証

        Returns:
            要件を満たしている場合True
        """
        pass

    @abstractmethod
    def get_estimated_memory_usage(self, duration_seconds: float) -> float:
        """
        推定メモリ使用量を取得（MB）

        Args:
            duration_seconds: 音声の長さ（秒）

        Returns:
            推定メモリ使用量（MB）
        """
        pass


class IAlignmentProcessor(ABC):
    """アライメント処理のインターフェース"""

    @abstractmethod
    def align(
        self,
        segments: list[TranscriptionSegmentV2],
        audio_path: str | Path,
        language: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> list[TranscriptionSegmentV2]:
        """
        文字起こしセグメントに対してアライメントを実行

        Args:
            segments: アライメント前のセグメント
            audio_path: 音声ファイルのパス
            language: 言語コード
            progress_callback: 進捗報告用コールバック

        Returns:
            アライメント済みセグメントのリスト

        Raises:
            AlignmentError: アライメントに失敗した場合
        """
        pass

    @abstractmethod
    def align_single_segment(
        self, segment: TranscriptionSegmentV2, audio_data: Any, language: str
    ) -> TranscriptionSegmentV2:
        """
        単一セグメントのアライメントを実行

        Args:
            segment: アライメント前のセグメント
            audio_data: 音声データ（numpy配列など）
            language: 言語コード

        Returns:
            アライメント済みセグメント
        """
        pass

    @abstractmethod
    def estimate_timestamps(self, text: str, start_time: float, end_time: float) -> list[dict[str, Any]]:
        """
        タイムスタンプが取得できない場合の推定処理

        Args:
            text: テキスト
            start_time: 開始時刻
            end_time: 終了時刻

        Returns:
            推定されたword情報のリスト
        """
        pass


class ICacheManager(ABC):
    """キャッシュ管理のインターフェース"""

    @abstractmethod
    def get_cache_key(self, video_path: str | Path, model_size: str, processing_mode: str, stage: str) -> str:
        """
        キャッシュキーを生成

        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ
            processing_mode: 処理モード（api/local）
            stage: 処理段階（transcription/alignment/complete）

        Returns:
            キャッシュキー
        """
        pass

    @abstractmethod
    def save_transcription_cache(
        self, cache_key: str, segments: list[TranscriptionSegmentV2], metadata: dict[str, Any]
    ) -> bool:
        """
        文字起こし結果をキャッシュに保存

        Args:
            cache_key: キャッシュキー
            segments: 文字起こしセグメント
            metadata: メタデータ

        Returns:
            保存に成功した場合True
        """
        pass

    @abstractmethod
    def save_alignment_cache(
        self, cache_key: str, segments: list[TranscriptionSegmentV2], metadata: dict[str, Any]
    ) -> bool:
        """
        アライメント結果をキャッシュに保存

        Args:
            cache_key: キャッシュキー
            segments: アライメント済みセグメント
            metadata: メタデータ

        Returns:
            保存に成功した場合True
        """
        pass

    @abstractmethod
    def load_cache(self, cache_key: str) -> TranscriptionResultV2 | None:
        """
        キャッシュから結果を読み込み

        Args:
            cache_key: キャッシュキー

        Returns:
            キャッシュされた結果、存在しない場合None
        """
        pass

    @abstractmethod
    def list_caches(self, video_path: str | Path) -> list[CacheEntry]:
        """
        指定された動画のキャッシュ一覧を取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            キャッシュエントリのリスト
        """
        pass

    @abstractmethod
    def clean_old_caches(self, max_age_days: int = 30) -> int:
        """
        古いキャッシュをクリーンアップ

        Args:
            max_age_days: 保持する最大日数

        Returns:
            削除されたキャッシュ数
        """
        pass


class IProgressReporter(ABC):
    """進捗報告のインターフェース"""

    @abstractmethod
    def report_progress(self, stage: str, current: float, total: float, message: str) -> None:
        """
        進捗を報告

        Args:
            stage: 処理段階
            current: 現在の進捗
            total: 全体の進捗
            message: メッセージ
        """
        pass

    @abstractmethod
    def report_error(self, stage: str, error: Exception, recoverable: bool = False) -> None:
        """
        エラーを報告

        Args:
            stage: 処理段階
            error: エラー
            recoverable: 回復可能なエラーかどうか
        """
        pass

    @abstractmethod
    def report_warning(self, stage: str, warning: str, details: dict[str, Any] | None = None) -> None:
        """
        警告を報告

        Args:
            stage: 処理段階
            warning: 警告メッセージ
            details: 詳細情報
        """
        pass


class ISubprocessWorker(ABC):
    """サブプロセスワーカーのインターフェース"""

    @abstractmethod
    def execute_in_subprocess(
        self, task_type: str, config: dict[str, Any], timeout: int | None = None
    ) -> dict[str, Any]:
        """
        サブプロセスでタスクを実行

        Args:
            task_type: タスクタイプ（transcribe/align）
            config: タスク設定
            timeout: タイムアウト（秒）

        Returns:
            実行結果

        Raises:
            SubprocessError: サブプロセス実行エラー
        """
        pass

    @abstractmethod
    def is_worker_available(self) -> bool:
        """
        ワーカーが利用可能かチェック

        Returns:
            利用可能な場合True
        """
        pass

    @abstractmethod
    def get_worker_status(self) -> dict[str, Any]:
        """
        ワーカーの状態を取得

        Returns:
            状態情報（メモリ使用量、実行中タスクなど）
        """
        pass


class IUnifiedTranscriber(ABC):
    """統一文字起こしインターフェース（メインオーケストレーター）"""

    @abstractmethod
    def process(self, request: ProcessingRequest) -> TranscriptionResultV2:
        """
        文字起こしとアライメントの統合処理を実行

        Args:
            request: 処理リクエスト

        Returns:
            処理結果

        Raises:
            ProcessingError: 処理エラー
        """
        pass

    @abstractmethod
    def process_with_retry(self, request: ProcessingRequest, max_retries: int = 3) -> TranscriptionResultV2:
        """
        リトライ機能付きで処理を実行

        Args:
            request: 処理リクエスト
            max_retries: 最大リトライ回数

        Returns:
            処理結果
        """
        pass

    @abstractmethod
    def validate_result(self, result: TranscriptionResultV2) -> bool:
        """
        処理結果を検証

        Args:
            result: 処理結果

        Returns:
            有効な結果の場合True
        """
        pass

    @abstractmethod
    def get_available_caches(self, video_path: str | Path) -> list[dict[str, Any]]:
        """
        利用可能なキャッシュのリストを取得

        Args:
            video_path: 動画ファイルパス

        Returns:
            キャッシュ情報のリスト
        """
        pass
