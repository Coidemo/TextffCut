"""
カスタム例外クラス
"""

from pathlib import Path
from typing import Any


class BuzzClipError(Exception):
    """Buzz Clipの基本例外クラス"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def get_user_message(self) -> str:
        """ユーザー向けのメッセージを取得"""
        return self.message

    def get_debug_info(self) -> dict[str, Any]:
        """デバッグ情報を取得"""
        return {"error_type": self.__class__.__name__, "message": self.message, "details": self.details}


class TranscriptionError(BuzzClipError):
    """文字起こし関連のエラー"""

    pass


class VideoProcessingError(BuzzClipError):
    """動画処理関連のエラー"""

    pass


class FileNotFoundError(BuzzClipError):
    """ファイルが見つからないエラー"""

    def __init__(self, file_path: str | Path) -> None:
        super().__init__(f"ファイルが見つかりません: {file_path}", {"file_path": file_path})


class FFmpegError(VideoProcessingError):
    """FFmpeg実行エラー"""

    def __init__(self, command: str, error_output: str) -> None:
        super().__init__("動画処理中にエラーが発生しました", {"command": command, "error_output": error_output})

    def get_user_message(self) -> str:
        """ユーザー向けのメッセージ"""
        if "No such file or directory" in self.details.get("error_output", ""):
            return "入力ファイルが見つかりません。ファイルパスを確認してください。"
        elif "Invalid argument" in self.details.get("error_output", ""):
            return "動画の形式がサポートされていません。"
        elif "Cannot allocate memory" in self.details.get("error_output", ""):
            return "メモリ不足です。より小さい動画で試すか、他のアプリケーションを閉じてください。"
        else:
            return f"動画処理中にエラーが発生しました。詳細: {self.details.get('error_output', '')[:200]}"


class WhisperError(TranscriptionError):
    """Whisper関連のエラー"""

    def __init__(self, message: str, model_size: str | None = None) -> None:
        super().__init__(message, {"model_size": model_size})


class MemoryError(BuzzClipError):
    """メモリ不足エラー"""

    def __init__(self, required_memory: float | None = None) -> None:
        message = "メモリが不足しています。"
        if required_memory:
            message += f" 必要なメモリ: {required_memory:.1f}GB"
        super().__init__(message, {"required_memory": required_memory})


class ConfigurationError(BuzzClipError):
    """設定関連のエラー"""

    pass
