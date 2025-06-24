"""
処理状態の永続化とリカバリー

Docker環境での処理中断時に状態を保存し、
再起動後に処理を再開できるようにする。
"""

import json
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging import get_logger

logger = get_logger(__name__)


class ProcessingStateManager:
    """処理状態の永続化とリカバリー"""

    def __init__(self, state_dir: Path | None = None):
        """初期化

        Args:
            state_dir: 状態ファイルの保存ディレクトリ
        """
        # Docker環境かどうかを判定
        is_docker = Path("/.dockerenv").exists()
        
        if state_dir:
            self.state_dir = state_dir
        elif is_docker:
            self.state_dir = Path("/app/state")
        else:
            # ローカル環境では一時ディレクトリを使用
            self.state_dir = Path.home() / ".textffcut" / "state"
            
        self.state_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ProcessingStateManager initialized with state_dir: {self.state_dir}")

    def save_state(
        self,
        video_path: str,
        state: str,  # "transcribing", "processing", "exporting"
        data: dict[str, Any],
        progress: float = 0.0,
    ) -> None:
        """処理状態を保存

        Args:
            video_path: 動画ファイルパス
            state: 処理状態
            data: 状態データ
            progress: 進捗率（0.0-1.0）
        """
        state_id = self._generate_state_id(video_path)
        state_file = self.state_dir / f"{state_id}.state"

        state_data = {
            "video_path": video_path,
            "state": state,
            "progress": progress,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        try:
            # JSON形式で保存
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            logger.info(f"State saved: {video_path} ({state}, {progress:.1%})")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def load_state(self, video_path: str) -> dict[str, Any] | None:
        """処理状態を読み込み

        Args:
            video_path: 動画ファイルパス

        Returns:
            状態データまたはNone
        """
        state_id = self._generate_state_id(video_path)
        state_file = self.state_dir / f"{state_id}.state"

        if not state_file.exists():
            return None

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # タイムスタンプをチェック（24時間以内）
            timestamp = datetime.fromisoformat(state_data["timestamp"])
            if datetime.now() - timestamp > timedelta(hours=24):
                logger.info(f"State file is too old: {video_path}")
                self.clear_state(video_path)
                return None

            logger.info(f"State loaded: {video_path} ({state_data['state']}, {state_data['progress']:.1%})")
            return state_data

        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def clear_state(self, video_path: str) -> None:
        """状態ファイルを削除

        Args:
            video_path: 動画ファイルパス
        """
        state_id = self._generate_state_id(video_path)
        state_file = self.state_dir / f"{state_id}.state"

        if state_file.exists():
            try:
                state_file.unlink()
                logger.info(f"State cleared: {video_path}")
            except Exception as e:
                logger.error(f"Failed to clear state: {e}")

    def list_states(self) -> list[dict[str, Any]]:
        """保存されているすべての状態をリスト

        Returns:
            状態データのリスト
        """
        states = []

        for state_file in self.state_dir.glob("*.state"):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)

                # タイムスタンプをチェック
                timestamp = datetime.fromisoformat(state_data["timestamp"])
                if datetime.now() - timestamp <= timedelta(hours=24):
                    states.append(state_data)

            except Exception as e:
                logger.error(f"Failed to read state file {state_file}: {e}")

        # タイムスタンプで降順ソート（新しいものが先）
        states.sort(key=lambda x: x["timestamp"], reverse=True)

        return states

    def cleanup_old_states(self, hours: int = 24) -> int:
        """古い状態ファイルをクリーンアップ

        Args:
            hours: 保持する時間（デフォルト24時間）

        Returns:
            削除したファイル数
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        deleted_count = 0

        for state_file in self.state_dir.glob("*.state"):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)

                timestamp = datetime.fromisoformat(state_data["timestamp"])
                if timestamp < cutoff_time:
                    state_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old state file: {state_file.name}")

            except Exception as e:
                logger.error(f"Failed to process state file {state_file}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old state files")

        return deleted_count

    def _generate_state_id(self, video_path: str) -> str:
        """動画パスから状態IDを生成

        Args:
            video_path: 動画ファイルパス

        Returns:
            状態ID（ファイル名として使用）
        """
        import hashlib

        # ファイルパスをハッシュ化
        hasher = hashlib.sha256()
        hasher.update(video_path.encode("utf-8"))

        # ファイル名も含める
        file_name = Path(video_path).name
        hasher.update(file_name.encode("utf-8"))

        # ファイルサイズも含める（存在する場合）
        try:
            file_size = Path(video_path).stat().st_size
            hasher.update(str(file_size).encode())
        except:
            pass

        return hasher.hexdigest()[:16]  # 最初の16文字を使用


class TranscriptionRecovery:
    """文字起こし処理のリカバリー"""

    def __init__(self, state_manager: ProcessingStateManager):
        """初期化

        Args:
            state_manager: 状態管理オブジェクト
        """
        self.state_manager = state_manager
        self.logger = get_logger(__name__)

    def check_recovery(self, video_path: str) -> dict[str, Any] | None:
        """リカバリー可能な状態があるかチェック

        Args:
            video_path: 動画ファイルパス

        Returns:
            リカバリー情報またはNone
        """
        state = self.state_manager.load_state(video_path)

        if not state:
            return None

        # 24時間以内の状態のみリカバリー対象
        timestamp = datetime.fromisoformat(state["timestamp"])
        if datetime.now() - timestamp > timedelta(hours=24):
            self.state_manager.clear_state(video_path)
            return None

        # 処理中断状態かチェック
        if state["state"] in ["transcribing", "processing"]:
            return {
                "video_path": video_path,
                "state": state["state"],
                "progress": state["progress"],
                "data": state["data"],
                "can_resume": True,
                "message": f"前回の処理が{state['progress']:.0%}まで完了しています。続きから再開しますか？",
            }

        return None

    def save_chunk_progress(
        self, video_path: str, chunk_index: int, total_chunks: int, chunk_data: dict[str, Any]
    ) -> None:
        """チャンクごとの進捗を保存

        Args:
            video_path: 動画ファイルパス
            chunk_index: 現在のチャンクインデックス
            total_chunks: 総チャンク数
            chunk_data: チャンクデータ
        """
        state = self.state_manager.load_state(video_path) or {"data": {}}

        # チャンクデータを更新
        if "chunks" not in state["data"]:
            state["data"]["chunks"] = []

        # チャンクを追加または更新
        while len(state["data"]["chunks"]) <= chunk_index:
            state["data"]["chunks"].append(None)

        state["data"]["chunks"][chunk_index] = chunk_data

        # 進捗率を計算
        completed_chunks = sum(1 for chunk in state["data"]["chunks"] if chunk is not None)
        progress = completed_chunks / total_chunks

        # 状態を保存
        self.state_manager.save_state(video_path, "transcribing", state["data"], progress)

    def get_pending_chunks(self, video_path: str, total_chunks: int) -> list[int]:
        """未処理のチャンクインデックスを取得

        Args:
            video_path: 動画ファイルパス
            total_chunks: 総チャンク数

        Returns:
            未処理チャンクのインデックスリスト
        """
        state = self.state_manager.load_state(video_path)

        if not state or "chunks" not in state.get("data", {}):
            # すべてのチャンクが未処理
            return list(range(total_chunks))

        chunks = state["data"]["chunks"]
        pending = []

        for i in range(total_chunks):
            if i >= len(chunks) or chunks[i] is None:
                pending.append(i)

        return pending

    def resume_transcription(self, video_path: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """文字起こしを再開

        Args:
            video_path: 動画ファイルパス
            data: リカバリーデータ

        Returns:
            再開情報またはNone
        """
        # 処理済みチャンクを確認
        processed_chunks = data.get("chunks", [])
        total_chunks = data.get("total_chunks", 0)

        if processed_chunks:
            self.logger.info(f"Resuming transcription from chunk {len(processed_chunks)}/{total_chunks}")
            return self._continue_chunk_processing(video_path, data)
        else:
            return self._resume_from_extraction(video_path, data)

    def _continue_chunk_processing(self, video_path: str, data: dict[str, Any]) -> dict[str, Any]:
        """チャンク処理を継続

        Args:
            video_path: 動画ファイルパス
            data: リカバリーデータ

        Returns:
            再開情報
        """
        return {
            "action": "continue_chunks",
            "processed_chunks": data.get("chunks", []),
            "total_chunks": data.get("total_chunks", 0),
            "audio_path": data.get("audio_path"),
            "model_config": data.get("model_config", {}),
        }

    def _resume_from_extraction(self, video_path: str, data: dict[str, Any]) -> dict[str, Any]:
        """音声抽出から再開

        Args:
            video_path: 動画ファイルパス
            data: リカバリーデータ

        Returns:
            再開情報
        """
        return {
            "action": "extract_audio",
            "video_path": video_path,
            "model_config": data.get("model_config", {}),
        }


def check_and_recover_on_startup() -> list[dict[str, Any]]:
    """Docker再起動時のリカバリー処理

    Returns:
        リカバリー可能な処理のリスト
    """
    state_manager = ProcessingStateManager()
    recovery = TranscriptionRecovery(state_manager)

    # 古い状態ファイルをクリーンアップ
    state_manager.cleanup_old_states()

    # リカバリー可能な処理をリスト
    recoverable = []

    for state_data in state_manager.list_states():
        video_path = state_data["video_path"]
        recovery_info = recovery.check_recovery(video_path)

        if recovery_info:
            recoverable.append(recovery_info)
            logger.info(f"Found recoverable process: {video_path} ({state_data['progress']:.0%})")

    if recoverable:
        logger.info(f"Total {len(recoverable)} recoverable processes found")
    else:
        logger.info("No recoverable processes found")

    return recoverable


# テスト用関数
def test_state_manager():
    """状態管理機能のテスト"""
    print("=== Processing State Manager Test ===")

    # テスト用ディレクトリ
    test_dir = Path("/tmp/test_state")
    test_dir.mkdir(exist_ok=True)

    state_manager = ProcessingStateManager(test_dir)
    recovery = TranscriptionRecovery(state_manager)

    # テスト動画パス
    video_path = "/test/sample_video.mp4"

    # 1. 状態の保存
    print("\n--- Save State ---")
    state_manager.save_state(
        video_path,
        "transcribing",
        {
            "total_chunks": 10,
            "chunks": [{"start": 0, "end": 60}, {"start": 60, "end": 120}],
            "audio_path": "/tmp/audio.wav",
        },
        progress=0.2,
    )
    print("✓ State saved")

    # 2. 状態の読み込み
    print("\n--- Load State ---")
    loaded_state = state_manager.load_state(video_path)
    if loaded_state:
        print(f"State: {loaded_state['state']}")
        print(f"Progress: {loaded_state['progress']:.0%}")
        print(f"Chunks: {len(loaded_state['data'].get('chunks', []))}")

    # 3. リカバリーチェック
    print("\n--- Check Recovery ---")
    recovery_info = recovery.check_recovery(video_path)
    if recovery_info:
        print(f"Can resume: {recovery_info['can_resume']}")
        print(f"Message: {recovery_info['message']}")

    # 4. チャンク進捗の保存
    print("\n--- Save Chunk Progress ---")
    for i in range(2, 5):
        recovery.save_chunk_progress(
            video_path, i, 10, {"start": i * 60, "end": (i + 1) * 60, "text": f"Chunk {i} text"}
        )
        print(f"✓ Chunk {i} saved")

    # 5. 未処理チャンクの取得
    print("\n--- Get Pending Chunks ---")
    pending = recovery.get_pending_chunks(video_path, 10)
    print(f"Pending chunks: {pending}")

    # 6. 状態のリスト
    print("\n--- List States ---")
    states = state_manager.list_states()
    print(f"Total states: {len(states)}")
    for state in states:
        print(f"  - {Path(state['video_path']).name}: {state['state']} ({state['progress']:.0%})")

    # 7. クリーンアップ
    print("\n--- Cleanup ---")
    state_manager.clear_state(video_path)
    print("✓ State cleared")

    # テストディレクトリの削除
    import shutil

    shutil.rmtree(test_dir)
    print("\n✓ Test completed!")


if __name__ == "__main__":
    test_state_manager()