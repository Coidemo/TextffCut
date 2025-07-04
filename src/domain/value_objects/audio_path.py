"""
AudioPath Value Object

音声ファイルパスを表現する特殊化されたFilePath
"""

from pathlib import Path

from .file_path import FilePath


class AudioPath(FilePath):
    """音声ファイルパスを表現するValue Object"""

    # サポートする音声ファイル拡張子
    SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}

    def __init__(self, path: str | Path | FilePath):
        """
        Args:
            path: 音声ファイルパス

        Raises:
            ValueError: サポートされていない拡張子の場合
        """
        if isinstance(path, FilePath):
            super().__init__(path.value)
        else:
            super().__init__(path)

        # 拡張子の検証
        if self.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {self.suffix}. "
                f"Supported formats: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

    @property
    def is_wav(self) -> bool:
        """WAVファイルかどうか"""
        return self.suffix.lower() == ".wav"

    @property
    def is_mp3(self) -> bool:
        """MP3ファイルかどうか"""
        return self.suffix.lower() == ".mp3"

    def to_wav_path(self) -> "AudioPath":
        """WAVファイルパスに変換（拡張子のみ変更）"""
        return AudioPath(self.with_suffix(".wav"))

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"AudioPath('{self.value}')"
