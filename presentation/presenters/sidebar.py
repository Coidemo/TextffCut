"""
サイドバーのPresenter

サイドバーのビジネスロジックを担当します。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.interfaces.error_handler import IErrorHandler
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.base import BasePresenter
from presentation.view_models.sidebar import SidebarViewModel
from use_cases.interfaces.file_gateway import IFileGateway

logger = logging.getLogger(__name__)


class SidebarPresenter(BasePresenter[SidebarViewModel]):
    """
    サイドバーのPresenter

    リカバリー、プロセス管理、設定などのビジネスロジックを担当します。
    """

    def __init__(
        self,
        view_model: SidebarViewModel,
        session_manager: SessionManager,
        file_gateway: IFileGateway,
        error_handler: IErrorHandler,
    ):
        """
        初期化

        Args:
            view_model: サイドバーViewModel
            session_manager: セッション管理
            file_gateway: ファイルゲートウェイ
            error_handler: エラーハンドラー
        """
        super().__init__(view_model)
        self.session_manager = session_manager
        self.file_gateway = file_gateway
        self.error_handler = error_handler

        # リカバリーディレクトリ
        self.recovery_dir = Path("recovery")

        # 設定ファイルパス
        self.settings_file = Path("settings.json")

    def initialize(self) -> None:
        """初期化処理"""
        try:
            # リカバリー状態を確認
            self._check_recovery_files()

            # 設定を読み込み
            self._load_settings()

            # APIキーマネージャーから保存済みキーを読み込み
            # 注意: settings.jsonではなく、暗号化されたファイルを優先
            from utils.api_key_manager import api_key_manager

            saved_key = api_key_manager.load_api_key()
            if saved_key:
                self.view_model.api_key = saved_key
            else:
                # 暗号化ファイルがない場合は、ViewModelからもクリア
                self.view_model.api_key = None

            # プロセス状態を初期化
            self.view_model.update_process_status("ready", "準備完了")

        except Exception as e:
            self.handle_error(e, "サイドバー初期化")

    def _check_recovery_files(self) -> None:
        """リカバリーファイルを確認"""
        try:
            if not self.recovery_dir.exists():
                return

            recovery_items = []

            # リカバリーファイルを検索
            for file in self.recovery_dir.glob("recovery_*.json"):
                try:
                    with open(file, encoding="utf-8") as f:
                        data = json.load(f)
                        recovery_items.append(
                            {
                                "file": file,
                                "timestamp": data.get("timestamp"),
                                "step": data.get("current_step"),
                                "video_path": data.get("video_path"),
                            }
                        )
                except Exception as e:
                    logger.warning(f"リカバリーファイル読み込みエラー: {file}, {e}")

            # 最新のものから順にソート
            recovery_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            # 最新のタイムスタンプ
            latest_timestamp = None
            if recovery_items:
                latest_timestamp = recovery_items[0].get("timestamp")

            # ViewModelを更新
            self.view_model.update_recovery_state(recovery_items, latest_timestamp)

        except Exception as e:
            logger.error(f"リカバリーファイル確認エラー: {e}")

    def _load_settings(self) -> None:
        """設定を読み込み"""
        try:
            if not self.settings_file.exists():
                return

            with open(self.settings_file, encoding="utf-8") as f:
                settings = json.load(f)

            # 無音検出設定
            silence_settings = settings.get("silence_detection", {})
            self.view_model.update_silence_settings(
                enabled=silence_settings.get("enabled", False),
                threshold=silence_settings.get("threshold", -35.0),
                min_duration=silence_settings.get("min_duration", 0.3),
                pad_start=silence_settings.get("pad_start", 0.3),
                pad_end=silence_settings.get("pad_end", 0.3),
            )

            # API設定
            api_settings = settings.get("api", {})
            self.view_model.update_api_settings(
                use_api=api_settings.get("use_api", False),
                # APIキーは暗号化ファイルから読み込むため、ここでは設定しない
                api_key=None,
                model=api_settings.get("model", "whisper-1"),
            )

            # 高度な設定
            advanced_settings = settings.get("advanced", {})
            self.view_model.update_advanced_settings(
                model_size=advanced_settings.get("model_size", "medium"),
                language=advanced_settings.get("language", "ja"),
                compute_type=advanced_settings.get("compute_type", "float16"),
                device=advanced_settings.get("device", "cuda"),
            )

        except Exception as e:
            logger.warning(f"設定ファイル読み込みエラー: {e}")

    def save_settings(self) -> bool:
        """
        設定を保存

        Returns:
            成功したかどうか
        """
        try:
            settings = {
                "silence_detection": {
                    "enabled": self.view_model.remove_silence_enabled,
                    "threshold": self.view_model.silence_threshold,
                    "min_duration": self.view_model.min_silence_duration,
                    "pad_start": self.view_model.silence_pad_start,
                    "pad_end": self.view_model.silence_pad_end,
                },
                "api": {
                    "use_api": self.view_model.use_api,
                    # APIキーは暗号化ファイルで管理するため、settings.jsonには保存しない
                    # "api_key": self.view_model.api_key,
                    "model": self.view_model.api_model,
                },
                "advanced": {
                    "model_size": self.view_model.model_size,
                    "language": self.view_model.audio_language,
                    "compute_type": self.view_model.whisper_compute_type,
                    "device": self.view_model.whisper_device,
                },
            }

            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            self.handle_error(e, "設定保存")
            return False

    def save_recovery_state(self) -> bool:
        """
        リカバリー状態を保存

        Returns:
            成功したかどうか
        """
        try:
            # リカバリーディレクトリを作成
            self.recovery_dir.mkdir(exist_ok=True)

            # 現在の状態を収集
            recovery_data = {
                "timestamp": datetime.now().isoformat(),
                "current_step": self.session_manager.get("current_step", "video_input"),
                "video_path": self.session_manager.get_video_path(),
                "transcription_result": self.session_manager.get_transcription_result(),
                "edited_text": self.session_manager.get_edited_text(),
                "time_ranges": self._serialize_time_ranges(self.session_manager.get_time_ranges()),
                "adjusted_time_ranges": self._serialize_time_ranges(self.session_manager.get("adjusted_time_ranges")),
            }

            # ファイルに保存
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            recovery_file = self.recovery_dir / f"recovery_{timestamp_str}.json"

            with open(recovery_file, "w", encoding="utf-8") as f:
                json.dump(recovery_data, f, ensure_ascii=False, indent=2)

            # 古いリカバリーファイルを削除（最新5個を保持）
            self._cleanup_old_recovery_files()

            # リカバリー状態を更新
            self._check_recovery_files()

            return True

        except Exception as e:
            self.handle_error(e, "リカバリー状態保存")
            return False

    def _serialize_time_ranges(self, time_ranges: list[Any] | None) -> list[dict[str, float]] | None:
        """時間範囲をシリアライズ"""
        if not time_ranges:
            return None

        serialized = []
        for tr in time_ranges:
            if hasattr(tr, "start") and hasattr(tr, "end"):
                serialized.append({"start": tr.start, "end": tr.end})
            elif isinstance(tr, dict):
                serialized.append(tr)

        return serialized

    def _cleanup_old_recovery_files(self) -> None:
        """古いリカバリーファイルを削除"""
        try:
            # すべてのリカバリーファイルを取得
            files = sorted(self.recovery_dir.glob("recovery_*.json"), reverse=True)

            # 最新5個以外を削除
            for file in files[5:]:
                file.unlink()

        except Exception as e:
            logger.warning(f"リカバリーファイルクリーンアップエラー: {e}")

    def load_recovery_state(self, recovery_item: dict[str, Any]) -> bool:
        """
        リカバリー状態を読み込み

        Args:
            recovery_item: リカバリーアイテム

        Returns:
            成功したかどうか
        """
        try:
            recovery_file = recovery_item.get("file")
            if not recovery_file or not recovery_file.exists():
                self.view_model.set_error("リカバリーファイルが見つかりません")
                return False

            with open(recovery_file, encoding="utf-8") as f:
                recovery_data = json.load(f)

            # SessionManagerに復元
            if recovery_data.get("video_path"):
                self.session_manager.set("video_path", recovery_data["video_path"])

            if recovery_data.get("transcription_result"):
                self.session_manager.set_transcription_result(recovery_data["transcription_result"])

            if recovery_data.get("edited_text"):
                self.session_manager.set_edited_text(recovery_data["edited_text"])

            if recovery_data.get("time_ranges"):
                # TimeRangeオブジェクトに変換
                from domain.value_objects.time_range import TimeRange

                time_ranges = [TimeRange(tr["start"], tr["end"]) for tr in recovery_data["time_ranges"]]
                self.session_manager.set_time_ranges(time_ranges)

            if recovery_data.get("adjusted_time_ranges"):
                from domain.value_objects.time_range import TimeRange

                adjusted_ranges = [TimeRange(tr["start"], tr["end"]) for tr in recovery_data["adjusted_time_ranges"]]
                self.session_manager.set("adjusted_time_ranges", adjusted_ranges)

            # 現在のステップを設定
            current_step = recovery_data.get("current_step", "video_input")
            self.session_manager.set("current_step", current_step)

            logger.info(f"リカバリー状態を復元しました: {recovery_file}")
            return True

        except Exception as e:
            self.handle_error(e, "リカバリー状態読み込み")
            return False

    def update_process_status(self, status: str, message: str = "", details: list[str] = None) -> None:
        """
        プロセス状態を更新

        Args:
            status: 状態 (ready, running, stopped)
            message: メッセージ
            details: 詳細情報のリスト
        """
        self.view_model.update_process_status(status, message, details)

    def toggle_silence_removal(self, enabled: bool) -> None:
        """無音削除の有効/無効を切り替え"""
        self.view_model.remove_silence_enabled = enabled
        self.view_model.notify()
        self.save_settings()

    def update_silence_threshold(self, threshold: float) -> None:
        """無音閾値を更新"""
        self.view_model.silence_threshold = threshold
        self.view_model.notify()
        self.save_settings()

    def toggle_api_mode(self, use_api: bool) -> None:
        """APIモードの有効/無効を切り替え"""
        self.view_model.use_api = use_api
        self.view_model.notify()
        self.save_settings()

    def set_api_key(self, api_key: str) -> bool:
        """APIキーを設定"""
        try:
            # APIキーマネージャーを使用して保存
            from utils.api_key_manager import api_key_manager

            if api_key_manager.save_api_key(api_key):
                self.view_model.api_key = api_key
                self.view_model.notify()
                return True
            return False
        except Exception as e:
            self.handle_error(e, "APIキー保存")
            return False

    def delete_api_key(self) -> bool:
        """APIキーを削除"""
        try:
            import streamlit as st

            from utils.api_key_manager import api_key_manager

            # 削除を実行
            result = api_key_manager.delete_api_key()

            # 成功/失敗に関わらずViewModelをクリア
            # （ファイルが既に削除されている場合もクリアすべき）
            self.view_model.api_key = None
            self.view_model.use_api = False  # APIモードも無効化
            self.view_model.notify()

            # セッション状態もクリア
            if "api_key" in st.session_state:
                del st.session_state.api_key

            # 設定を保存（APIキーがNoneの状態で）
            self.save_settings()

            return result
        except Exception as e:
            self.handle_error(e, "APIキー削除")
            return False

    def set_model_size(self, model_size: str) -> None:
        """モデルサイズを設定"""
        self.view_model.model_size = model_size
        self.view_model.notify()
        self.save_settings()

    def handle_error(self, error: Exception, context: str) -> None:
        """
        エラーをハンドリング

        Args:
            error: 発生したエラー
            context: エラーのコンテキスト
        """
        logger.error(f"{context}でエラーが発生しました: {error}", exc_info=True)
        error_message = self.error_handler.handle_error(error)
        self.view_model.set_error(f"{context}: {error_message}")

    def reset(self) -> None:
        """状態をリセット"""
        self.view_model.reset()
