#!/usr/bin/env python3
"""
リファクタリング統合テスト

新しいアーキテクチャと既存機能の統合をテストします。
"""
import sys
import unittest
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class TestRefactoringIntegration(unittest.TestCase):
    """リファクタリングの統合テスト"""

    def test_constants_usage_in_main(self) -> None:
        """main.pyでの定数使用をテスト"""
        print("\n=== main.pyでの定数使用テスト ===")

        # main.pyの内容を読み込み
        main_path = project_root / "main.py"
        with open(main_path, encoding="utf-8") as f:
            main_content = f.read()

        # 定数のインポートを確認
        self.assertIn("from core.constants import", main_content)
        self.assertIn("ApiSettings", main_content)
        self.assertIn("ModelSettings", main_content)
        self.assertIn("SilenceDetection", main_content)

        # マジックナンバーが置き換えられているか確認
        self.assertIn("ApiSettings.OPENAI_COST_PER_MINUTE", main_content)
        self.assertIn("ModelSettings.DEFAULT_SIZE", main_content)

        # 古いマジックナンバーが残っていないか確認
        # 0.006は定数定義以外では使われていないはず
        lines_with_0006 = [
            line for line in main_content.split("\n") if "0.006" in line and "OPENAI_COST_PER_MINUTE" not in line
        ]
        self.assertEqual(len(lines_with_0006), 0, f"マジックナンバー0.006が残っています: {lines_with_0006}")

        print("✓ 定数の使用: OK")

    def test_error_handling_integration(self) -> None:
        """新しいエラーハンドリングの統合をテスト"""
        print("\n=== エラーハンドリング統合テスト ===")

        # main.pyの内容を確認
        main_path = project_root / "main.py"
        with open(main_path, encoding="utf-8") as f:
            main_content = f.read()

        # 新しいエラーハンドリングのインポート
        self.assertIn("from core.error_handling import", main_content)
        self.assertIn("ErrorHandler", main_content)

        # エラーハンドリングの使用
        self.assertIn("ProcessingError", main_content)
        self.assertIn("ValidationError", main_content)
        self.assertIn("ResourceError", main_content)
        self.assertIn("FileValidationError", main_content)

        # ErrorHandlerの使用
        self.assertIn("error_handler = ErrorHandler", main_content)
        self.assertIn("error_handler.handle_error", main_content)

        print("✓ エラーハンドリングの統合: OK")

    def test_service_imports(self) -> None:
        """サービス層のインポートをテスト"""
        print("\n=== サービス層インポートテスト ===")

        # main.pyの内容を確認
        main_path = project_root / "main.py"
        with open(main_path, encoding="utf-8") as f:
            main_content = f.read()

        # IntegrationServiceのインポート
        self.assertIn("from services.integration_service import IntegrationService", main_content)

        # 既存サービスのインポート
        self.assertIn("from services import", main_content)
        self.assertIn("ConfigurationService", main_content)
        self.assertIn("VideoProcessingService", main_content)

        print("✓ サービス層のインポート: OK")

    def test_type_hints(self) -> None:
        """型ヒントの追加をテスト"""
        print("\n=== 型ヒントテスト ===")

        # main.pyの内容を確認
        main_path = project_root / "main.py"
        with open(main_path, encoding="utf-8") as f:
            main_content = f.read()

        # 型ヒントのインポート
        self.assertIn("from typing import", main_content)
        self.assertIn("Any", main_content)
        self.assertIn("Dict", main_content)

        # 関数の型ヒント
        self.assertIn("def main() -> None:", main_content)
        self.assertIn("def debug_words_status(result: Any) -> None:", main_content)

        print("✓ 型ヒントの追加: OK")

    def test_backward_compatibility(self) -> None:
        """後方互換性をテスト"""
        print("\n=== 後方互換性テスト ===")

        # 既存のインポートが維持されているか
        main_path = project_root / "main.py"
        with open(main_path, encoding="utf-8") as f:
            main_content = f.read()

        # 既存のコアモジュール
        self.assertIn("from core import Transcriber, TextProcessor", main_content)
        self.assertIn("from core.transcription_smart_split import SmartSplitTranscriber", main_content)
        self.assertIn("from core.transcription_subprocess import SubprocessTranscriber", main_content)

        # 既存のユーティリティ
        self.assertIn("from utils.file_utils import ensure_directory", main_content)
        self.assertIn("from utils.time_utils import format_time", main_content)

        # 既存の例外（互換性のため残されている）
        self.assertIn("from utils.exceptions import", main_content)

        print("✓ 後方互換性: OK")

    def test_api_cost_constant(self) -> None:
        """API料金定数の統合をテスト"""
        print("\n=== API料金定数テスト ===")

        # 定数が定義されているか
        from core.constants import ApiSettings

        self.assertTrue(hasattr(ApiSettings, "OPENAI_COST_PER_MINUTE"))
        self.assertEqual(ApiSettings.OPENAI_COST_PER_MINUTE, 0.006)

        print(f"✓ API料金定数: ${ApiSettings.OPENAI_COST_PER_MINUTE}/分")

    def test_worker_compatibility(self) -> None:
        """worker_transcribe.pyの互換性をテスト"""
        print("\n=== ワーカー互換性テスト ===")

        # worker_transcribe.pyが存在し、インポート可能か
        worker_path = project_root / "worker_transcribe.py"
        self.assertTrue(worker_path.exists(), "worker_transcribe.pyが存在しません")

        # 新しいTranscriptionWorkerクラスがインポート可能か
        try:
            from orchestrator import TranscriptionWorker as NewWorker  # noqa: F401

            print("✓ 新しいTranscriptionWorkerクラス: インポート可能")
        except ImportError as e:
            self.fail(f"新しいTranscriptionWorkerクラスのインポートに失敗: {e}")

        # 既存のmain関数が存在するか
        with open(worker_path, encoding="utf-8") as f:
            worker_content = f.read()

        self.assertIn("def main():", worker_content)
        self.assertIn('if __name__ == "__main__":', worker_content)

        print("✓ worker_transcribe.pyの互換性: OK")


def run_integration_tests() -> None:
    """統合テストを実行"""
    print("=" * 60)
    print("リファクタリング統合テスト")
    print("=" * 60)

    # テストスイートを作成
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRefactoringIntegration)

    # テストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    print(f"実行テスト数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ すべてのテストが成功しました！")
        print("リファクタリングは既存機能と正しく統合されています。")
    else:
        print("\n❌ 一部のテストが失敗しました。")
        print("上記のエラーを確認して修正してください。")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
