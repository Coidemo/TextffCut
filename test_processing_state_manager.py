"""
ProcessingStateManagerの統合テスト

処理状態の保存とリカバリー機能の動作確認。
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.processing_state_manager import (
    ProcessingStateManager,
    TranscriptionRecovery,
    check_and_recover_on_startup,
)


def test_basic_state_management():
    """基本的な状態管理のテスト"""
    print("=== Basic State Management Test ===")

    # テスト用ディレクトリ
    test_dir = Path("/tmp/test_state_basic")
    test_dir.mkdir(exist_ok=True)

    state_manager = ProcessingStateManager(test_dir)

    # テスト動画パス
    video_path = "/test/videos/sample.mp4"

    # 1. 状態の保存
    print("\n--- Save State ---")
    test_data = {"model_size": "medium", "language": "ja", "total_chunks": 5, "audio_path": "/tmp/sample_audio.wav"}

    state_manager.save_state(video_path, "transcribing", test_data, progress=0.4)
    print("✓ State saved successfully")

    # 2. 状態の読み込み
    print("\n--- Load State ---")
    loaded_state = state_manager.load_state(video_path)

    assert loaded_state is not None, "State should be loaded"
    assert loaded_state["state"] == "transcribing"
    assert loaded_state["progress"] == 0.4
    assert loaded_state["data"]["model_size"] == "medium"
    print("✓ State loaded correctly")
    print(f"  State: {loaded_state['state']}")
    print(f"  Progress: {loaded_state['progress']:.0%}")
    print(f"  Model: {loaded_state['data']['model_size']}")

    # 3. 状態のクリア
    print("\n--- Clear State ---")
    state_manager.clear_state(video_path)

    # 確認
    loaded_state = state_manager.load_state(video_path)
    assert loaded_state is None, "State should be cleared"
    print("✓ State cleared successfully")

    # クリーンアップ
    import shutil

    shutil.rmtree(test_dir)

    print("\n✓ Basic test completed!")


def test_recovery_workflow():
    """リカバリーワークフローのテスト"""
    print("\n=== Recovery Workflow Test ===")

    # テスト用ディレクトリ
    test_dir = Path("/tmp/test_state_recovery")
    test_dir.mkdir(exist_ok=True)

    state_manager = ProcessingStateManager(test_dir)
    recovery = TranscriptionRecovery(state_manager)

    video_path = "/test/videos/long_video.mp4"

    # 1. チャンクごとの進捗保存をシミュレート
    print("\n--- Simulate Chunk Processing ---")
    total_chunks = 10

    # 最初の3チャンクを処理
    for i in range(3):
        chunk_data = {
            "start": i * 60,
            "end": (i + 1) * 60,
            "text": f"This is chunk {i} transcription",
            "segments": [
                {"start": i * 60, "end": i * 60 + 30, "text": f"First half of chunk {i}"},
                {"start": i * 60 + 30, "end": (i + 1) * 60, "text": f"Second half of chunk {i}"},
            ],
        }
        recovery.save_chunk_progress(video_path, i, total_chunks, chunk_data)
        print(f"✓ Chunk {i+1}/{total_chunks} processed")
        time.sleep(0.1)  # 短い遅延

    # 2. リカバリーチェック
    print("\n--- Check Recovery ---")
    recovery_info = recovery.check_recovery(video_path)

    assert recovery_info is not None, "Recovery info should be available"
    assert recovery_info["can_resume"] is True
    assert recovery_info["progress"] == 0.3  # 3/10 = 0.3

    print("✓ Recovery check passed")
    print(f"  Message: {recovery_info['message']}")
    print(f"  Progress: {recovery_info['progress']:.0%}")

    # 3. 未処理チャンクの確認
    print("\n--- Get Pending Chunks ---")
    pending_chunks = recovery.get_pending_chunks(video_path, total_chunks)

    assert len(pending_chunks) == 7, f"Should have 7 pending chunks, got {len(pending_chunks)}"
    assert pending_chunks == [3, 4, 5, 6, 7, 8, 9]

    print(f"✓ Pending chunks: {pending_chunks}")

    # 4. 処理を再開（シミュレート）
    print("\n--- Resume Processing ---")
    resume_info = recovery.resume_transcription(video_path, recovery_info["data"])

    assert resume_info is not None
    assert resume_info["action"] == "continue_chunks"
    assert len(resume_info["processed_chunks"]) == 3

    print("✓ Resume info generated")
    print(f"  Action: {resume_info['action']}")
    print(f"  Processed chunks: {len(resume_info['processed_chunks'])}")

    # クリーンアップ
    import shutil

    shutil.rmtree(test_dir)

    print("\n✓ Recovery workflow test completed!")


def test_multiple_files_and_cleanup():
    """複数ファイルの管理とクリーンアップのテスト"""
    print("\n=== Multiple Files and Cleanup Test ===")

    # テスト用ディレクトリ
    test_dir = Path("/tmp/test_state_multiple")
    test_dir.mkdir(exist_ok=True)

    state_manager = ProcessingStateManager(test_dir)

    # 1. 複数の動画の状態を保存
    print("\n--- Save Multiple States ---")
    video_files = ["/test/video1.mp4", "/test/video2.mp4", "/test/video3.mp4"]

    for i, video_path in enumerate(video_files):
        state_manager.save_state(
            video_path,
            "processing" if i % 2 == 0 else "transcribing",
            {"index": i, "test": True},
            progress=(i + 1) / len(video_files),
        )
        print(f"✓ State saved for {Path(video_path).name}")

    # 2. 状態のリスト表示
    print("\n--- List All States ---")
    states = state_manager.list_states()

    assert len(states) == 3, f"Should have 3 states, got {len(states)}"

    for state in states:
        print(f"  - {Path(state['video_path']).name}: " f"{state['state']} ({state['progress']:.0%})")

    # 3. 古い状態ファイルのシミュレート
    print("\n--- Simulate Old State ---")

    # 25時間前の状態を手動で作成
    old_state_id = state_manager._generate_state_id("/test/old_video.mp4")
    old_state_file = state_manager.state_dir / f"{old_state_id}.state"

    old_timestamp = datetime.now() - timedelta(hours=25)
    old_state_data = {
        "video_path": "/test/old_video.mp4",
        "state": "transcribing",
        "progress": 0.5,
        "timestamp": old_timestamp.isoformat(),
        "data": {},
    }

    with open(old_state_file, "w", encoding="utf-8") as f:
        json.dump(old_state_data, f)

    print("✓ Created old state file (25 hours old)")

    # 4. クリーンアップ実行
    print("\n--- Cleanup Old States ---")
    deleted_count = state_manager.cleanup_old_states(hours=24)

    assert deleted_count == 1, f"Should delete 1 file, deleted {deleted_count}"
    print(f"✓ Cleaned up {deleted_count} old state file(s)")

    # 5. 残っている状態を確認
    print("\n--- Verify Remaining States ---")
    remaining_states = state_manager.list_states()

    assert len(remaining_states) == 3, f"Should have 3 states remaining, got {len(remaining_states)}"
    print(f"✓ {len(remaining_states)} states remaining")

    # クリーンアップ
    import shutil

    shutil.rmtree(test_dir)

    print("\n✓ Multiple files test completed!")


def test_startup_recovery():
    """起動時のリカバリーチェックのテスト"""
    print("\n=== Startup Recovery Test ===")

    # テスト用ディレクトリ
    test_dir = Path("/tmp/test_state_startup")
    test_dir.mkdir(exist_ok=True)

    # ProcessingStateManagerのデフォルトディレクトリを一時的に変更
    import orchestrator.processing_state_manager as psm

    original_init = psm.ProcessingStateManager.__init__

    def mock_init(self, state_dir=None):
        original_init(self, test_dir)

    psm.ProcessingStateManager.__init__ = mock_init

    try:
        state_manager = ProcessingStateManager()

        # 1. リカバリー可能な状態を作成
        print("\n--- Create Recoverable States ---")

        # 処理中の動画1
        state_manager.save_state(
            "/videos/processing_video.mp4",
            "transcribing",
            {
                "total_chunks": 20,
                "chunks": [{"data": f"chunk_{i}"} for i in range(5)],
                "model_config": {"model_size": "medium", "language": "ja"},
            },
            progress=0.25,
        )

        # 処理中の動画2
        state_manager.save_state("/videos/another_video.mp4", "processing", {"step": "silence_removal"}, progress=0.6)

        # 完了済みの動画（リカバリー対象外）
        state_manager.save_state("/videos/completed_video.mp4", "completed", {}, progress=1.0)

        print("✓ Created 3 state files (2 recoverable, 1 completed)")

        # 2. 起動時リカバリーチェック
        print("\n--- Check Startup Recovery ---")
        recoverable = check_and_recover_on_startup()

        assert len(recoverable) == 2, f"Should find 2 recoverable processes, found {len(recoverable)}"

        print(f"✓ Found {len(recoverable)} recoverable processes:")
        for rec in recoverable:
            print(f"  - {Path(rec['video_path']).name}: " f"{rec['state']} ({rec['progress']:.0%})")

        # 3. リカバリー情報の検証
        print("\n--- Verify Recovery Info ---")

        # 最初のリカバリー可能プロセスを確認
        first_recovery = recoverable[0]
        assert first_recovery["can_resume"] is True
        assert "message" in first_recovery

        print("✓ Recovery info is valid")
        print(f"  First recovery message: {first_recovery['message']}")

    finally:
        # モックを元に戻す
        psm.ProcessingStateManager.__init__ = original_init

        # クリーンアップ
        import shutil

        shutil.rmtree(test_dir)

    print("\n✓ Startup recovery test completed!")


def run_all_tests():
    """すべてのテストを実行"""
    print("=== ProcessingStateManager Integration Tests ===\n")

    tests = [
        ("Basic State Management", test_basic_state_management),
        ("Recovery Workflow", test_recovery_workflow),
        ("Multiple Files and Cleanup", test_multiple_files_and_cleanup),
        ("Startup Recovery", test_startup_recovery),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ {test_name} failed: {e}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"Tests passed: {passed}/{len(tests)}")
    print(f"Tests failed: {failed}/{len(tests)}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
