"""
Gateway インターフェース定義

Infrastructure層が実装すべきインターフェース
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..entities import Clip, Subtitle, TextDifference, TranscriptionResult, TranscriptionSegment, VideoInfo
from ..value_objects import FilePath, TimeRange


class IFileGateway(ABC):
    """ファイルシステムアクセスのインターフェース"""

    @abstractmethod
    def exists(self, path: FilePath) -> bool:
        """ファイルの存在確認"""
        pass

    @abstractmethod
    def read(self, path: FilePath) -> bytes:
        """ファイルの読み込み"""
        pass

    @abstractmethod
    def write(self, path: FilePath, content: bytes) -> None:
        """ファイルの書き込み"""
        pass

    @abstractmethod
    def delete(self, path: FilePath) -> None:
        """ファイルの削除"""
        pass

    @abstractmethod
    def list_files(self, directory: FilePath, pattern: str = "*") -> list[FilePath]:
        """ディレクトリ内のファイル一覧取得"""
        pass


class ITranscriptionGateway(ABC):
    """文字起こしAPIのインターフェース"""

    @abstractmethod
    def transcribe(
        self,
        audio_path: FilePath,
        model_size: str = "large-v2",
        language: str = "ja",
        progress_callback: Callable[[str], None] | None = None,
    ) -> TranscriptionResult:
        """音声ファイルの文字起こし"""
        pass


class IVideoGateway(ABC):
    """動画処理のインターフェース"""

    @abstractmethod
    def get_video_info(self, video_path: FilePath) -> VideoInfo:
        """動画情報の取得"""
        pass

    @abstractmethod
    def extract_audio(self, video_path: FilePath, output_path: FilePath | None = None) -> FilePath:
        """動画から音声を抽出"""
        pass

    @abstractmethod
    def extract_clip(self, video_path: FilePath, time_range: TimeRange, output_path: FilePath) -> None:
        """動画の一部を切り出し"""
        pass

    @abstractmethod
    def concat_clips(self, clip_paths: list[FilePath], output_path: FilePath) -> None:
        """複数の動画を結合"""
        pass


class ISilenceDetectionGateway(ABC):
    """無音検出のインターフェース"""

    @abstractmethod
    def detect_silence(
        self,
        audio_path: FilePath,
        threshold: float = -35.0,
        min_silence_duration: float = 0.3,
        min_segment_duration: float = 0.3,
    ) -> list[TimeRange]:
        """無音区間の検出（返り値は音声がある区間）"""
        pass


class ITextProcessorGateway(ABC):
    """テキスト処理のインターフェース"""

    @abstractmethod
    def find_differences(
        self, original: str, edited: str, segments: list[TranscriptionSegment]
    ) -> list[TextDifference]:
        """テキストの差分検出"""
        pass


class IExportGateway(ABC):
    """エクスポート処理の基底インターフェース"""

    pass


class IFCPXMLExportGateway(IExportGateway):
    """FCPXMLエクスポートのインターフェース"""

    @abstractmethod
    def export(
        self, clips: list[Clip], video_info: VideoInfo, output_path: FilePath, project_name: str = "TextffCut Project"
    ) -> None:
        """FCPXML形式でエクスポート"""
        pass


class IEDLExportGateway(IExportGateway):
    """EDLエクスポートのインターフェース"""

    @abstractmethod
    def export(
        self, clips: list[Clip], output_path: FilePath, fps: float = 29.97, title: str = "TextffCut EDL"
    ) -> None:
        """EDL形式でエクスポート"""
        pass


class ISRTExportGateway(IExportGateway):
    """SRTエクスポートのインターフェース"""

    @abstractmethod
    def export(self, subtitles: list[Subtitle], output_path: FilePath) -> None:
        """SRT形式でエクスポート"""
        pass
