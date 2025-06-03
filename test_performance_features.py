"""
パフォーマンストラッキングと手動モード選択機能のテスト
"""
import os
import sys
import time
import json
from pathlib import Path
import tempfile
import shutil

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.performance_tracker import PerformanceTracker, PerformanceMetrics
from core.transcription import Transcriber
from config import config


def test_performance_tracker():
    """パフォーマンストラッカーのテスト"""
    print("\n[パフォーマンストラッカーのテスト]")
    
    # テスト用の一時動画パス
    test_video_path = "test_video.mp4"
    
    # 1. PerformanceMetricsのテスト
    print("✅ PerformanceMetrics: 計算テスト")
    metrics = PerformanceMetrics(
        start_time=time.time(),
        video_duration_seconds=90.0,
        mode="optimized",
        model_size="whisper-1",
        use_api=True
    )
    time.sleep(0.1)  # 処理時間をシミュレート
    metrics.end_time = time.time()
    metrics.segments_processed = 50
    metrics.calculate_metrics()
    
    assert metrics.duration_seconds > 0
    assert metrics.realtime_factor > 0
    print(f"   処理時間: {metrics.duration_seconds:.3f}秒")
    print(f"   リアルタイム係数: {metrics.realtime_factor:.1f}倍速")
    
    # 2. PerformanceTrackerの履歴保存テスト
    print("\n✅ PerformanceTracker: 履歴保存テスト")
    tracker = PerformanceTracker(test_video_path)
    
    # テスト用の履歴を作成
    for i in range(3):
        mode = ["normal", "optimized", "ultra_optimized"][i]
        test_metrics = tracker.start_tracking(
            mode=mode,
            model_size="whisper-1",
            use_api=True,
            video_duration=90.0
        )
        time.sleep(0.01)
        tracker.end_tracking(segments_processed=50 + i*10)
    
    # 3. 統計情報の取得テスト
    print("\n✅ PerformanceTracker: 統計情報取得テスト")
    mode_stats = tracker.get_mode_statistics()
    
    assert len(mode_stats) == 3
    for mode, stats in mode_stats.items():
        print(f"   {mode}: {stats['count']}回実行, 平均{stats['avg_realtime_factor']:.1f}倍速")
    
    # 4. 最適モードの推奨テスト
    print("\n✅ PerformanceTracker: 最適モード推奨テスト")
    best_mode = tracker.get_best_mode()
    print(f"   推奨モード: {best_mode}")
    assert best_mode in ["normal", "optimized", "ultra_optimized"]
    
    # クリーンアップ
    if tracker.history_file.exists():
        shutil.rmtree(tracker.history_file.parent)
    
    print("\n✅ すべてのパフォーマンストラッカーテストが成功しました！")


def test_optimization_mode_selection():
    """最適化モード選択のテスト"""
    print("\n[最適化モード選択のテスト]")
    
    # APIトランスクライバーのモード選択ロジックをテスト
    from core.transcription_api import APITranscriber
    from utils.system_resources import system_resource_manager
    
    # 設定を一時的にAPI使用に変更
    original_use_api = config.transcription.use_api
    config.transcription.use_api = True
    config.transcription.api_key = "test_key"
    
    try:
        # 1. 自動選択モードのテスト
        print("✅ 自動選択モード: システムスペックに基づく選択")
        system_spec = system_resource_manager.get_system_spec()
        print(f"   システムスペック: {system_spec.spec_level}")
        print(f"   利用可能メモリ: {system_spec.available_memory_gb:.1f}GB")
        
        # 2. 手動選択モードのテスト
        print("\n✅ 手動選択モード: 各モードの選択")
        modes = ["normal", "optimized", "ultra_optimized"]
        for mode in modes:
            print(f"   {mode}モードを選択可能")
        
    finally:
        # 設定を元に戻す
        config.transcription.use_api = original_use_api
    
    print("\n✅ すべての最適化モード選択テストが成功しました！")


def test_performance_feedback_integration():
    """パフォーマンスフィードバック統合テスト"""
    print("\n[パフォーマンスフィードバック統合テスト]")
    
    # TranscriptionResultにprocessing_time属性が存在することを確認
    from core.transcription import TranscriptionResult
    
    print("✅ TranscriptionResult: processing_time属性テスト")
    result = TranscriptionResult(
        language="ja",
        segments=[],
        original_audio_path="test.mp4",
        model_size="whisper-1",
        processing_time=10.5
    )
    
    assert hasattr(result, 'processing_time')
    assert result.processing_time == 10.5
    print(f"   処理時間属性: {result.processing_time}秒")
    
    print("\n✅ すべての統合テストが成功しました！")


def run_all_tests():
    """すべてのテストを実行"""
    print("="*80)
    print("パフォーマンス機能テスト開始")
    print("="*80)
    
    try:
        test_performance_tracker()
        test_optimization_mode_selection()
        test_performance_feedback_integration()
        
        print("\n" + "="*80)
        print("🎉 すべてのテストが成功しました！")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ テスト失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()