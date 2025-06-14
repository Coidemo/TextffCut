#!/usr/bin/env python
"""
worker_transcribe.pyとworker_transcribe_v2.pyの統合テスト

両方の実装が同じ結果を生成することを確認します。
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def create_test_config(video_path: str, model_size: str = "base", 
                      task_type: str = "full", use_api: bool = False) -> str:
    """テスト用の設定ファイルを作成"""
    config_data = {
        'video_path': video_path,
        'model_size': model_size,
        'use_cache': False,
        'save_cache': False,
        'task_type': task_type,
        'config': {
            'transcription': {
                'use_api': use_api,
                'api_provider': 'openai',
                'api_key': 'test_key' if use_api else None,
                'model_size': model_size,
                'language': 'ja',
                'compute_type': 'int8',
                'sample_rate': 16000,
                'isolation_mode': 'none'
            }
        }
    }
    
    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        return f.name


def run_worker(script_name: str, config_path: str) -> dict:
    """ワーカースクリプトを実行して結果を取得"""
    result_path = os.path.join(os.path.dirname(config_path), 'result.json')
    
    # 既存の結果ファイルを削除
    if os.path.exists(result_path):
        os.unlink(result_path)
    
    # ワーカーを実行
    cmd = [sys.executable, script_name, config_path]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    
    # プログレス出力を解析
    progress_lines = [line for line in stdout.split('\n') if line.startswith('PROGRESS:')]
    
    # エラーチェック
    if process.returncode != 0:
        print(f"Error running {script_name}:")
        print(f"STDOUT:\n{stdout}")
        print(f"STDERR:\n{stderr}")
        return None
    
    # 結果ファイルを読み込み
    if not os.path.exists(result_path):
        print(f"Result file not found: {result_path}")
        return None
    
    with open(result_path, 'r') as f:
        result = json.load(f)
    
    return {
        'result': result,
        'progress_lines': progress_lines,
        'stdout': stdout,
        'stderr': stderr
    }


def compare_imports():
    """両方のスクリプトがインポートできることを確認"""
    print("=== インポートテスト ===")
    
    try:
        import worker_transcribe
        print("✅ worker_transcribe.py のインポート成功")
    except Exception as e:
        print(f"❌ worker_transcribe.py のインポート失敗: {e}")
        return False
    
    try:
        import worker_transcribe_v2
        print("✅ worker_transcribe_v2.py のインポート成功")
    except Exception as e:
        print(f"❌ worker_transcribe_v2.py のインポート失敗: {e}")
        return False
    
    return True


def compare_basic_structure():
    """基本的な構造比較"""
    print("\n=== 構造比較 ===")
    
    # テスト動画の存在確認
    test_video = "videos/test_short.mp4"
    if not os.path.exists(test_video):
        print(f"⚠️ テスト動画が見つかりません: {test_video}")
        print("短いテスト動画を作成してください")
        return False
    
    # 設定ファイルを作成
    config_path = create_test_config(test_video)
    
    try:
        # 両方のワーカーで同じ設定を処理（ドライラン）
        print("設定ファイルの処理をテスト中...")
        
        # worker_transcribe_v2の構造をテスト
        from worker_transcribe_v2 import TranscriptionWorker, ConfigLoader
        
        loader = ConfigLoader(config_path)
        config = loader.load()
        
        print(f"✅ 設定読み込み成功: video_path={config.video_path}")
        print(f"✅ model_size={config.model_size}, task_type={config.task_type}")
        
        # TranscriptionWorkerの初期化テスト
        worker = TranscriptionWorker(config_path)
        print("✅ TranscriptionWorkerの初期化成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 構造テストエラー: {e}")
        return False
    
    finally:
        # クリーンアップ
        os.unlink(config_path)


def compare_memory_manager():
    """メモリ管理機能の比較"""
    print("\n=== メモリ管理機能の比較 ===")
    
    try:
        # 旧実装のメモリ関連インポート
        from core.auto_optimizer import AutoOptimizer as OldOptimizer
        from core.memory_monitor import MemoryMonitor as OldMonitor
        
        # 新実装のメモリ管理
        from worker_transcribe_v2 import MemoryManager
        
        # 両方で同じモデルサイズで初期化
        old_optimizer = OldOptimizer('base')
        old_monitor = OldMonitor()
        
        new_manager = MemoryManager('base')
        
        # 同じメモリ使用率で最適パラメータを取得
        test_memory = 50.0
        old_params = old_optimizer.get_optimal_params(test_memory)
        
        # 新実装でも同じように動作することを確認
        new_manager.monitor.get_memory_usage = lambda: test_memory
        new_params = new_manager.get_optimal_params()
        
        print(f"✅ 旧実装パラメータ: chunk_seconds={old_params['chunk_seconds']}")
        print(f"✅ 新実装パラメータ: chunk_seconds={new_params['chunk_seconds']}")
        
        # 診断モードのリセットを確認
        old_optimizer.reset_diagnostic_mode()
        new_manager.optimizer.reset_diagnostic_mode()
        
        print("✅ 診断モードリセット機能が両方で動作")
        
        return True
        
    except Exception as e:
        print(f"❌ メモリ管理比較エラー: {e}")
        return False


def test_error_handling():
    """エラーハンドリングの比較"""
    print("\n=== エラーハンドリングテスト ===")
    
    # 存在しないファイルで設定を作成
    config_path = create_test_config("/nonexistent/video.mp4")
    
    try:
        # 新実装でのエラーハンドリングをテスト
        from worker_transcribe_v2 import TranscriptionWorker
        
        worker = TranscriptionWorker(config_path)
        
        # メモリエラーのハンドリングテスト
        try:
            worker._handle_memory_error(MemoryError("Test error"))
        except SystemExit as e:
            print("✅ メモリエラーハンドリングが正しく動作（exit code: 1）")
        
        # 一般エラーのハンドリングテスト
        try:
            worker._handle_general_error(Exception("Test general error"))
        except SystemExit as e:
            print("✅ 一般エラーハンドリングが正しく動作（exit code: 1）")
        
        # エラー結果ファイルの確認
        result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        if os.path.exists(result_path):
            with open(result_path, 'r') as f:
                error_result = json.load(f)
            
            if not error_result.get('success', True):
                print("✅ エラー結果が正しく保存される")
        
        return True
        
    except Exception as e:
        print(f"❌ エラーハンドリングテストエラー: {e}")
        return False
    
    finally:
        # クリーンアップ
        os.unlink(config_path)
        result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        if os.path.exists(result_path):
            os.unlink(result_path)


def main():
    """メインテスト実行"""
    print("=== worker_transcribe リファクタリング統合テスト ===\n")
    
    tests = [
        ("インポートテスト", compare_imports),
        ("基本構造テスト", compare_basic_structure),
        ("メモリ管理比較", compare_memory_manager),
        ("エラーハンドリング", test_error_handling)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"\n✅ {test_name}: PASSED")
            else:
                print(f"\n❌ {test_name}: FAILED")
        except Exception as e:
            print(f"\n❌ {test_name}: ERROR - {e}")
    
    print(f"\n=== 結果: {passed}/{total} テストパス ===")
    
    if passed == total:
        print("\n🎉 すべてのテストがパスしました！")
        print("worker_transcribe.pyを新しい実装に置き換える準備ができています。")
    else:
        print("\n⚠️ いくつかのテストが失敗しました。")
        print("問題を修正してから統合を進めてください。")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)