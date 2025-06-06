#!/usr/bin/env python
"""
既存機能への影響をテストするスクリプト
"""

import os
import sys
from pathlib import Path
import tempfile
import json
from unittest.mock import MagicMock, patch

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_transcription_api_import():
    """文字起こしAPIモジュールのインポートテスト"""
    print("\n=== 文字起こしAPIモジュールのインポートテスト ===")
    try:
        from core.transcription_api import WhisperAPITranscriber
        print("✓ WhisperAPITranscriberのインポート成功")
        
        # 基本的なインスタンス化
        transcriber = WhisperAPITranscriber(api_key="test_key")
        print("✓ WhisperAPITranscriberのインスタンス化成功")
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_transcription_local_import():
    """ローカル文字起こしモジュールのインポートテスト"""
    print("\n=== ローカル文字起こしモジュールのインポートテスト ===")
    try:
        from core.transcription import WhisperXTranscriber
        print("✓ WhisperXTranscriberのインポート成功")
        
        # 基本的なインスタンス化（WhisperXなしでも初期化は可能）
        transcriber = WhisperXTranscriber()
        print("✓ WhisperXTranscriberのインスタンス化成功")
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_unified_transcriber():
    """統一Transcriberのテスト"""
    print("\n=== 統一Transcriberのテスト ===")
    try:
        from core.unified_transcriber import UnifiedTranscriber
        from core.models import ProcessingMode
        
        print("✓ UnifiedTranscriberのインポート成功")
        
        # APIモードでインスタンス化
        transcriber = UnifiedTranscriber(
            mode=ProcessingMode.API,
            api_key="test_key"
        )
        print("✓ APIモードでのインスタンス化成功")
        
        # ローカルモードでインスタンス化
        transcriber = UnifiedTranscriber(
            mode=ProcessingMode.LOCAL
        )
        print("✓ ローカルモードでのインスタンス化成功")
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_processor():
    """VideoProcessorの既存機能テスト"""
    print("\n=== VideoProcessorの既存機能テスト ===")
    try:
        from core.video import VideoProcessor
        print("✓ VideoProcessorのインポート成功")
        
        # テスト用の動画パス（存在しなくてもOK）
        test_path = "test_video.mp4"
        processor = VideoProcessor(test_path)
        print("✓ VideoProcessorのインスタンス化成功")
        
        # 既存メソッドの存在確認
        methods = [
            'get_video_info',
            'extract_audio',
            'detect_silence_from_wav',
            'remove_silence_new',
            'process_video'
        ]
        
        for method in methods:
            if hasattr(processor, method):
                print(f"✓ メソッド '{method}' が存在")
            else:
                print(f"✗ メソッド '{method}' が見つかりません")
                return False
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_export_functionality():
    """エクスポート機能のテスト"""
    print("\n=== エクスポート機能のテスト ===")
    try:
        from core.export import FCPXMLExporter, EDLExporter
        print("✓ エクスポートモジュールのインポート成功")
        
        # FCPXMLExporter
        fcpxml = FCPXMLExporter(
            video_path="test.mp4",
            project_name="Test Project"
        )
        print("✓ FCPXMLExporterのインスタンス化成功")
        
        # EDLExporter
        edl = EDLExporter(
            video_path="test.mp4",
            project_name="Test Project"
        )
        print("✓ EDLExporterのインスタンス化成功")
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_text_processor():
    """TextProcessorの既存機能テスト"""
    print("\n=== TextProcessorの既存機能テスト ===")
    try:
        from core.text_processor import TextProcessor
        print("✓ TextProcessorのインポート成功")
        
        # インスタンス化
        processor = TextProcessor()
        print("✓ TextProcessorのインスタンス化成功")
        
        # 既存メソッドの確認
        methods = ['find_differences', 'get_segment_ranges']
        for method in methods:
            if hasattr(processor, method):
                print(f"✓ メソッド '{method}' が存在")
            else:
                print(f"✗ メソッド '{method}' が見つかりません")
                return False
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_main_app_imports():
    """メインアプリケーションのインポートテスト"""
    print("\n=== メインアプリケーションのインポートテスト ===")
    try:
        # main.pyの主要な関数をインポート
        from main import (
            load_transcription_result,
            save_transcription_result,
            get_transcriber,
            process_with_api,
            process_with_local
        )
        print("✓ main.pyの主要関数のインポート成功")
        
        # UI関連のインポート
        from ui.components import render_header, render_transcription_section
        print("✓ UIコンポーネントのインポート成功")
        
        from ui.file_upload import render_file_upload
        print("✓ ファイルアップロードUIのインポート成功")
        
        return True
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_worker_scripts():
    """ワーカースクリプトのインポートテスト"""
    print("\n=== ワーカースクリプトのインポートテスト ===")
    
    # worker_transcribe.py
    try:
        import worker_transcribe
        print("✓ worker_transcribe.pyのインポート成功")
    except Exception as e:
        print(f"✗ worker_transcribe.pyのインポートエラー: {e}")
        return False
    
    # worker_align.py
    try:
        import worker_align
        print("✓ worker_align.pyのインポート成功")
    except Exception as e:
        print(f"✗ worker_align.pyのインポートエラー: {e}")
        return False
    
    return True


def test_backwards_compatibility():
    """後方互換性のテスト"""
    print("\n=== 後方互換性のテスト ===")
    
    # 旧形式のTranscriptionResultが読み込めるか
    try:
        from core.transcription import TranscriptionResult
        print("✓ 旧形式のTranscriptionResultクラスが存在")
        
        # to_v2_format メソッドの存在確認
        result = TranscriptionResult(segments=[], language="ja")
        if hasattr(result, 'to_v2_format'):
            print("✓ to_v2_format()メソッドが存在")
        else:
            print("✗ to_v2_format()メソッドが見つかりません")
            return False
            
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False
    
    return True


def run_all_tests():
    """全テストを実行"""
    print("="*50)
    print("既存機能への影響テスト")
    print("="*50)
    
    tests = [
        test_transcription_api_import,
        test_transcription_local_import,
        test_unified_transcriber,
        test_video_processor,
        test_export_functionality,
        test_text_processor,
        test_main_app_imports,
        test_worker_scripts,
        test_backwards_compatibility
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n✗ テスト '{test.__name__}' で予期しないエラー: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    # 結果サマリー
    print("\n" + "="*50)
    print("テスト結果サマリー")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n合計: {passed}/{total} テスト合格")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)