"""
TextffCut 設定管理モジュール
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class TranscriptionConfig:
    """文字起こし関連の設定"""
    model_size: str = "large-v3"
    whisper_models: List[str] = field(default_factory=lambda: ["large-v3", "medium", "small", "base"])
    chunk_seconds: int = 30
    sample_rate: int = 16000
    num_workers: Optional[int] = None  # Noneの場合は自動計算
    batch_size: int = 16
    language: str = "ja"
    compute_type: str = "int8"
    
    # API設定（OpenAI専用）
    use_api: bool = False  # APIを使用するかどうか
    api_provider: str = "openai"  # 固定
    api_key: Optional[str] = None
    api_models: List[str] = field(default_factory=lambda: ["whisper-1"])
    
    def __post_init__(self):
        if self.num_workers is None:
            self.num_workers = os.cpu_count() // 2 or 4
        
        # 環境変数からAPI設定を読み込み
        if os.getenv('TEXTFFCUT_USE_API', '').lower() == 'true':
            self.use_api = True
        if api_key := os.getenv('TEXTFFCUT_API_KEY'):
            self.api_key = api_key
        # APIプロバイダーはOpenAI固定（環境変数での変更不要）


@dataclass
class VideoConfig:
    """動画処理関連の設定"""
    supported_formats: List[str] = field(default_factory=lambda: ['.mp4', '.mov', '.avi', '.mkv', '.wmv'])
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
    default_padding_end: float = 0.1    # 終了部分のパディング（秒）


@dataclass
class UIConfig:
    """UI関連の設定"""
    page_title: str = "TextffCut"
    page_icon: str = "🎬"
    layout: str = "wide"


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
    
    def ensure_directories(self):
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
    
    def __post_init__(self):
        self.paths.ensure_directories()
    
    @classmethod
    def from_env(cls) -> 'Config':
        """環境変数から設定を読み込み"""
        config = cls()
        
        # 環境変数からの読み込み例
        if model_size := os.getenv('TEXTFFCUT_MODEL_SIZE'):
            config.transcription.model_size = model_size
        
        if output_dir := os.getenv('TEXTFFCUT_OUTPUT_DIR'):
            config.paths.output_dir = output_dir
            
        return config


# グローバル設定インスタンス
config = Config.from_env()