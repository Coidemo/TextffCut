"""
TextffCut 設定管理モジュール
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class TranscriptionConfig:
    """文字起こし関連の設定"""

    # 基本設定（ユーザーが選択可能）
    model_size: str = "large-v3"
    whisper_models: list[str] = field(default_factory=lambda: ["large-v3", "medium", "small", "base"])
    language: str = "ja"

    # API設定（ユーザーが選択可能）
    use_api: bool = False  # APIを使用するかどうか
    api_provider: str = "openai"  # 固定
    api_key: str | None = None
    api_models: list[str] = field(default_factory=lambda: ["whisper-1"])

    # 固定設定（自動最適化で管理されるため削除対象から除外）
    sample_rate: int = 16000
    compute_type: str = "int8"
    isolation_mode: str = "subprocess"  # 常にサブプロセス分離

    # API用の固定設定
    api_retry_count: int = 3  # APIリトライ回数
    
    # VAD処理設定
    use_vad_processing: bool = True  # VADベースの処理を使用するか（デフォルトで有効）

    # MLX設定（Apple Silicon Mac用）
    use_mlx_whisper: bool = True  # MLXが利用可能なら自動的に使用（フォールバックあり）

    # 以下は全て自動最適化により動的に決定されるため削除
    # chunk_seconds, num_workers, batch_size, max_workers
    # local_align_chunk_seconds, force_separated_mode
    # adaptive_workers関連, chunk_seconds_*_spec
    # api_chunk_seconds, api_max_workers, api_align_chunk_seconds

    def __post_init__(self) -> None:
        # 環境変数からAPI設定を読み込み
        if os.getenv("TEXTFFCUT_USE_API", "").lower() == "true":
            self.use_api = True
        if api_key := os.getenv("TEXTFFCUT_API_KEY"):
            self.api_key = api_key
        # APIプロバイダーはOpenAI固定（環境変数での変更不要）
        
        # VAD処理フラグを環境変数から読み込み（明示的に設定された場合は上書き）
        vad_env = os.getenv("TEXTFFCUT_USE_VAD", "").lower()
        if vad_env == "true":
            self.use_vad_processing = True
        elif vad_env == "false":
            self.use_vad_processing = False

        # MLXフラグを環境変数から読み込み
        mlx_env = os.getenv("TEXTFFCUT_USE_MLX_WHISPER", "").lower()
        if mlx_env == "true":
            self.use_mlx_whisper = True
        elif mlx_env == "false":
            self.use_mlx_whisper = False


@dataclass
class VideoConfig:
    """動画処理関連の設定"""

    supported_formats: list[str] = field(default_factory=lambda: [".mp4", ".mov", ".avi", ".mkv", ".wmv"])
    default_fps: int = 30
    ffmpeg_preset: str = "ultrafast"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    video_codec: str = "libx264"

    # 無音検出のデフォルト値
    default_noise_threshold: float = -35.0
    default_min_silence_duration: float = 0.3
    default_min_segment_duration: float = 0.3
    default_padding_start: float = 0.1  # 開始部分のパディング（秒）
    default_padding_end: float = 0.1  # 終了部分のパディング（秒）


@dataclass
class UIConfig:
    """UI関連の設定"""

    page_title: str = "TextffCut"
    page_icon: str = "🎬"
    layout: Literal["centered", "wide"] = "wide"


@dataclass
class PathConfig:
    """パス関連の設定"""

    base_dir: Path = field(default_factory=lambda: Path.cwd())
    videos_dir: str = "videos"
    output_dir: str = "output"
    transcriptions_dir: str = "transcriptions"

    @property
    def videos_path(self) -> Path:
        return self.base_dir / self.videos_dir

    @property
    def output_path(self) -> Path:
        return self.base_dir / self.output_dir

    @property
    def transcriptions_path(self) -> Path:
        return self.base_dir / self.transcriptions_dir

    def ensure_directories(self) -> None:
        """必要なディレクトリを作成"""
        self.videos_path.mkdir(exist_ok=True)
        self.output_path.mkdir(exist_ok=True)
        self.transcriptions_path.mkdir(exist_ok=True)


@dataclass
class Config:
    """アプリケーション全体の設定"""

    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    paths: PathConfig = field(default_factory=PathConfig)

    def __post_init__(self) -> None:
        self.paths.ensure_directories()

    @classmethod
    def from_env(cls) -> "Config":
        """環境変数から設定を読み込み"""
        config = cls()

        # 環境変数からの読み込み例
        if model_size := os.getenv("TEXTFFCUT_MODEL_SIZE"):
            config.transcription.model_size = model_size

        if output_dir := os.getenv("TEXTFFCUT_OUTPUT_DIR"):
            config.paths.output_dir = output_dir

        return config


# グローバル設定インスタンス
config = Config.from_env()
