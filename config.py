<<<<<<< Updated upstream
from dataclasses import dataclass, field
from typing import List, Dict, Any
from pathlib import Path

@dataclass
class AppConfig:
    """アプリケーションの設定を管理するクラス"""
    
    # デフォルトの設定値
    default_noise_threshold: float = -35
    default_min_silence_duration: float = 0.3
    default_min_segment_duration: float = 0.3
    default_timeline_fps: int = 30
    
    # サポートされている動画形式
    supported_video_formats: List[str] = field(default_factory=lambda: ['.mp4', '.mov', '.avi', '.mkv', '.wmv'])
    
    # Whisperモデルの設定
    whisper_models: List[str] = field(default_factory=lambda: ["large-v3", "medium", "small", "base"])
    
    # パス設定
    input_dir: Path = Path("videos")
    output_dir: Path = Path("output")
    transcriptions_dir: Path = Path("transcriptions")
    
    # FFmpeg設定
    ffmpeg_preset: str = "ultrafast"
    ffmpeg_audio_bitrate: str = "192k"
    
    def __post_init__(self):
        """初期化後の処理"""
        # ディレクトリの作成
        self.input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.transcriptions_dir.mkdir(exist_ok=True)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'AppConfig':
        """辞書から設定を生成"""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """設定を辞書に変換"""
        return {
            'default_noise_threshold': self.default_noise_threshold,
            'default_min_silence_duration': self.default_min_silence_duration,
            'default_min_segment_duration': self.default_min_segment_duration,
            'default_timeline_fps': self.default_timeline_fps,
            'supported_video_formats': self.supported_video_formats,
            'whisper_models': self.whisper_models,
            'input_dir': str(self.input_dir),
            'output_dir': str(self.output_dir),
            'transcriptions_dir': str(self.transcriptions_dir),
            'ffmpeg_preset': self.ffmpeg_preset,
            'ffmpeg_audio_bitrate': self.ffmpeg_audio_bitrate
        }

# グローバルな設定インスタンス
config = AppConfig() 
=======
"""
Buzz Clip 設定管理モジュール
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
    
    def __post_init__(self):
        if self.num_workers is None:
            self.num_workers = os.cpu_count() // 2 or 4


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


@dataclass
class UIConfig:
    """UI関連の設定"""
    page_title: str = "Buzz Clip - 文字起こし"
    page_icon: str = "🎙️"
    layout: str = "wide"
    chars_per_line: int = 20
    max_subtitle_lines: int = 2


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
        if model_size := os.getenv('BUZZ_CLIP_MODEL_SIZE'):
            config.transcription.model_size = model_size
        
        if output_dir := os.getenv('BUZZ_CLIP_OUTPUT_DIR'):
            config.paths.output_dir = output_dir
            
        return config


# グローバル設定インスタンス
config = Config.from_env()
>>>>>>> Stashed changes
