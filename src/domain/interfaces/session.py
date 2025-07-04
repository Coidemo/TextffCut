"""
セッション管理のインターフェース
"""

from abc import ABC, abstractmethod

from ..entities import TranscriptionResult, VideoInfo
from ..value_objects import FilePath, TimeRange


class ISessionManager(ABC):
    """セッション状態管理のインターフェース"""

    # 文字起こし関連
    @abstractmethod
    def get_transcription_result(self) -> TranscriptionResult | None:
        """文字起こし結果の取得"""
        pass

    @abstractmethod
    def set_transcription_result(self, result: TranscriptionResult) -> None:
        """文字起こし結果の保存"""
        pass

    # テキスト編集関連
    @abstractmethod
    def get_edited_text(self) -> str | None:
        """編集済みテキストの取得"""
        pass

    @abstractmethod
    def set_edited_text(self, text: str) -> None:
        """編集済みテキストの保存"""
        pass

    # 動画情報関連
    @abstractmethod
    def get_video_path(self) -> FilePath | None:
        """動画パスの取得"""
        pass

    @abstractmethod
    def set_video_path(self, path: FilePath) -> None:
        """動画パスの保存"""
        pass

    @abstractmethod
    def get_video_info(self) -> VideoInfo | None:
        """動画情報の取得"""
        pass

    @abstractmethod
    def set_video_info(self, info: VideoInfo) -> None:
        """動画情報の保存"""
        pass

    # 時間範囲関連
    @abstractmethod
    def get_time_ranges(self) -> list[TimeRange] | None:
        """時間範囲リストの取得"""
        pass

    @abstractmethod
    def set_time_ranges(self, ranges: list[TimeRange]) -> None:
        """時間範囲リストの保存"""
        pass

    @abstractmethod
    def get_adjusted_time_ranges(self) -> list[TimeRange] | None:
        """調整済み時間範囲リストの取得"""
        pass

    @abstractmethod
    def set_adjusted_time_ranges(self, ranges: list[TimeRange]) -> None:
        """調整済み時間範囲リストの保存"""
        pass

    # エクスポート設定関連
    @abstractmethod
    def get_export_settings(self) -> dict | None:
        """エクスポート設定の取得"""
        pass

    @abstractmethod
    def set_export_settings(self, settings: dict) -> None:
        """エクスポート設定の保存"""
        pass

    # 無音検出設定関連
    @abstractmethod
    def get_silence_threshold(self) -> float:
        """無音閾値の取得"""
        pass

    @abstractmethod
    def set_silence_threshold(self, threshold: float) -> None:
        """無音閾値の保存"""
        pass

    @abstractmethod
    def get_min_silence_duration(self) -> float:
        """最小無音時間の取得"""
        pass

    @abstractmethod
    def set_min_silence_duration(self, duration: float) -> None:
        """最小無音時間の保存"""
        pass

    # 管理操作
    @abstractmethod
    def clear_all(self) -> None:
        """すべてのセッションデータをクリア"""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """キーの存在確認"""
        pass
