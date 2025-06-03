"""
簡易パフォーマンステスト（既存キャッシュを利用）
"""
import os
import time
import json
from pathlib import Path
from datetime import datetime

# 環境変数設定
os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"  # 低スペックモードを強制

import logging
logging.basicConfig(level=logging.INFO)

from utils.system_resources import system_resource_manager
from core.disk_cache_manager import DiskCacheManager
from core.segment_splitter import SegmentSplitter

def test_ultra_optimization_modules():
    """超最適化モジュールのテスト"""
    print("\n" + "="*80)
    print("超最適化モジュールのパフォーマンステスト")
    print("="*80)
    
    # 1. システムリソース確認
    print("\n1. システムリソース確認（強制低スペックモード）")
    spec = system_resource_manager.get_system_spec()
    print(f"  スペックレベル: {spec.spec_level}")
    print(f"  メモリ: {spec.total_memory_gb:.1f}GB (利用可能: {spec.available_memory_gb:.1f}GB)")
    print(f"  推奨API並列数: {spec.recommended_api_workers}")
    print(f"  推奨アライメント並列数: {spec.recommended_align_workers}")
    print(f"  推奨チャンクサイズ: {spec.recommended_chunk_seconds}秒")
    
    # 2. ディスクキャッシュマネージャーテスト
    print("\n2. ディスクキャッシュマネージャーテスト")
    cache_manager = DiskCacheManager()
    
    # 大量のダミーセグメントを作成
    dummy_segments = []
    for i in range(130):  # 65分÷30秒 = 130チャンク相当
        segments = []
        for j in range(10):  # 各チャンクに10セグメント
            segments.append({
                "start": i * 30 + j * 3,
                "end": i * 30 + (j + 1) * 3,
                "text": f"これはチャンク{i}のセグメント{j}のテストテキストです。"
            })
        dummy_segments.append(segments)
    
    # キャッシュへの書き込みテスト
    start_time = time.time()
    for i, segments in enumerate(dummy_segments):
        cache_manager.save_api_result(i, segments)
    write_time = time.time() - start_time
    
    cache_size = cache_manager.get_cache_size_mb()
    print(f"  書き込み時間: {write_time:.2f}秒 ({len(dummy_segments)}チャンク)")
    print(f"  キャッシュサイズ: {cache_size:.2f}MB")
    
    # キャッシュからの読み込みテスト
    start_time = time.time()
    loaded_segments = []
    for i in range(len(dummy_segments)):
        segments = cache_manager.load_api_result(i)
        if segments:
            loaded_segments.extend(segments)
    read_time = time.time() - start_time
    
    print(f"  読み込み時間: {read_time:.2f}秒 ({len(loaded_segments)}セグメント)")
    
    # 3. セグメントスプリッターテスト
    print("\n3. セグメントスプリッターテスト")
    splitter = SegmentSplitter()
    
    # 長いセグメントを作成
    long_segments = [{
        "start": 0,
        "end": 45,  # 45秒の長いセグメント
        "text": "これは非常に長いセグメントです。" * 20
    }]
    
    start_time = time.time()
    split_segments = splitter.split_segments(long_segments, 30)
    split_time = time.time() - start_time
    
    print(f"  分割前: {len(long_segments)}セグメント")
    print(f"  分割後: {len(split_segments)}セグメント")
    print(f"  処理時間: {split_time:.3f}秒")
    
    # クリーンアップ
    cache_manager.cleanup()
    
    # 4. メモリプレッシャーシミュレーション
    print("\n4. メモリプレッシャー検出テスト")
    is_pressure = system_resource_manager.check_memory_pressure()
    print(f"  メモリプレッシャー: {'あり' if is_pressure else 'なし'}")
    
    current_api = 10
    current_align = 3
    new_api, new_align = system_resource_manager.adjust_workers_for_memory(current_api, current_align)
    if new_api != current_api:
        print(f"  ワーカー調整: API {current_api}→{new_api}, アライメント {current_align}→{new_align}")
    else:
        print(f"  ワーカー調整: 不要")
    
    print("\n" + "="*80)
    print("パフォーマンステスト完了")
    print("="*80)


if __name__ == "__main__":
    test_ultra_optimization_modules()