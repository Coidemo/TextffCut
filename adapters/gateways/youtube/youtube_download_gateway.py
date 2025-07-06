"""
YouTube ダウンロードゲートウェイの実装

yt-dlpを使用してYouTube動画をダウンロードします。
作者の許可を得た動画のみダウンロード可能です。
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp

from domain.value_objects.file_path import FilePath
from use_cases.interfaces.youtube_download_gateway import (
    DownloadProgress,
    IYouTubeDownloadGateway,
    VideoInfo,
)

logger = logging.getLogger(__name__)


class YouTubeDownloadGateway(IYouTubeDownloadGateway):
    """YouTube ダウンロードゲートウェイの実装"""

    def __init__(self, output_dir: Path):
        """
        初期化

        Args:
            output_dir: ダウンロード先ディレクトリ
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._progress_callback: Callable[[DownloadProgress], None] | None = None

    def validate_url(self, url: str) -> bool:
        """
        YouTube URLの妥当性を検証

        Args:
            url: 検証するURL

        Returns:
            有効なYouTube URLかどうか
        """
        patterns = [
            r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://youtu\.be/[\w-]+",
            r"^https?://(?:www\.)?youtube\.com/embed/[\w-]+",
        ]
        return any(re.match(pattern, url) for pattern in patterns)

    def get_video_info(self, url: str) -> VideoInfo:
        """
        動画情報を取得

        Args:
            url: YouTube URL

        Returns:
            動画情報

        Raises:
            ValueError: URLが無効な場合
            RuntimeError: 動画情報の取得に失敗した場合
        """
        if not self.validate_url(url):
            raise ValueError(f"無効なYouTube URL: {url}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            # YouTubeのボット検出を回避するオプション
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ja,en;q=0.9",
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # 最適なフォーマットを選択
                formats = info.get("formats", [])
                best_video = None
                best_audio = None

                for fmt in formats:
                    if fmt.get("vcodec") != "none" and fmt.get("acodec") == "none":
                        # ビデオのみ
                        if not best_video or (fmt.get("height", 0) or 0) > (best_video.get("height", 0) or 0):
                            best_video = fmt
                    elif fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
                        # オーディオのみ
                        if not best_audio or (fmt.get("abr", 0) or 0) > (best_audio.get("abr", 0) or 0):
                            best_audio = fmt

                # ファイルサイズの推定
                estimated_size = 0
                if best_video:
                    video_size = best_video.get("filesize") or 0
                    if not video_size and best_video.get("tbr"):
                        # ビットレートから推定（tbr * duration / 8）
                        video_size = int(best_video["tbr"] * info["duration"] * 1000 / 8)
                    estimated_size += video_size

                if best_audio:
                    audio_size = best_audio.get("filesize") or 0
                    if not audio_size and best_audio.get("abr"):
                        # ビットレートから推定
                        audio_size = int(best_audio["abr"] * info["duration"] * 1000 / 8)
                    estimated_size += audio_size

                # フォールバック：duration から推定（1080p = 約150MB/10分）
                if estimated_size == 0:
                    estimated_size = int(info["duration"] * 2.5 * 1024 * 1024)  # 2.5MB/秒

                return VideoInfo(
                    title=info["title"],
                    duration=info["duration"],
                    uploader=info.get("uploader", "Unknown"),
                    description=info.get("description", ""),
                    thumbnail=info.get("thumbnail", ""),
                    estimated_size=estimated_size,
                    formats=len(formats),
                )

        except Exception as e:
            logger.error(f"動画情報の取得に失敗: {e}")
            error_msg = str(e)
            if "Sign in to confirm" in error_msg:
                raise RuntimeError(
                    "YouTubeがアクセスを制限しています。" "時間をおいて再試行するか、別の動画でお試しください。"
                )
            raise RuntimeError(f"動画情報の取得に失敗しました: {error_msg}")

    def download_video(
        self,
        url: str,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> FilePath:
        """
        動画をダウンロード

        Args:
            url: YouTube URL
            progress_callback: 進捗コールバック関数

        Returns:
            ダウンロードしたファイルのパス

        Raises:
            ValueError: URLが無効な場合
            RuntimeError: ダウンロードに失敗した場合
        """
        if not self.validate_url(url):
            raise ValueError(f"無効なYouTube URL: {url}")

        self._progress_callback = progress_callback

        # ファイル名をサニタイズ
        def sanitize_filename(filename: str) -> str:
            """ファイル名から無効な文字を削除"""
            # Windowsで無効な文字を置換
            invalid_chars = '<>:"|?*'
            for char in invalid_chars:
                filename = filename.replace(char, "_")
            # 先頭・末尾の空白やドットを削除
            filename = filename.strip(". ")
            # 長すぎる場合は切り詰め
            if len(filename) > 200:
                filename = filename[:200]
            return filename

        ydl_opts = {
            # macOSと互換性の高いフォーマットを優先（H.264を強制）
            "format": "bestvideo[vcodec^=avc][height<=1080]+bestaudio[ext=m4a]/bestvideo[vcodec^=h264][height<=1080]+bestaudio/best[vcodec^=avc]/best[vcodec^=h264]/best",
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            # YouTubeのボット検出を回避するオプション
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ja,en;q=0.9",
            },
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ],
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,  # 日本語ファイル名を許可
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                # ダウンロードされたファイルのパスを取得
                filename = ydl.prepare_filename(info)
                # 拡張子をmp4に変更（後処理で変換される場合）
                if not filename.endswith(".mp4"):
                    base = Path(filename).stem
                    filename = str(self.output_dir / f"{base}.mp4")

                output_path = Path(filename)

                if not output_path.exists():
                    # ファイル名がサニタイズされた可能性があるので探す
                    sanitized_title = sanitize_filename(info["title"])
                    possible_path = self.output_dir / f"{sanitized_title}.mp4"
                    if possible_path.exists():
                        output_path = possible_path
                    else:
                        # videosディレクトリ内の最新のmp4ファイルを探す
                        mp4_files = list(self.output_dir.glob("*.mp4"))
                        if mp4_files:
                            output_path = max(mp4_files, key=lambda p: p.stat().st_mtime)
                        else:
                            raise RuntimeError("ダウンロードしたファイルが見つかりません")

                logger.info(f"動画をダウンロードしました: {output_path}")
                return FilePath(str(output_path))

        except Exception as e:
            logger.error(f"ダウンロードに失敗: {e}")
            error_msg = str(e)
            if "Sign in to confirm" in error_msg:
                raise RuntimeError(
                    "YouTubeがアクセスを制限しています。" "時間をおいて再試行するか、別の動画でお試しください。"
                )
            raise RuntimeError(f"ダウンロードに失敗しました: {error_msg}")

    def _progress_hook(self, d: dict[str, Any]) -> None:
        """
        yt-dlpの進捗フック

        Args:
            d: 進捗情報
        """
        if self._progress_callback is None:
            return

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0)
            eta = d.get("eta", 0)

            if total > 0:
                percent = (downloaded / total) * 100
            else:
                percent = 0

            progress = DownloadProgress(
                status="downloading",
                percent=percent,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=speed or 0,
                eta=eta or 0,
            )
            self._progress_callback(progress)

        elif status == "finished":
            progress = DownloadProgress(
                status="finished",
                percent=100,
                downloaded_bytes=d.get("total_bytes", 0),
                total_bytes=d.get("total_bytes", 0),
                speed=0,
                eta=0,
            )
            self._progress_callback(progress)
