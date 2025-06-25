"""
TextffCut 2段階処理アーキテクチャ用例外クラス

処理の各段階で発生する可能性のあるエラーを
明確に分類・管理するための例外クラス定義。
"""

from typing import Any

from utils.exceptions import BuzzClipError


class ProcessingError(BuzzClipError):
    """処理全般のエラー基底クラス"""

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
        recoverable: bool = False,
    ):
        """
        Args:
            message: エラーメッセージ
            stage: エラーが発生した処理段階
            details: 詳細情報
            recoverable: 回復可能なエラーかどうか
        """
        super().__init__(message)
        self.stage = stage
        self.details = details or {}
        self.recoverable = recoverable

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        base_message = super().get_user_message()
        if self.stage:
            return f"[{self.stage}] {base_message}"
        return base_message


class TranscriptionValidationError(ProcessingError):
    """文字起こし結果の検証エラー"""

    def __init__(
        self, message: str, missing_fields: list[str] | None = None, invalid_segments: list[str] | None = None
    ):
        """
        Args:
            message: エラーメッセージ
            missing_fields: 欠落しているフィールド
            invalid_segments: 無効なセグメントID
        """
        details = {"missing_fields": missing_fields or [], "invalid_segments": invalid_segments or []}
        super().__init__(message, stage="validation", details=details, recoverable=False)

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        messages = ["⚠️ 文字起こし結果の検証エラー"]

        if self.details.get("missing_fields"):
            messages.append(f"必須フィールドが欠落: {', '.join(self.details['missing_fields'])}")

        if self.details.get("invalid_segments"):
            count = len(self.details["invalid_segments"])
            messages.append(f"{count}個のセグメントで問題が検出されました")

        messages.append("📝 解決方法: 文字起こしを再実行してください")

        return "\n".join(messages)


class WordsFieldMissingError(TranscriptionValidationError):
    """wordsフィールド欠落エラー（最重要）"""

    def __init__(self, segment_count: int, sample_segments: list[str] | None = None):
        """
        Args:
            segment_count: wordsが欠落しているセグメント数
            sample_segments: サンプルセグメントテキスト
        """
        message = f"{segment_count}個のセグメントでwords情報が欠落しています"
        super().__init__(message, missing_fields=["words"], invalid_segments=sample_segments)
        self.segment_count = segment_count

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        return "❌ 文字位置情報（words）が見つかりません。文字起こしを再度実行して下さい。"


class AlignmentError(ProcessingError):
    """アライメント処理の一般的なエラー"""

    pass


class AlignmentValidationError(ProcessingError):
    """アライメント結果の検証エラー"""

    def __init__(self, message: str, failed_count: int, total_count: int, error_types: dict[str, int] | None = None):
        """
        Args:
            message: エラーメッセージ
            failed_count: 失敗したセグメント数
            total_count: 全セグメント数
            error_types: エラータイプ別の件数
        """
        details = {
            "failed_count": failed_count,
            "total_count": total_count,
            "success_rate": (total_count - failed_count) / total_count if total_count > 0 else 0,
            "error_types": error_types or {},
        }
        super().__init__(message, stage="alignment_validation", details=details, recoverable=True)

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        success_rate = self.details["success_rate"] * 100
        messages = [
            "⚠️ アライメント処理が部分的に失敗しました",
            f"成功率: {success_rate:.1f}% ({self.details['total_count'] - self.details['failed_count']}/{self.details['total_count']})",
        ]

        if self.details.get("error_types"):
            messages.append("\nエラーの内訳:")
            for error_type, count in self.details["error_types"].items():
                messages.append(f"  - {error_type}: {count}件")

        if success_rate > 50:
            messages.append("\n✅ 処理を継続できますが、一部の精度が低下する可能性があります")
        else:
            messages.append("\n❌ 成功率が低すぎるため、再実行を推奨します")

        return "\n".join(messages)


class SubprocessError(ProcessingError):
    """サブプロセス実行エラー"""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        return_code: int | None = None,
        stderr: str | None = None,
    ):
        """
        Args:
            message: エラーメッセージ
            command: 実行コマンド
            return_code: 終了コード
            stderr: 標準エラー出力
        """
        details = {"command": command, "return_code": return_code, "stderr": stderr}
        super().__init__(message, stage="subprocess", details=details, recoverable=True)

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        messages = ["⚠️ サブプロセスの実行でエラーが発生しました"]

        if self.details.get("return_code"):
            messages.append(f"終了コード: {self.details['return_code']}")

        if self.details.get("stderr"):
            stderr_lines = self.details["stderr"].strip().split("\n")
            if len(stderr_lines) > 5:
                messages.append("エラー内容（抜粋）:")
                messages.extend(f"  {line}" for line in stderr_lines[-5:])
            else:
                messages.append("エラー内容:")
                messages.extend(f"  {line}" for line in stderr_lines)

        messages.append("\n📝 解決方法: 処理を再実行してください")

        return "\n".join(messages)


class CacheError(ProcessingError):
    """キャッシュ関連のエラー"""

    def __init__(self, message: str, cache_path: str | None = None, operation: str | None = None):
        """
        Args:
            message: エラーメッセージ
            cache_path: キャッシュファイルパス
            operation: 操作（read/write/delete）
        """
        details = {"cache_path": cache_path, "operation": operation}
        super().__init__(message, stage="cache", details=details, recoverable=True)


class RetryExhaustedError(ProcessingError):
    """リトライ回数超過エラー"""

    def __init__(self, message: str, attempts: int, last_error: Exception | None = None):
        """
        Args:
            message: エラーメッセージ
            attempts: 試行回数
            last_error: 最後のエラー
        """
        details = {"attempts": attempts, "last_error": str(last_error) if last_error else None}
        super().__init__(message, stage="retry", details=details, recoverable=False)

    def get_user_message(self) -> str:
        """ユーザー向けメッセージを取得"""
        messages = [
            f"❌ {self.details['attempts']}回の再試行後も処理に失敗しました",
        ]

        if self.details.get("last_error"):
            messages.append(f"\n最後のエラー: {self.details['last_error']}")

        messages.extend(
            [
                "",
                "📝 解決方法:",
                "1. システムリソース（メモリ・ディスク）を確認",
                "2. 動画ファイルの破損を確認",
                "3. より小さいモデルサイズを試す",
                "4. 問題が続く場合は、ログファイルを確認",
            ]
        )

        return "\n".join(messages)
