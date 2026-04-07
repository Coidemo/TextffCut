"""メディア素材（フレーム画像・BGM・効果音）の自動検出ユーティリティ。

overlaysフォルダからメディア素材を検出し、FCPXMLExporter.export()に渡す設定を生成する。
CLI/GUI両方で共通利用する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MediaAssetConfig:
    overlay_settings: dict | None = None
    bgm_settings: dict | None = None
    additional_audio_settings: dict | None = None

    @property
    def has_any(self) -> bool:
        return any([self.overlay_settings, self.bgm_settings, self.additional_audio_settings])

    def summary(self) -> str:
        """CLIやログ用のサマリー文字列を返す。"""
        parts: list[str] = []
        if self.overlay_settings:
            name = Path(self.overlay_settings["frame_path"]).name
            parts.append(f"フレーム: {name}")
        if self.bgm_settings:
            name = Path(self.bgm_settings["bgm_path"]).name
            parts.append(f"BGM: {name}")
        if self.additional_audio_settings:
            n = len(self.additional_audio_settings["audio_files"])
            parts.append(f"効果音: {n}個")
        if not parts:
            return "メディア素材: なし"
        return "メディア素材: " + " | ".join(parts)


def detect_media_assets(
    video_path: Path,
    asset_dir: Path | None = None,
    *,
    enable_frame: bool = True,
    enable_bgm: bool = True,
    enable_se: bool = True,
) -> MediaAssetConfig:
    """動画パスからoverlaysフォルダを自動検出し、設定を返す。

    Args:
        video_path: 動画ファイルのパス
        asset_dir: メディア素材のディレクトリ（Noneなら video_path.parent / "overlays"）
        enable_frame: フレーム画像を含めるか
        enable_bgm: BGMを含めるか
        enable_se: 効果音を含めるか

    Returns:
        MediaAssetConfig: FCPXMLExporter.export()に渡せる設定
    """
    config = MediaAssetConfig()

    overlay_dir = asset_dir if asset_dir else video_path.parent / "overlays"
    if not overlay_dir.exists():
        return config

    # フレーム画像
    if enable_frame:
        frame_path = overlay_dir / "frame.png"
        if frame_path.exists():
            config.overlay_settings = {"frame_path": str(frame_path)}
            logger.info(f"フレーム画像検出: {frame_path}")

    # BGM
    if enable_bgm:
        bgm_path = overlay_dir / "bgm.mp3"
        if bgm_path.exists():
            config.bgm_settings = {
                "bgm_path": str(bgm_path),
                "bgm_volume": -25,
                "bgm_loop": True,
            }
            logger.info(f"BGM検出: {bgm_path}")

    # 効果音（bgm.mp3以外のMP3ファイル）
    if enable_se:
        mp3_files = sorted(
            (f for f in overlay_dir.iterdir() if f.suffix.lower() == ".mp3" and f.name != "bgm.mp3"),
            key=lambda x: x.name,
        )
        if mp3_files:
            config.additional_audio_settings = {
                "audio_files": [str(f) for f in mp3_files],
                "volume": -20,
                "muted": False,
            }
            logger.info(f"効果音検出: {len(mp3_files)}個")

    return config
