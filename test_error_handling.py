#!/usr/bin/env python3
"""
統一エラーハンドリングシステムのテスト
"""

import logging
import sys
import unittest
from io import StringIO
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from core.error_handling import (
    AlignmentError,
    ErrorCategory,
    ErrorHandler,
    ErrorSeverity,
    ExportError,
    FFmpegError,
    FileValidationError,
    InsufficientMemoryError,
    ProcessingError,
    TextffCutError,
    TranscriptionError,
    ValidationError,
    VideoProcessingError,
    WhisperError,
    WordsFieldMissingError,
)


class TestErrorClasses(unittest.TestCase):
    """エラークラスのテスト"""

    def test_base_error_creation(self) -> None:
        """基底エラークラスの作成テスト"""
        error = TextffCutError(message="テストエラー", details={"key": "value"}, user_message="ユーザー向けメッセージ")

        self.assertEqual(error.message, "テストエラー")
        self.assertEqual(error.details, {"key": "value"})
        self.assertEqual(error.user_message, "ユーザー向けメッセージ")
        self.assertEqual(error.error_code, "UNKNOWN_ERROR")
        self.assertIsNotNone(error.timestamp)

    def test_validation_error(self) -> None:
        """検証エラーのテスト"""
        error = ValidationError("無効な入力", details={"field": "email"})

        self.assertEqual(error.error_code, "VALIDATION_ERROR")
        self.assertEqual(error.severity, ErrorSeverity.WARNING)
        self.assertEqual(error.category, ErrorCategory.VALIDATION)
        self.assertTrue(error.recoverable)

    def test_file_validation_error(self) -> None:
        """ファイル検証エラーのテスト"""
        error = FileValidationError("/path/to/file not found")

        self.assertEqual(error.error_code, "FILE_VALIDATION_ERROR")
        self.assertEqual(error.user_message, "ファイルが見つからないか、アクセスできません")

    def test_processing_errors(self) -> None:
        """処理エラーのテスト"""
        # 文字起こしエラー
        trans_error = TranscriptionError("文字起こし失敗")
        self.assertEqual(trans_error.error_code, "TRANSCRIPTION_ERROR")

        # 動画処理エラー
        video_error = VideoProcessingError("動画処理失敗")
        self.assertEqual(video_error.error_code, "VIDEO_PROCESSING_ERROR")

        # アライメントエラー
        align_error = AlignmentError("アライメント失敗")
        self.assertEqual(align_error.error_code, "ALIGNMENT_ERROR")

        # エクスポートエラー
        export_error = ExportError("エクスポート失敗")
        self.assertEqual(export_error.error_code, "EXPORT_ERROR")

    def test_resource_errors(self) -> None:
        """リソースエラーのテスト"""
        # メモリ不足エラー
        memory_error = InsufficientMemoryError("メモリ不足", details={"available": "2GB"})
        self.assertEqual(memory_error.error_code, "INSUFFICIENT_MEMORY_ERROR")
        self.assertEqual(memory_error.severity, ErrorSeverity.CRITICAL)

    def test_external_system_errors(self) -> None:
        """外部システムエラーのテスト"""
        # FFmpegエラー
        ffmpeg_error = FFmpegError("FFmpeg実行失敗", details={"command": "ffmpeg -i input.mp4"})
        self.assertEqual(ffmpeg_error.error_code, "FFMPEG_ERROR")

        # Whisperエラー
        whisper_error = WhisperError("Whisperモデルロード失敗")
        self.assertEqual(whisper_error.error_code, "WHISPER_ERROR")

    def test_words_field_missing_error(self) -> None:
        """wordsフィールド欠落エラーのテスト"""
        error = WordsFieldMissingError("wordsフィールドがありません")
        self.assertEqual(error.error_code, "WORDS_FIELD_MISSING")
        self.assertTrue(error.recoverable)

    def test_error_with_cause(self) -> None:
        """原因付きエラーのテスト"""
        cause = ValueError("元のエラー")
        error = ProcessingError("処理エラー", cause=cause)

        self.assertEqual(error.cause, cause)
        self.assertEqual(error.details["cause_type"], "ValueError")
        self.assertEqual(error.details["cause_message"], "元のエラー")

    def test_error_to_dict(self) -> None:
        """エラー情報の辞書変換テスト"""
        error = ValidationError("テストエラー", details={"field": "name"}, user_message="名前が無効です")

        error_dict = error.to_dict()

        self.assertEqual(error_dict["error_code"], "VALIDATION_ERROR")
        self.assertEqual(error_dict["message"], "テストエラー")
        self.assertEqual(error_dict["user_message"], "名前が無効です")
        self.assertEqual(error_dict["severity"], "warning")
        self.assertEqual(error_dict["category"], "validation")
        self.assertTrue(error_dict["recoverable"])
        self.assertEqual(error_dict["details"], {"field": "name"})
        self.assertIn("timestamp", error_dict)


class TestErrorHandler(unittest.TestCase):
    """ErrorHandlerのテスト"""

    def setUp(self) -> None:
        """テスト前の準備"""
        # ログ出力をキャプチャするための設定
        self.log_stream = StringIO()
        self.log_handler = logging.StreamHandler(self.log_stream)
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.log_handler)

        self.error_handler = ErrorHandler(self.logger)

    def tearDown(self) -> None:
        """テスト後のクリーンアップ"""
        self.logger.removeHandler(self.log_handler)
        self.log_stream.close()

    def test_handle_textffcut_error(self) -> None:
        """TextffCutErrorの処理テスト"""
        error = ValidationError("テスト検証エラー", details={"test": True})

        # raise_after=Falseでエラー情報を取得
        error_info = self.error_handler.handle_error(error, context="test_context", raise_after=False)

        self.assertIsNotNone(error_info)
        self.assertEqual(error_info["error_code"], "VALIDATION_ERROR")
        self.assertEqual(error_info["context"], "test_context")

        # ログ出力の確認
        log_output = self.log_stream.getvalue()
        self.assertIn("[test_context]", log_output)
        self.assertIn("[VALIDATION_ERROR]", log_output)

    def test_handle_unexpected_error(self) -> None:
        """予期しないエラーの処理テスト"""
        error = ValueError("予期しないエラー")

        error_info = self.error_handler.handle_error(error, context="unexpected_test", raise_after=False)

        self.assertIsNotNone(error_info)
        self.assertEqual(error_info["error_code"], "UNEXPECTED_ERROR")
        self.assertEqual(error_info["error_type"], "ValueError")
        self.assertEqual(error_info["message"], "予期しないエラー")

    def test_error_severity_logging(self) -> None:
        """エラー重要度に応じたログ出力テスト"""
        # CRITICALエラー
        critical_error = InsufficientMemoryError("メモリ不足")
        self.error_handler.handle_error(critical_error, context="memory_test", raise_after=False)

        log_output = self.log_stream.getvalue()
        # Pythonのloggingモジュールは大文字でレベルを出力
        self.assertIn("CRITICAL", log_output)

    def test_format_user_message(self) -> None:
        """ユーザーメッセージのフォーマットテスト"""
        # TextffCutError
        error1 = ValidationError("エラー")
        msg1 = ErrorHandler.format_user_message(error1)
        self.assertEqual(msg1, "入力値が正しくありません")

        # 通常の例外
        error2 = ValueError("エラー")
        msg2 = ErrorHandler.format_user_message(error2)
        self.assertEqual(msg2, "システムエラーが発生しました")

    def test_is_recoverable(self) -> None:
        """回復可能性チェックのテスト"""
        # 回復可能
        error1 = ValidationError("エラー")
        self.assertTrue(ErrorHandler.is_recoverable(error1))

        # 回復不可能
        error2 = ProcessingError("エラー")
        self.assertFalse(ErrorHandler.is_recoverable(error2))

        # 通常の例外
        error3 = ValueError("エラー")
        self.assertFalse(ErrorHandler.is_recoverable(error3))

    def test_get_error_code(self) -> None:
        """エラーコード取得テスト"""
        # TextffCutError
        error1 = TranscriptionError("エラー")
        code1 = ErrorHandler.get_error_code(error1)
        self.assertEqual(code1, "TRANSCRIPTION_ERROR")

        # 通常の例外
        error2 = RuntimeError("エラー")
        code2 = ErrorHandler.get_error_code(error2)
        self.assertEqual(code2, "UNEXPECTED_ERROR")

    def test_raise_after_true(self) -> None:
        """raise_after=Trueの場合の動作テスト"""
        error = ValidationError("テストエラー")

        with self.assertRaises(ValidationError):
            self.error_handler.handle_error(error, context="raise_test", raise_after=True)

        # ログは出力されているはず
        log_output = self.log_stream.getvalue()
        self.assertIn("[raise_test]", log_output)


class TestErrorScenarios(unittest.TestCase):
    """実際の使用シナリオのテスト"""

    def test_file_processing_scenario(self) -> None:
        """ファイル処理シナリオ"""

        def process_file(path: str):
            if not path:
                raise FileValidationError("ファイルパスが指定されていません")

            if not path.endswith(".mp4"):
                raise ValidationError(
                    "サポートされていないファイル形式",
                    details={"path": path, "expected": "mp4"},
                    user_message="MP4ファイルを指定してください",
                )

            # 処理中のエラー
            raise VideoProcessingError(
                "動画の処理に失敗しました", details={"path": path, "reason": "codec_not_supported"}
            )

        # テスト実行
        with self.assertRaises(FileValidationError):
            process_file("")

        with self.assertRaises(ValidationError) as cm:
            process_file("test.avi")
        self.assertEqual(cm.exception.user_message, "MP4ファイルを指定してください")

        with self.assertRaises(VideoProcessingError) as cm2:
            process_file("test.mp4")
        self.assertEqual(cm2.exception.details["reason"], "codec_not_supported")

    def test_memory_check_scenario(self) -> None:
        """メモリチェックシナリオ"""

        def check_memory(required_gb: float, available_gb: float):
            if available_gb < required_gb:
                raise InsufficientMemoryError(
                    f"メモリが不足しています。必要: {required_gb}GB, 利用可能: {available_gb}GB",
                    details={"required_gb": required_gb, "available_gb": available_gb},
                )

        # メモリ不足のテスト
        with self.assertRaises(InsufficientMemoryError) as cm:
            check_memory(8.0, 4.0)

        self.assertEqual(cm.exception.severity, ErrorSeverity.CRITICAL)
        self.assertEqual(cm.exception.details["required_gb"], 8.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
