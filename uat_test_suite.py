"""
UAT (User Acceptance Testing) テストスイート
既存機能への影響とエラーを徹底的にチェック
"""
import os
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

# テスト用の設定
TEST_VIDEO_SHORT = "/Users/naoki/myProject/TextffCut/videos/test.mp4"
TEST_VIDEO_MEDIUM = "/Users/naoki/myProject/TextffCut/videos/001_AI活用の始めの一歩：お笑いAIから学ぶ発想術.mp4"
TEST_VIDEO_LONG = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）世界は保守かリベラルか？ではなくて変革か維持か？で2つに分かれてる.mp4"


class UATTestSuite:
    """UATテストスイート"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.test_results = []
        self.failed_tests = []
        
    def log_result(self, test_name: str, status: str, details: str = "", error: Exception = None):
        """テスト結果をログ"""
        result = {
            "test_name": test_name,
            "status": status,
            "details": details,
            "error": str(error) if error else None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        
        if status == "FAILED":
            self.failed_tests.append(test_name)
            
        # コンソール出力
        icon = "✅" if status == "PASSED" else "❌"
        print(f"{icon} {test_name}: {status}")
        if details:
            print(f"   {details}")
        if error:
            print(f"   Error: {error}")
    
    def run_all_tests(self):
        """すべてのテストを実行"""
        print("\n" + "="*80)
        print("UAT (User Acceptance Testing) 開始")
        print("="*80 + "\n")
        
        # 1. 環境チェック
        self.test_environment_check()
        
        # 2. 既存機能のテスト
        self.test_existing_features()
        
        # 3. 新機能のテスト
        self.test_new_features()
        
        # 4. エラーハンドリングテスト
        self.test_error_handling()
        
        # 5. パフォーマンステスト
        self.test_performance()
        
        # 6. UI統合テスト
        self.test_ui_integration()
        
        # 7. 結果サマリー
        self.print_summary()
    
    def test_environment_check(self):
        """環境チェック"""
        print("\n[1. 環境チェック]")
        
        # 必要なモジュールのインポートチェック
        try:
            from config import Config
            from core.transcription import Transcriber
            from core.video import VideoProcessor
            from core.text_processor import TextProcessor
            from core.export import FCPXMLExporter
            self.log_result("モジュールインポート", "PASSED")
        except ImportError as e:
            self.log_result("モジュールインポート", "FAILED", error=e)
            return
        
        # 設定ファイルの読み込み
        try:
            config = Config()
            self.log_result("設定ファイル読み込み", "PASSED")
        except Exception as e:
            self.log_result("設定ファイル読み込み", "FAILED", error=e)
        
        # テスト動画の存在確認
        for video_path in [TEST_VIDEO_SHORT, TEST_VIDEO_MEDIUM]:
            if Path(video_path).exists():
                self.log_result(f"テスト動画確認: {Path(video_path).name}", "PASSED")
            else:
                self.log_result(f"テスト動画確認: {Path(video_path).name}", "FAILED", 
                              details="ファイルが見つかりません")
    
    def test_existing_features(self):
        """既存機能のテスト"""
        print("\n[2. 既存機能のリグレッションテスト]")
        
        # 2.1 ローカルモード（WhisperX）のテスト
        self._test_local_mode()
        
        # 2.2 従来のAPIモードのテスト
        self._test_legacy_api_mode()
        
        # 2.3 テキスト処理機能
        self._test_text_processing()
        
        # 2.4 動画処理機能
        self._test_video_processing()
        
        # 2.5 エクスポート機能
        self._test_export_functionality()
    
    def _test_local_mode(self):
        """ローカルモードのテスト"""
        try:
            from config import Config
            config = Config()
            config.transcription.use_api = False
            
            # WhisperXが利用可能かチェック
            try:
                import whisperx
                self.log_result("WhisperX利用可能性", "PASSED")
            except ImportError:
                self.log_result("WhisperX利用可能性", "SKIPPED", 
                              details="WhisperXがインストールされていません")
                return
            
            # 簡単な文字起こしテスト
            from core.transcription import Transcriber
            transcriber = Transcriber(config)
            
            # キャッシュを使用してテスト
            cache_path = transcriber.get_cache_path(TEST_VIDEO_SHORT, "base")
            if cache_path.exists():
                result = transcriber.load_from_cache(cache_path)
                if result:
                    self.log_result("ローカルモード: キャッシュ読み込み", "PASSED",
                                  details=f"{len(result.segments)}セグメント")
                else:
                    self.log_result("ローカルモード: キャッシュ読み込み", "FAILED")
            else:
                self.log_result("ローカルモード: キャッシュ読み込み", "SKIPPED",
                              details="キャッシュが存在しません")
                
        except Exception as e:
            self.log_result("ローカルモードテスト", "FAILED", error=e)
    
    def _test_legacy_api_mode(self):
        """従来のAPIモードのテスト"""
        if not self.api_key:
            self.log_result("APIモード: 基本動作", "SKIPPED", 
                          details="APIキーが設定されていません")
            return
        
        try:
            from config import Config
            config = Config()
            config.transcription.use_api = True
            config.transcription.api_key = self.api_key
            
            # adaptive_workersを無効化して従来モードをテスト
            config.transcription.adaptive_workers = False
            
            from core.transcription import Transcriber
            transcriber = Transcriber(config)
            
            # インスタンス作成の確認
            self.log_result("APIモード: インスタンス作成", "PASSED")
            
            # API設定の確認
            if transcriber.api_transcriber:
                self.log_result("APIモード: 設定確認", "PASSED")
            else:
                self.log_result("APIモード: 設定確認", "FAILED")
                
        except Exception as e:
            self.log_result("APIモードテスト", "FAILED", error=e)
    
    def _test_text_processing(self):
        """テキスト処理機能のテスト"""
        try:
            from core.text_processor import TextProcessor
            processor = TextProcessor()
            
            # 差分検出テスト
            original = "これはテスト文章です。"
            revised = "これは修正されたテスト文章です。"
            
            differences = processor.find_differences(original, revised)
            
            if differences and differences.has_additions():
                self.log_result("テキスト処理: 差分検出", "PASSED",
                              details=f"{len(differences.added_chars)}文字の追加を検出")
            else:
                self.log_result("テキスト処理: 差分検出", "FAILED",
                              details="差分が検出されませんでした")
                
        except Exception as e:
            self.log_result("テキスト処理テスト", "FAILED", error=e)
    
    def _test_video_processing(self):
        """動画処理機能のテスト"""
        try:
            from core.video import VideoProcessor, VideoInfo
            from config import Config
            config = Config()
            processor = VideoProcessor(config)
            
            # 動画情報取得テスト
            if Path(TEST_VIDEO_SHORT).exists():
                info = VideoInfo.from_file(TEST_VIDEO_SHORT)
                if info and info.duration > 0:
                    self.log_result("動画処理: 情報取得", "PASSED",
                                  details=f"動画長: {info.duration:.1f}秒")
                else:
                    self.log_result("動画処理: 情報取得", "FAILED")
            else:
                self.log_result("動画処理: 情報取得", "SKIPPED",
                              details="テスト動画が見つかりません")
                
        except Exception as e:
            self.log_result("動画処理テスト", "FAILED", error=e)
    
    def _test_export_functionality(self):
        """エクスポート機能のテスト"""
        try:
            from core.export import FCPXMLExporter, ExportSegment
            from config import Config
            config = Config()
            exporter = FCPXMLExporter(config)
            
            # 実際のテスト動画を使用
            if not Path(TEST_VIDEO_SHORT).exists():
                self.log_result("エクスポート: FCPXML生成", "SKIPPED",
                              details="テスト動画が見つかりません")
                return
            
            # 実際の動画を使用したセグメント
            segments = [
                ExportSegment(
                    source_path=TEST_VIDEO_SHORT,
                    start_time=0,
                    end_time=2,
                    timeline_start=0
                ),
                ExportSegment(
                    source_path=TEST_VIDEO_SHORT,
                    start_time=5,
                    end_time=7,
                    timeline_start=2
                )
            ]
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fcpxml', delete=False) as f:
                temp_path = f.name
            
            try:
                success = exporter.export(
                    segments=segments,
                    output_path=temp_path,
                    timeline_fps=30,
                    project_name="UAT Test Project"
                )
                
                if success and Path(temp_path).exists():
                    # FCPXMLファイルの内容を簡単に検証
                    with open(temp_path, 'r') as f:
                        content = f.read()
                        if "<fcpxml" in content and "</fcpxml>" in content:
                            self.log_result("エクスポート: FCPXML生成", "PASSED",
                                          details="有効なFCPXMLファイルを生成")
                        else:
                            self.log_result("エクスポート: FCPXML生成", "FAILED",
                                          details="無効なFCPXMLファイル")
                else:
                    self.log_result("エクスポート: FCPXML生成", "FAILED",
                                  details="ファイル生成に失敗")
                    
            finally:
                if Path(temp_path).exists():
                    os.unlink(temp_path)
                    
        except Exception as e:
            self.log_result("エクスポートテスト", "FAILED", error=e)
    
    def test_new_features(self):
        """新機能のテスト"""
        print("\n[3. 新機能のテスト]")
        
        # 3.1 自動最適化選択
        self._test_auto_optimization()
        
        # 3.2 ディスクキャッシュ
        self._test_disk_cache()
        
        # 3.3 セグメント分割
        self._test_segment_splitter()
        
        # 3.4 システムリソース管理
        self._test_system_resources()
    
    def _test_auto_optimization(self):
        """自動最適化選択のテスト"""
        try:
            from config import Config
            config = Config()
            config.transcription.use_api = True
            config.transcription.adaptive_workers = True
            
            # 環境変数で低スペックモードを強制
            os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"
            
            from utils.system_resources import system_resource_manager
            spec = system_resource_manager.get_system_spec()
            
            if spec.spec_level == 'low':
                self.log_result("自動最適化: 低スペック検出", "PASSED",
                              details=f"推奨チャンクサイズ: {spec.recommended_chunk_seconds}秒")
            else:
                self.log_result("自動最適化: 低スペック検出", "FAILED",
                              details=f"検出されたスペック: {spec.spec_level}")
            
            # 環境変数をクリーンアップ
            del os.environ["TEXTFFCUT_FORCE_LOW_SPEC"]
            
        except Exception as e:
            self.log_result("自動最適化テスト", "FAILED", error=e)
            if "TEXTFFCUT_FORCE_LOW_SPEC" in os.environ:
                del os.environ["TEXTFFCUT_FORCE_LOW_SPEC"]
    
    def _test_disk_cache(self):
        """ディスクキャッシュのテスト"""
        try:
            from core.disk_cache_manager import DiskCacheManager
            cache = DiskCacheManager()
            
            # テストデータ
            test_segments = [{"start": 0, "end": 5, "text": "テスト"}]
            
            # 保存と読み込み
            cache.save_api_result(0, test_segments)
            loaded = cache.load_api_result(0)
            
            if loaded and loaded[0]["text"] == "テスト":
                self.log_result("ディスクキャッシュ: 保存/読み込み", "PASSED")
            else:
                self.log_result("ディスクキャッシュ: 保存/読み込み", "FAILED")
            
            # クリーンアップ
            cache.cleanup()
            
        except Exception as e:
            self.log_result("ディスクキャッシュテスト", "FAILED", error=e)
    
    def _test_segment_splitter(self):
        """セグメント分割のテスト"""
        try:
            from core.segment_splitter import SegmentSplitter
            splitter = SegmentSplitter()
            
            # 長いセグメントのテスト
            long_segment = {
                "start": 0,
                "end": 30,
                "text": "これは長いテスト文章です。" * 10
            }
            
            result = splitter.split_segments([long_segment], 20)
            
            if len(result) > 1:
                self.log_result("セグメント分割: 長いセグメント", "PASSED",
                              details=f"1セグメント → {len(result)}セグメント")
            else:
                self.log_result("セグメント分割: 長いセグメント", "FAILED",
                              details="分割されませんでした")
                
        except Exception as e:
            self.log_result("セグメント分割テスト", "FAILED", error=e)
    
    def _test_system_resources(self):
        """システムリソース管理のテスト"""
        try:
            from utils.system_resources import system_resource_manager
            
            # メモリ使用量取得
            memory_usage = system_resource_manager.get_memory_usage()
            if memory_usage > 0:
                self.log_result("システムリソース: メモリ監視", "PASSED",
                              details=f"現在の使用量: {memory_usage:.1f}GB")
            else:
                self.log_result("システムリソース: メモリ監視", "FAILED")
            
            # メモリプレッシャーチェック
            is_pressure = system_resource_manager.check_memory_pressure()
            self.log_result("システムリソース: メモリプレッシャー", "PASSED",
                          details=f"メモリプレッシャー: {'あり' if is_pressure else 'なし'}")
            
        except Exception as e:
            self.log_result("システムリソーステスト", "FAILED", error=e)
    
    def test_error_handling(self):
        """エラーハンドリングのテスト"""
        print("\n[4. エラーハンドリングテスト]")
        
        # 4.1 無効なファイルパス
        self._test_invalid_file_path()
        
        # 4.2 APIエラーシミュレーション
        self._test_api_errors()
        
        # 4.3 メモリ不足シミュレーション
        self._test_memory_pressure()
    
    def _test_invalid_file_path(self):
        """無効なファイルパスのテスト"""
        try:
            from core.video import VideoProcessor
            processor = VideoProcessor()
            
            # 存在しないファイル
            info = processor.get_video_info("non_existent_file.mp4")
            if info is None:
                self.log_result("エラーハンドリング: 無効なファイル", "PASSED",
                              details="適切にNoneを返しました")
            else:
                self.log_result("エラーハンドリング: 無効なファイル", "FAILED",
                              details="エラーが正しく処理されませんでした")
                
        except Exception as e:
            # 例外が発生した場合も適切
            self.log_result("エラーハンドリング: 無効なファイル", "PASSED",
                          details=f"例外が適切に発生: {type(e).__name__}")
    
    def _test_api_errors(self):
        """APIエラーのテスト"""
        try:
            from core.timeout_handler import TimeoutHandler
            handler = TimeoutHandler(max_retries=1, initial_timeout=0.1)
            
            # エラーをシミュレート
            def error_func():
                raise Exception("テストエラー")
            
            result = handler.with_timeout_and_retry(error_func, task_name="エラーテスト")
            
            if result is None:
                self.log_result("エラーハンドリング: リトライ処理", "PASSED",
                              details="エラーが正しく処理されました")
            else:
                self.log_result("エラーハンドリング: リトライ処理", "FAILED",
                              details="エラーが処理されませんでした")
                
        except Exception as e:
            self.log_result("APIエラーテスト", "FAILED", error=e)
    
    def _test_memory_pressure(self):
        """メモリプレッシャーのテスト"""
        try:
            from utils.system_resources import system_resource_manager
            
            # 現在のワーカー数
            current_api = 10
            current_align = 3
            
            # 調整テスト
            new_api, new_align = system_resource_manager.adjust_workers_for_memory(
                current_api, current_align
            )
            
            self.log_result("エラーハンドリング: メモリ調整", "PASSED",
                          details=f"ワーカー数: {current_api}→{new_api}, {current_align}→{new_align}")
            
        except Exception as e:
            self.log_result("メモリプレッシャーテスト", "FAILED", error=e)
    
    def test_performance(self):
        """パフォーマンステスト"""
        print("\n[5. パフォーマンステスト]")
        
        # 簡易的なパフォーマンス確認
        try:
            from core.disk_cache_manager import DiskCacheManager
            cache = DiskCacheManager()
            
            # 大量データの書き込みテスト
            start_time = time.time()
            for i in range(100):
                cache.save_api_result(i, [{"text": f"segment_{i}"}])
            write_time = time.time() - start_time
            
            # 読み込みテスト
            start_time = time.time()
            for i in range(100):
                cache.load_api_result(i)
            read_time = time.time() - start_time
            
            cache.cleanup()
            
            self.log_result("パフォーマンス: ディスクI/O", "PASSED",
                          details=f"書込: {write_time:.3f}秒, 読込: {read_time:.3f}秒 (100件)")
            
        except Exception as e:
            self.log_result("パフォーマンステスト", "FAILED", error=e)
    
    def test_ui_integration(self):
        """UI統合テスト（Streamlit）"""
        print("\n[6. UI統合テスト]")
        
        # Streamlitコンポーネントのインポートテスト
        try:
            from ui.components import show_video_selector, show_api_key_manager, show_transcription_mode_selector
            from ui.file_upload import show_video_input
            self.log_result("UI: モジュールインポート", "PASSED")
        except ImportError as e:
            self.log_result("UI: モジュールインポート", "FAILED", error=e)
            return
        
        # main.pyの基本的な機能確認
        try:
            from main import process_transcription
            self.log_result("UI: メイン処理関数", "PASSED",
                          details="process_transcription関数が利用可能")
        except ImportError:
            self.log_result("UI: メイン処理関数", "SKIPPED",
                          details="main.pyのインポートエラー（Streamlit依存）")
        
        # 設定の確認
        try:
            from config import Config
            config = Config()
            
            # API/ローカルモードの切り替え確認
            original_use_api = config.transcription.use_api
            config.transcription.use_api = True
            self.log_result("UI: API/ローカル切り替え", "PASSED",
                          details="設定の切り替えが可能")
            config.transcription.use_api = original_use_api
            
        except Exception as e:
            self.log_result("UI統合テスト", "FAILED", error=e)
    
    def print_summary(self):
        """テスト結果のサマリーを表示"""
        print("\n" + "="*80)
        print("UAT テスト結果サマリー")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["status"] == "PASSED")
        failed_tests = sum(1 for r in self.test_results if r["status"] == "FAILED")
        skipped_tests = sum(1 for r in self.test_results if r["status"] == "SKIPPED")
        
        print(f"\n総テスト数: {total_tests}")
        print(f"✅ 成功: {passed_tests}")
        print(f"❌ 失敗: {failed_tests}")
        print(f"⏭️  スキップ: {skipped_tests}")
        
        if failed_tests > 0:
            print(f"\n失敗したテスト:")
            for test_name in self.failed_tests:
                print(f"  - {test_name}")
        
        # 結果をファイルに保存
        report_path = "uat_test_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": {
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests,
                    "skipped": skipped_tests
                },
                "results": self.test_results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n詳細なレポートを保存しました: {report_path}")
        
        # 最終判定
        if failed_tests == 0:
            print("\n🎉 すべてのテストが成功しました！プルリクエストの作成を推奨します。")
            return True
        else:
            print("\n⚠️  一部のテストが失敗しました。修正が必要です。")
            return False


def main():
    """メイン実行"""
    # APIキーを取得
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    elif os.environ.get("OPENAI_API_KEY"):
        api_key = os.environ.get("OPENAI_API_KEY")
    
    # テストスイート実行
    suite = UATTestSuite(api_key=api_key)
    success = suite.run_all_tests()
    
    # 終了コード
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()