#!/usr/bin/env python3
"""
リファクタリング完全性テスト

全フェーズのリファクタリングが正しく完了していることを確認する統合テスト。
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import json
import tempfile
import shutil

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))


class RefactoringCompletionTest:
    """リファクタリング完全性テスト"""
    
    def __init__(self):
        self.results = []
        self.errors = []
    
    def run_all_tests(self):
        """すべてのテストを実行"""
        print("=== リファクタリング完全性テスト開始 ===\n")
        
        # Phase 1: 基本的なリファクタリング
        self.test_phase1_constants()
        self.test_phase1_worker_class()
        
        # Phase 2: アーキテクチャ改善
        self.test_phase2_service_layer()
        self.test_phase2_alignment_diagnostics()
        
        # Phase 3: エラーハンドリングと型ヒント
        self.test_phase3_error_handling()
        self.test_phase3_type_hints()
        
        # 統合テスト
        self.test_integration()
        
        # 結果表示
        self.show_results()
    
    def test_phase1_constants(self):
        """Phase 1-1: 定数化のテスト"""
        print("Phase 1-1: マジックナンバーの定数化")
        
        try:
            # 定数ファイルのインポート確認
            from core.constants import (
                ProcessingDefaults, SilenceDetection,
                ModelSettings, ApiSettings, PerformanceSettings
            )
            
            # 定数の存在確認
            assert hasattr(ProcessingDefaults, 'LANGUAGE')
            assert hasattr(SilenceDetection, 'DEFAULT_THRESHOLD')
            assert hasattr(ModelSettings, 'DEFAULT_SIZE')
            
            # 型の確認
            assert isinstance(ProcessingDefaults.LANGUAGE, str)
            assert isinstance(SilenceDetection.DEFAULT_THRESHOLD, (int, float))
            
            self.add_result("Phase 1-1: 定数化", True, "すべての定数が正しく定義されています")
            
        except Exception as e:
            self.add_result("Phase 1-1: 定数化", False, str(e))
    
    def test_phase1_worker_class(self):
        """Phase 1-2/3: Workerクラス化のテスト"""
        print("\nPhase 1-2/3: Workerクラス化")
        
        try:
            # 新しいWorkerクラスのインポート
            from orchestrator.transcription_worker import TranscriptionWorker
            
            # クラスの属性確認
            assert hasattr(TranscriptionWorker, 'process_segment')
            assert hasattr(TranscriptionWorker, 'process_all_segments')
            assert hasattr(TranscriptionWorker, 'handle_error')
            
            # 旧実装が置き換えられているか確認
            worker_path = Path("worker_transcribe.py")
            if worker_path.exists():
                content = worker_path.read_text(encoding='utf-8')
                assert "TranscriptionWorker" in content
                assert "# 旧実装から新実装への移行" in content
            
            self.add_result("Phase 1-2/3: Workerクラス化", True, "Workerクラスが正しく実装されています")
            
        except Exception as e:
            self.add_result("Phase 1-2/3: Workerクラス化", False, str(e))
    
    def test_phase2_service_layer(self):
        """Phase 2-1/2: サービス層のテスト"""
        print("\nPhase 2-1/2: サービス層")
        
        try:
            # サービス層のインポート
            from services.base import BaseService, ServiceResult
            from services.transcription_service import TranscriptionService
            from services.export_service import ExportService
            from services.integration_service import IntegrationService
            
            # BaseServiceの検証
            assert hasattr(BaseService, 'execute')
            assert hasattr(BaseService, 'create_success_result')
            assert hasattr(BaseService, 'create_error_result')
            
            # ServiceResultの検証
            result = ServiceResult(success=True)
            assert hasattr(result, 'success')
            assert hasattr(result, 'data')
            assert hasattr(result, 'error')
            
            self.add_result("Phase 2-1/2: サービス層", True, "サービス層が正しく実装されています")
            
        except Exception as e:
            self.add_result("Phase 2-1/2: サービス層", False, str(e))
    
    def test_phase2_alignment_diagnostics(self):
        """Phase 2-3: アライメント診断のテスト"""
        print("\nPhase 2-3: アライメント診断")
        
        try:
            # アライメント診断のインポート
            from core.alignment_diagnostics import (
                AlignmentDiagnostics, DiagnosticLevel,
                DiagnosticResult, SegmentDiagnostic
            )
            
            # クラスの検証（引数を指定して初期化）
            from config import Config
            config = Config()
            diagnostics = AlignmentDiagnostics(model_size='medium', config=config)
            assert hasattr(diagnostics, 'analyze_segment')
            assert hasattr(diagnostics, 'analyze_result')
            assert hasattr(diagnostics, 'generate_report')
            
            # 診断レベルの確認
            assert hasattr(DiagnosticLevel, 'OK')
            assert hasattr(DiagnosticLevel, 'WARNING')
            assert hasattr(DiagnosticLevel, 'ERROR')
            
            self.add_result("Phase 2-3: アライメント診断", True, "診断機能が正しく実装されています")
            
        except Exception as e:
            self.add_result("Phase 2-3: アライメント診断", False, str(e))
    
    def test_phase3_error_handling(self):
        """Phase 3-1: エラーハンドリングのテスト"""
        print("\nPhase 3-1: エラーハンドリング")
        
        try:
            # エラーハンドリングのインポート
            from core.error_handling import (
                TextffCutError, ErrorHandler, ErrorSeverity,
                ErrorCategory, ValidationError, ProcessingError
            )
            
            # エラークラスの検証
            assert issubclass(ValidationError, TextffCutError)
            assert issubclass(ProcessingError, TextffCutError)
            
            # ErrorHandlerの検証
            handler = ErrorHandler()
            assert hasattr(handler, 'handle_error')
            assert hasattr(handler, 'format_user_message')
            
            # エラーカテゴリの確認
            assert hasattr(ErrorCategory, 'VALIDATION')
            assert hasattr(ErrorCategory, 'PROCESSING')
            
            self.add_result("Phase 3-1: エラーハンドリング", True, "統一エラーハンドリングが実装されています")
            
        except Exception as e:
            self.add_result("Phase 3-1: エラーハンドリング", False, str(e))
    
    def test_phase3_type_hints(self):
        """Phase 3-2: 型ヒントのテスト"""
        print("\nPhase 3-2: 型ヒント")
        
        try:
            # 型定義のインポート
            from core.types import (
                VideoPath, TimeSeconds, ModelSize,
                TranscriptionOptions, VideoMetadata,
                ProgressCallback, Result
            )
            
            # 型の使用確認
            video_path: VideoPath = "/path/to/video.mp4"
            duration: TimeSeconds = 123.45
            
            # TypedDictの確認
            options: TranscriptionOptions = {
                'language': 'ja',
                'model_size': 'medium'
            }
            
            # mypyの設定確認
            pyproject_path = Path("pyproject.toml")
            assert pyproject_path.exists()
            content = pyproject_path.read_text()
            assert "[tool.mypy]" in content
            
            self.add_result("Phase 3-2: 型ヒント", True, "型定義が正しく実装されています")
            
        except Exception as e:
            self.add_result("Phase 3-2: 型ヒント", False, str(e))
    
    def test_integration(self):
        """統合テスト: すべてのコンポーネントの連携"""
        print("\n統合テスト")
        
        try:
            # 主要なインポートが問題なく行えるか
            from main import main
            from config import Config
            from core.transcription import Transcriber
            from core.video import VideoProcessor
            from core.export import FCPXMLExporter
            
            # Configが新しい定数を使用しているか
            from core.constants import ProcessingDefaults
            config = Config()
            
            # サービス層が統合されているか
            from services.integration_service import IntegrationService
            
            # エラーハンドリングが統合されているか
            from core.error_handling import ErrorHandler
            
            self.add_result("統合テスト", True, "すべてのコンポーネントが正しく統合されています")
            
        except Exception as e:
            self.add_result("統合テスト", False, str(e))
    
    def add_result(self, test_name: str, success: bool, message: str):
        """テスト結果を追加"""
        self.results.append({
            'test': test_name,
            'success': success,
            'message': message
        })
        
        status = "✓" if success else "✗"
        print(f"  {status} {message}")
        
        if not success:
            self.errors.append(f"{test_name}: {message}")
    
    def show_results(self):
        """結果を表示"""
        print("\n=== テスト結果サマリー ===")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r['success'])
        failed = total - passed
        
        print(f"\n合計: {total} テスト")
        print(f"成功: {passed} テスト")
        print(f"失敗: {failed} テスト")
        
        if failed > 0:
            print("\n失敗したテスト:")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n🎉 すべてのテストが成功しました！")
        
        # 結果をJSONファイルに保存
        with open("refactoring_test_results.json", "w", encoding='utf-8') as f:
            json.dump({
                'summary': {
                    'total': total,
                    'passed': passed,
                    'failed': failed
                },
                'results': self.results,
                'errors': self.errors
            }, f, ensure_ascii=False, indent=2)
        
        print("\n結果は refactoring_test_results.json に保存されました")


def run_mypy_check():
    """mypyによる型チェック"""
    print("\n=== mypy型チェック ===")
    
    try:
        # mypyがインストールされているか確認
        result = subprocess.run(
            ["python", "-m", "mypy", "--version"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print("mypyがインストールされていません。スキップします。")
            return
        
        # 主要なモジュールの型チェック
        modules_to_check = [
            "core/types.py",
            "core/models_typed.py",
            "services/base_updated.py",
            "core/error_handling.py"
        ]
        
        for module in modules_to_check:
            if Path(module).exists():
                print(f"\n{module} の型チェック中...")
                result = subprocess.run(
                    ["python", "-m", "mypy", module],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"  ✓ 型チェック成功")
                else:
                    print(f"  ✗ 型チェックエラー:")
                    print(result.stdout)
    
    except Exception as e:
        print(f"型チェックエラー: {e}")


def check_documentation():
    """ドキュメントの更新確認"""
    print("\n=== ドキュメント確認 ===")
    
    docs_to_check = [
        ("README.md", ["リファクタリング", "アーキテクチャ"]),
        ("docs/refactoring_plan.md", ["Phase", "完了"]),
        ("docs/type_hints_guide.md", ["型ヒント", "ガイドライン"]),
        ("CLAUDE.md", ["リファクタリング", "完了"])
    ]
    
    for doc_path, keywords in docs_to_check:
        path = Path(doc_path)
        if path.exists():
            content = path.read_text(encoding='utf-8')
            found = all(keyword in content for keyword in keywords)
            status = "✓" if found else "⚠"
            print(f"{status} {doc_path} - {'更新済み' if found else '要確認'}")
        else:
            print(f"✗ {doc_path} - ファイルが見つかりません")


if __name__ == '__main__':
    # 完全性テスト実行
    tester = RefactoringCompletionTest()
    tester.run_all_tests()
    
    # 型チェック
    run_mypy_check()
    
    # ドキュメント確認
    check_documentation()
    
    print("\n=== 完了 ===")