"""
共通型定義モジュール

プロジェクト全体で使用される型定義を集約。
型の一貫性とIDEサポートの向上を目的とする。
"""

from typing import (
    TypedDict, Literal, Union, Protocol, Callable,
    Dict, List, Optional, Any, Tuple, Type
)
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


# ============================================================================
# 基本型エイリアス
# ============================================================================

# パス関連
VideoPath = Union[str, Path]
AudioPath = Union[str, Path]
FilePath = Union[str, Path]
DirectoryPath = Union[str, Path]

# 時間関連
TimeSeconds = float
TimeMilliseconds = int
FrameNumber = int
FrameRate = float

# サイズ関連
ByteSize = int
Percentage = float  # 0.0 - 100.0


# ============================================================================
# リテラル型定義
# ============================================================================

# ファイルフォーマット
VideoFormat = Literal['mp4', 'mov', 'avi', 'mkv', 'webm']
AudioFormat = Literal['wav', 'mp3', 'aac', 'm4a', 'flac']
ExportFormat = Literal['fcpxml', 'xmeml', 'edl', 'json', 'srt', 'vtt']

# モデル関連
ModelSize = Literal['base', 'small', 'medium', 'large', 'large-v2', 'large-v3', 'whisper-1']
ComputeType = Literal['int8', 'int16', 'float16', 'float32']
ProcessingMode = Literal['api', 'local', 'hybrid']

# 言語コード（主要なもの）
LanguageCode = Literal[
    'ja', 'en', 'zh', 'ko', 'es', 'fr', 'de', 'it', 'pt', 'ru',
    'ar', 'hi', 'th', 'vi', 'id', 'tr', 'pl', 'nl', 'sv', 'da'
]

# 処理状態
ProcessingStatus = Literal['pending', 'in_progress', 'completed', 'failed', 'cancelled']
AlignmentStatus = Literal['pending', 'aligned', 'failed', 'skipped']


# ============================================================================
# TypedDict定義（辞書の型安全性）
# ============================================================================

class VideoMetadata(TypedDict):
    """動画メタデータ"""
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    bitrate: Optional[int]
    audio_codec: Optional[str]
    audio_sample_rate: Optional[int]
    audio_channels: Optional[int]


class TranscriptionOptions(TypedDict, total=False):
    """文字起こしオプション"""
    language: Optional[LanguageCode]
    model_size: ModelSize
    compute_type: ComputeType
    batch_size: int
    beam_size: int
    best_of: int
    temperature: float
    compression_ratio_threshold: float
    log_prob_threshold: float
    no_speech_threshold: float
    condition_on_previous_text: bool
    initial_prompt: Optional[str]
    suppress_tokens: Optional[List[int]]
    without_timestamps: bool


class SilenceDetectionOptions(TypedDict, total=False):
    """無音検出オプション"""
    threshold_db: float
    min_silence_duration: float
    min_segment_duration: float
    pad_start: float
    pad_end: float


class ExportOptions(TypedDict, total=False):
    """エクスポートオプション"""
    format: ExportFormat
    project_name: Optional[str]
    event_name: Optional[str]
    include_metadata: bool
    custom_metadata: Optional[Dict[str, Any]]


class TimeRange(TypedDict):
    """時間範囲"""
    start: TimeSeconds
    end: TimeSeconds


class WordInfo(TypedDict):
    """単語情報"""
    word: str
    start: TimeSeconds
    end: TimeSeconds
    confidence: Optional[float]


class SegmentDict(TypedDict):
    """セグメント情報（辞書形式）"""
    id: str
    text: str
    start: TimeSeconds
    end: TimeSeconds
    words: Optional[List[WordInfo]]
    confidence: Optional[float]
    language: Optional[str]
    speaker: Optional[str]


# ============================================================================
# Protocol定義（構造的サブタイピング）
# ============================================================================

class ProgressCallback(Protocol):
    """進捗通知コールバック"""
    def __call__(self, progress: float, message: str) -> None:
        """
        Args:
            progress: 進捗率（0.0-1.0）
            message: 進捗メッセージ
        """
        ...


class ErrorCallback(Protocol):
    """エラー通知コールバック"""
    def __call__(self, error: Exception, context: str) -> None:
        """
        Args:
            error: 発生したエラー
            context: エラーコンテキスト
        """
        ...


class LogCallback(Protocol):
    """ログ出力コールバック"""
    def __call__(self, level: str, message: str, **kwargs: Any) -> None:
        """
        Args:
            level: ログレベル
            message: ログメッセージ
            **kwargs: 追加情報
        """
        ...


class Transcriber(Protocol):
    """文字起こしインターフェース"""
    def transcribe(
        self,
        audio_path: AudioPath,
        language: Optional[LanguageCode] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> List[SegmentDict]:
        """文字起こしを実行"""
        ...


class VideoProcessor(Protocol):
    """動画処理インターフェース"""
    def extract_audio(self, video_path: VideoPath) -> AudioPath:
        """音声を抽出"""
        ...
    
    def get_metadata(self, video_path: VideoPath) -> VideoMetadata:
        """メタデータを取得"""
        ...


# ============================================================================
# 複合型定義
# ============================================================================

# 結果型
TranscriptionResult = Union[List[SegmentDict], Dict[str, Any]]
ProcessingResult = Union[Dict[str, Any], None]
ValidationResult = Tuple[bool, Optional[str]]

# コールバック型
AnyCallback = Union[ProgressCallback, ErrorCallback, LogCallback, None]

# 設定型
ConfigValue = Union[str, int, float, bool, List[Any], Dict[str, Any], None]
ConfigDict = Dict[str, ConfigValue]

# エラー型
ErrorDetails = Dict[str, Any]
ErrorInfo = TypedDict('ErrorInfo', {
    'error_code': str,
    'message': str,
    'details': Optional[ErrorDetails],
    'timestamp': datetime
})


# ============================================================================
# ジェネリック型定義
# ============================================================================

@dataclass
class Result[T]:
    """汎用結果型"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Page[T]:
    """ページネーション用型"""
    items: List[T]
    total: int
    page: int
    page_size: int
    
    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total
    
    @property
    def has_prev(self) -> bool:
        return self.page > 1


# ============================================================================
# 型ガード関数
# ============================================================================

def is_video_format(ext: str) -> bool:
    """動画フォーマットかチェック"""
    return ext.lower().lstrip('.') in ['mp4', 'mov', 'avi', 'mkv', 'webm']


def is_audio_format(ext: str) -> bool:
    """音声フォーマットかチェック"""
    return ext.lower().lstrip('.') in ['wav', 'mp3', 'aac', 'm4a', 'flac']


def is_valid_language(code: str) -> bool:
    """有効な言語コードかチェック"""
    valid_codes = [
        'ja', 'en', 'zh', 'ko', 'es', 'fr', 'de', 'it', 'pt', 'ru',
        'ar', 'hi', 'th', 'vi', 'id', 'tr', 'pl', 'nl', 'sv', 'da'
    ]
    return code in valid_codes


# ============================================================================
# 型変換関数
# ============================================================================

def to_path(path: Union[str, Path]) -> Path:
    """パスオブジェクトに変換"""
    return Path(path) if isinstance(path, str) else path


def to_seconds(ms: TimeMilliseconds) -> TimeSeconds:
    """ミリ秒を秒に変換"""
    return ms / 1000.0


def to_milliseconds(sec: TimeSeconds) -> TimeMilliseconds:
    """秒をミリ秒に変換"""
    return int(sec * 1000)