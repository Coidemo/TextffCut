#!/usr/bin/env python3
"""
サービス層統合テスト

main.pyでのサービス層統合が正しく動作することを確認。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from services import (
    ConfigurationService,
    TextEditingService,
    VideoProcessingService,
    ExportService,
    WorkflowService
)
from core import TranscriptionSegment
from core.models import WordInfo
from ui import SessionStateAdapter


def test_configuration_service():
    """ConfigurationServiceのテスト"""
    print("=== ConfigurationServiceテスト ===")
    
    config = Config()
    service = ConfigurationService(config)
    
    # 料金計算テスト
    print("\n1. 料金計算テスト")
    result = service.calculate_api_cost(10.5)  # 10.5分
    if result.success:
        data = result.data
        print(f"✅ 料金計算成功")
        print(f"   USD: ${data['cost_usd']:.3f}")
        print(f"   JPY: {data['cost_jpy']:.0f}円")
    else:
        print(f"❌ エラー: {result.error}")
    
    # モデル検証テスト
    print("\n2. モデル検証テスト")
    result = service.validate_model_settings(
        model_size="large-v3",
        use_api=False,
        available_memory_gb=8.0  # 8GB（警告が出るはず）
    )
    if result.success:
        data = result.data
        print(f"✅ 検証成功")
        print(f"   Valid: {data['valid']}")
        print(f"   Warnings: {data['warnings']}")
        print(f"   Memory Status: {data['memory_status']}")
    else:
        print(f"❌ エラー: {result.error}")
    
    # 出力パス生成テスト
    print("\n3. 出力パス生成テスト")
    result = service.get_output_path(
        video_path="/Users/test/video.mp4",
        process_type="clip",
        output_format="fcpxml"
    )
    if result.success:
        data = result.data
        print(f"✅ パス生成成功")
        print(f"   Output Path: {data['output_path']}")
        print(f"   File Name: {data['file_name']}")
    else:
        print(f"❌ エラー: {result.error}")


def test_session_state_adapter():
    """SessionStateAdapterのテスト"""
    print("\n\n=== SessionStateAdapterテスト ===")
    
    # モックセッション状態
    mock_session_state = {
        'current_video_path': '/test/video.mp4',
        'use_api': False,
        'local_model_size': 'medium',
        'remove_silence': True,
        'silence_threshold': -35.0
    }
    
    adapter = SessionStateAdapter(mock_session_state)
    
    # ワークフロー設定の取得
    print("\n1. ワークフロー設定の取得")
    settings = adapter.get_workflow_settings()
    print(f"✅ 設定取得成功")
    print(f"   Model Size: {settings.model_size}")
    print(f"   Use API: {settings.use_api}")
    print(f"   Remove Silence: {settings.remove_silence}")
    
    # 処理状態の取得
    print("\n2. 処理状態の取得")
    processing_state = adapter.get_processing_state()
    print(f"✅ 状態取得成功")
    print(f"   Use API: {processing_state.use_api}")
    print(f"   Model Size: {processing_state.local_model_size}")
    print(f"   Silence Threshold: {processing_state.silence_threshold}")


def test_imports():
    """インポートテスト"""
    print("=== インポートテスト ===")
    
    try:
        # main.pyで使用される新しいインポートをテスト
        from services import (
            ConfigurationService,
            TextEditingService,
            VideoProcessingService,
            ExportService,
            WorkflowService
        )
        from ui import SessionStateAdapter
        from core import TranscriptionSegment
        print("✅ すべてのインポートが成功しました")
        return True
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        return False


def test_text_editing_service():
    """TextEditingServiceのテスト"""
    print("\n\n=== TextEditingServiceテスト ===")
    
    config = Config()
    service = TextEditingService(config)
    
    # テストセグメント（wordsを含む）
    segments = [
        TranscriptionSegment(
            start=0.0,
            end=5.0,
            text="これはテストです",
            words=[
                WordInfo(word="これは", start=0.0, end=1.0),
                WordInfo(word="テスト", start=1.0, end=3.0),
                WordInfo(word="です", start=3.0, end=5.0)
            ]
        ),
        TranscriptionSegment(
            start=5.0,
            end=10.0,
            text="サービス層のテスト",
            words=[
                WordInfo(word="サービス層の", start=5.0, end=7.0),
                WordInfo(word="テスト", start=7.0, end=10.0)
            ]
        )
    ]
    
    # 差分検出テスト
    print("\n1. 差分検出テスト")
    result = service.find_differences(
        segments,
        "これはテストです"
    )
    if result.success:
        print(f"✅ 差分検出成功")
        print(f"   差分セグメント数: {len(result.data)}")
        print(f"   メタデータ: {result.metadata}")
    else:
        print(f"❌ エラー: {result.error}")


def test_video_processing_service():
    """VideoProcessingServiceのテスト（基本的な初期化のみ）"""
    print("\n\n=== VideoProcessingServiceテスト ===")
    
    config = Config()
    service = VideoProcessingService(config)
    print("✅ VideoProcessingService初期化成功")


def test_export_service():
    """ExportServiceのテスト（基本的な初期化のみ）"""
    print("\n\n=== ExportServiceテスト ===")
    
    config = Config()
    service = ExportService(config)
    print("✅ ExportService初期化成功")


def main():
    """メインテスト実行"""
    print("=== サービス層統合テスト開始 ===\n")
    
    # インポートテスト
    if not test_imports():
        print("\nインポートに失敗したため、テストを中止します")
        return
    
    # 各テストを実行
    test_configuration_service()
    test_session_state_adapter()
    test_text_editing_service()
    test_video_processing_service()
    test_export_service()
    
    print("\n\n=== テスト完了 ===")


if __name__ == "__main__":
    main()