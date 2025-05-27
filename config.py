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