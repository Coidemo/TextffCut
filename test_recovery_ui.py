"""
リカバリーUIの動作確認テスト

StreamlitアプリケーションでリカバリーUIが
正しく動作することを確認する。
"""

import sys
from pathlib import Path
from typing import Any

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.processing_state_manager import ProcessingStateManager
from utils.logging import get_logger

logger = get_logger(__name__)


def create_test_states() -> None:
    """テスト用の状態ファイルを作成"""
    print("=== Creating Test States ===")

    state_manager = ProcessingStateManager()

    # テスト用の状態を作成
    test_videos: list[dict[str, Any]] = [
        {
            "path": "/videos/test_video1.mp4",
            "state": "transcribing",
            "progress": 0.45,
            "data": {
                "total_chunks": 10,
                "chunks": [{"text": f"Chunk {i}"} for i in range(4)],
                "model_size": "medium",
                "language": "ja",
            },
        },
        {
            "path": "/videos/test_video2.mp4",
            "state": "processing",
            "progress": 0.8,
            "data": {
                "step": "exporting",
                "format": "fcpxml",
            },
        },
        {
            "path": "/videos/test_video3.mp4",
            "state": "error",
            "progress": 0.2,
            "data": {
                "error": "メモリ不足エラー",
                "task_id": "test_task_3",
            },
        },
    ]

    for video_info in test_videos:
        state_manager.save_state(video_info["path"], video_info["state"], video_info["data"], video_info["progress"])
        print(f"✓ Created state for {Path(video_info['path']).name} ({video_info['state']})")

    print("\nTest states created successfully!")
    print("\nTo test the recovery UI:")
    print("1. Run: streamlit run main.py")
    print("2. Check the '🔄 リカバリー' tab in the sidebar")
    print("3. Check the '📋 履歴' tab to see all states")
    print("4. Try processing /videos/test_video1.mp4 to see recovery prompt")


def cleanup_test_states() -> None:
    """テスト用の状態ファイルをクリーンアップ"""
    print("\n=== Cleaning Up Test States ===")

    state_manager = ProcessingStateManager()

    test_videos = [
        "/videos/test_video1.mp4",
        "/videos/test_video2.mp4",
        "/videos/test_video3.mp4",
    ]

    for video_path in test_videos:
        state_manager.clear_state(video_path)
        print(f"✓ Cleared state for {Path(video_path).name}")

    print("\nTest states cleaned up!")


def test_recovery_component() -> None:
    """リカバリーコンポーネントの単体テスト"""
    print("\n=== Testing Recovery Components ===")

    # 状態マネージャーを初期化
    state_manager = ProcessingStateManager()

    # テスト動画パス
    test_video = "/test/recovery_test.mp4"

    # 1. 状態の保存
    print("\n--- Save State ---")
    state_manager.save_state(
        test_video,
        "transcribing",
        {
            "total_chunks": 5,
            "chunks": [{"text": f"Chunk {i}"} for i in range(2)],
            "model_size": "medium",
        },
        progress=0.4,
    )
    print("✓ State saved")

    # 2. 状態の読み込み
    print("\n--- Load State ---")
    loaded_state = state_manager.load_state(test_video)
    if loaded_state:
        print(f"✓ State loaded: {loaded_state['state']} ({loaded_state['progress']:.0%})")

    # 3. リカバリー情報の確認
    print("\n--- Check Recovery ---")
    from orchestrator.processing_state_manager import TranscriptionRecovery

    recovery = TranscriptionRecovery(state_manager)
    recovery_info = recovery.check_recovery(test_video)

    if recovery_info:
        print(f"✓ Recovery available: {recovery_info['message']}")
        print(f"  Can resume: {recovery_info['can_resume']}")
        print(f"  Progress: {recovery_info['progress']:.0%}")

    # 4. クリーンアップ
    print("\n--- Cleanup ---")
    state_manager.clear_state(test_video)
    print("✓ State cleared")


def main() -> None:
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description="Recovery UI Test")
    parser.add_argument("--create", action="store_true", help="Create test states")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup test states")
    parser.add_argument("--test", action="store_true", help="Run component tests")

    args = parser.parse_args()

    if args.create:
        create_test_states()
    elif args.cleanup:
        cleanup_test_states()
    elif args.test:
        test_recovery_component()
    else:
        # デフォルト：テスト状態を作成
        create_test_states()
        print("\n" + "=" * 50)
        print("Run with --cleanup to remove test states")
        print("Run with --test to test components")


if __name__ == "__main__":
    main()
