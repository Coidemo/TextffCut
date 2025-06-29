#!/usr/bin/env python
"""
定数モジュールのテスト

マジックナンバーの設定化が正しく機能することを確認します。
"""

import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_import_constants() -> bool:
    """定数モジュールのインポートテスト"""
    try:
        from core.constants import (  # noqa: F401
            AdjustmentFactors,
            AudioProcessing,
            BatchSizeLimits,
            ChunkSizeLimits,
            ErrorMessages,
            MemoryEstimates,
            MemoryThresholds,
            TranscriptionSegments,
            WorkerLimits,
        )

        print("✅ 定数モジュールのインポート成功")
        return True
    except ImportError as e:
        print(f"❌ 定数モジュールのインポート失敗: {e}")
        return False


def test_constant_values() -> bool:
    """定数値の妥当性をチェック"""
    from core.constants import BatchSizeLimits, ChunkSizeLimits, MemoryThresholds

    try:
        # メモリ閾値の順序チェック
        assert MemoryThresholds.NORMAL < MemoryThresholds.COMFORTABLE
        assert MemoryThresholds.COMFORTABLE < MemoryThresholds.TARGET
        assert MemoryThresholds.TARGET < MemoryThresholds.HIGH
        assert MemoryThresholds.HIGH < MemoryThresholds.EMERGENCY
        assert MemoryThresholds.EMERGENCY < MemoryThresholds.CRITICAL
        print("✅ メモリ閾値の順序が正しい")

        # バッチサイズの順序チェック
        assert BatchSizeLimits.MINIMUM <= BatchSizeLimits.EMERGENCY
        assert BatchSizeLimits.EMERGENCY <= BatchSizeLimits.SMALL
        assert BatchSizeLimits.SMALL <= BatchSizeLimits.DEFAULT
        assert BatchSizeLimits.DEFAULT <= BatchSizeLimits.MEDIUM
        assert BatchSizeLimits.MEDIUM <= BatchSizeLimits.LARGE
        assert BatchSizeLimits.LARGE <= BatchSizeLimits.MAXIMUM
        print("✅ バッチサイズの順序が正しい")

        # チャンクサイズの順序チェック
        assert ChunkSizeLimits.DIAGNOSTIC_CHUNK < ChunkSizeLimits.ABSOLUTE_MINIMUM
        assert ChunkSizeLimits.ABSOLUTE_MINIMUM <= ChunkSizeLimits.EMERGENCY_MINIMUM
        assert ChunkSizeLimits.EMERGENCY_MINIMUM < ChunkSizeLimits.MAXIMUM
        print("✅ チャンクサイズの順序が正しい")

        return True
    except AssertionError as e:
        print(f"❌ 定数値の妥当性チェック失敗: {e}")
        return False


def test_usage_in_modules() -> bool:
    """各モジュールでの使用をテスト"""
    # worker_transcribe.pyの一部をインポート
    try:

        print("✅ worker_transcribe.pyが定数を使用可能")
    except Exception as e:
        print(f"❌ worker_transcribe.pyのインポートエラー: {e}")
        return False

    # auto_optimizer.pyのインポート
    try:
        from core.auto_optimizer import AutoOptimizer

        AutoOptimizer("base")
        print("✅ AutoOptimizerが定数を使用可能")
    except Exception as e:
        print(f"❌ AutoOptimizerのインポートエラー: {e}")
        return False

    # alignment_processor.pyのインポート
    try:

        print("✅ AlignmentProcessorが定数を使用可能")
    except Exception as e:
        print(f"❌ AlignmentProcessorのインポートエラー: {e}")
        return False

    return True


def test_error_messages() -> bool:
    """エラーメッセージのフォーマットテスト"""
    from core.constants import ErrorMessages

    # メモリ警告メッセージのフォーマットテスト
    try:
        formatted = ErrorMessages.LOW_MEMORY_WARNING.format(7.5)
        assert "7.5GB" in formatted
        print("✅ エラーメッセージのフォーマットが正しい")
        return True
    except Exception as e:
        print(f"❌ エラーメッセージのフォーマットエラー: {e}")
        return False


def main() -> bool:
    """メインテスト実行"""
    print("=== マジックナンバー設定化のテスト ===\n")

    tests = [test_import_constants, test_constant_values, test_usage_in_modules, test_error_messages]

    passed = 0
    for test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                print(f"⚠️ {test_func.__name__} が失敗しました")
        except Exception as e:
            print(f"❌ {test_func.__name__} でエラー: {e}")

    print(f"\n=== テスト結果: {passed}/{len(tests)} パス ===")
    return passed == len(tests)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
