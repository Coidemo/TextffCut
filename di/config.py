"""
DI用設定モジュール

DIコンテナの設定と、既存のConfigクラスとの統合を管理します。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import Config as LegacyConfig


@dataclass
class DIConfig:
    """
    DI用の設定クラス

    既存のConfigクラスをラップし、DI固有の設定を追加します。
    """

    # 既存のConfig
    legacy_config: LegacyConfig = field(default_factory=LegacyConfig.from_env)

    # DI固有の設定
    container_config: dict[str, Any] = field(default_factory=dict)

    # 環境設定
    environment: str = field(default_factory=lambda: os.getenv("TEXTFFCUT_ENV", "production"))
    is_testing: bool = field(default_factory=lambda: os.getenv("TESTING", "").lower() == "true")

    # パス設定
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    def __post_init__(self):
        """初期化後の処理"""
        # コンテナ設定のデフォルト値
        self.container_config.setdefault("auto_wire", True)
        self.container_config.setdefault("strict_mode", self.is_testing)

    @property
    def is_development(self) -> bool:
        """開発環境かどうか"""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """本番環境かどうか"""
        return self.environment == "production"

    def get_legacy_config(self) -> LegacyConfig:
        """既存のConfigインスタンスを取得"""
        return self.legacy_config

    def update_from_streamlit_session(self, session_state: dict[str, Any]) -> None:
        """
        Streamlitのセッション状態から設定を更新

        Args:
            session_state: st.session_state の辞書
        """
        # APIキーの更新
        if "api_key" in session_state:
            self.legacy_config.transcription.api_key = session_state["api_key"]

        # モデルサイズの更新
        if "model_size" in session_state:
            self.legacy_config.transcription.model_size = session_state["model_size"]

        # API使用フラグの更新
        if "use_api" in session_state:
            self.legacy_config.transcription.use_api = session_state["use_api"]

    def to_dict(self) -> dict[str, Any]:
        """設定を辞書形式で取得（シリアライズ用）"""
        return {
            "environment": self.environment,
            "is_testing": self.is_testing,
            "container_config": self.container_config,
            "legacy_config": {
                "model_size": self.legacy_config.transcription.model_size,
                "use_api": self.legacy_config.transcription.use_api,
                "api_key": self.legacy_config.transcription.api_key or "",
                "silence_threshold": getattr(self.legacy_config.video, "silence_threshold", -35.0),
                "min_silence_duration": self.legacy_config.video.default_min_silence_duration,
                "min_segment_duration": getattr(self.legacy_config.video, "min_segment_duration", 0.3),
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DIConfig":
        """辞書から設定を復元（デシリアライズ用）"""
        # 既存のConfigを復元
        legacy_config = LegacyConfig()
        if "legacy_config" in data:
            legacy_data = data["legacy_config"]
            # 階層的な設定を復元
            if "model_size" in legacy_data:
                legacy_config.transcription.model_size = legacy_data["model_size"]
            if "silence_threshold" in legacy_data:
                legacy_config.video.silence_threshold = legacy_data["silence_threshold"]
            if "min_silence_duration" in legacy_data:
                legacy_config.video.default_min_silence_duration = legacy_data["min_silence_duration"]
            if "min_segment_duration" in legacy_data:
                legacy_config.video.min_segment_duration = legacy_data["min_segment_duration"]
            # APIモード関連の設定
            if "api_key" in legacy_data:
                legacy_config.transcription.api_key = legacy_data["api_key"]
            if "use_api" in legacy_data:
                legacy_config.transcription.use_api = legacy_data["use_api"]

        return cls(
            legacy_config=legacy_config,
            container_config=data.get("container_config", {}),
            environment=data.get("environment", "production"),
            is_testing=data.get("is_testing", False),
        )
