#!/usr/bin/env python3
"""
スモークテスト - CIで基本的な動作確認を行う

このテストはGitHub ActionsのCIで実行され、
アプリケーションの基本的な健全性を確認します。
"""
import sys
import subprocess


def test_imports():
    """必要なモジュールがインポートできることを確認"""
    print("Testing imports...")
    try:
        # コアモジュール
        import core.transcription
        import core.video
        import core.export
        import core.text_processor
        import core.auto_optimizer
        import core.transcription_smart_boundary
        
        # DIコンテナ
        import di.containers
        
        # プレゼンテーション層
        import presentation.presenters.main
        import presentation.views.main
        
        # アダプター
        import adapters.gateways.transcription.transcription_gateway
        
        # 設定
        import config
        
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def test_ffmpeg_available():
    """FFmpegが利用可能かを確認"""
    print("\nTesting FFmpeg availability...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True)
        if result.returncode == 0:
            print("✓ FFmpeg is available")
            return True
        else:
            print("✗ FFmpeg returned non-zero exit code")
            return False
    except FileNotFoundError:
        print("✗ FFmpeg not found")
        return False


def test_config_loading():
    """設定が正しく読み込めることを確認"""
    print("\nTesting configuration loading...")
    try:
        from config import Config
        config = Config()
        
        # 基本的な設定項目の確認
        assert hasattr(config, 'transcription')
        assert hasattr(config.transcription, 'model_size')
        assert hasattr(config.transcription, 'language')
        
        print("✓ Configuration loaded successfully")
        return True
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def test_vad_implementation():
    """VADベース実装の基本確認"""
    print("\nTesting VAD implementation...")
    try:
        from core.auto_optimizer import AutoOptimizer
        from core.constants import ChunkSizeLimits
        
        # AutoOptimizerの初期化
        optimizer = AutoOptimizer("medium")
        
        # 基本的なパラメータ確認
        params = optimizer.get_optimal_params(50.0)
        assert 'chunk_seconds' in params
        assert 'compute_type' in params
        assert params['chunk_seconds'] <= ChunkSizeLimits.MAXIMUM  # 30秒以下
        
        print("✓ VAD implementation check passed")
        return True
    except Exception as e:
        print(f"✗ VAD implementation error: {e}")
        return False


def test_di_container():
    """DIコンテナの初期化確認"""
    print("\nTesting DI container...")
    try:
        from di.containers import Container
        container = Container()
        
        # 基本的なプロバイダーの確認
        assert hasattr(container, 'gateways')
        assert hasattr(container, 'use_cases')
        assert hasattr(container, 'presenters')
        
        print("✓ DI container initialized successfully")
        return True
    except Exception as e:
        print(f"✗ DI container error: {e}")
        return False


def main():
    """スモークテストを実行"""
    print("Running TextffCut smoke tests...\n")
    
    tests = [
        test_imports,
        test_ffmpeg_available,
        test_config_loading,
        test_vad_implementation,
        test_di_container,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"✗ Unexpected error in {test.__name__}: {e}")
            results.append(False)
    
    # 結果の集計
    passed = sum(results)
    total = len(results)
    
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'='*50}")
    
    # すべてのテストが成功した場合のみ0を返す
    if passed == total:
        print("\n✓ All smoke tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()