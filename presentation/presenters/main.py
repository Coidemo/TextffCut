"""
メイン画面のPresenter

アプリケーション全体のビジネスロジックとワークフローを管理します。
"""

import logging
from pathlib import Path
from typing import Any

from domain.interfaces.error_handler import IErrorHandler
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.presenters.transcription import TranscriptionPresenter
from presentation.presenters.video_input import VideoInputPresenter
from presentation.view_models.main import MainViewModel

logger = logging.getLogger(__name__)


class MainPresenter:
    """
    メイン画面のPresenter

    各MVPコンポーネントを統合し、アプリケーション全体のワークフローを管理します。
    """

    def __init__(
        self,
        view_model: MainViewModel,
        video_input_presenter: VideoInputPresenter,
        transcription_presenter: TranscriptionPresenter,
        text_editor_presenter: TextEditorPresenter,
        export_settings_presenter: ExportSettingsPresenter,
        session_manager: SessionManager,
        error_handler: IErrorHandler,
    ):
        """
        初期化

        Args:
            view_model: メインのViewModel
            video_input_presenter: 動画入力のPresenter
            transcription_presenter: 文字起こしのPresenter
            text_editor_presenter: テキスト編集のPresenter
            export_settings_presenter: エクスポート設定のPresenter
            session_manager: セッション管理
            error_handler: エラーハンドリング
        """
        self.view_model = view_model
        self.video_input_presenter = video_input_presenter
        self.transcription_presenter = transcription_presenter
        self.text_editor_presenter = text_editor_presenter
        self.export_settings_presenter = export_settings_presenter
        self.session_manager = session_manager
        self.error_handler = error_handler

        # ワークフロー状態の初期化
        self._initialize_workflow_state()

        # 各Presenterのイベントをサブスクライブ
        self._subscribe_to_events()

    def _initialize_workflow_state(self) -> None:
        """ワークフロー状態の初期化"""
        # セッションマネージャーから既存の状態を復元
        video_path_str = self.session_manager.get_video_path()
        if video_path_str:
            video_path = Path(video_path_str)
            duration = self.session_manager.get("video_duration", 0.0)
            video_input_completed = self.session_manager.get("video_input_completed", False)

            # ViewModelに状態を復元
            if video_input_completed and duration > 0:
                self.view_model.complete_video_input(video_path, duration)
                logger.info(f"セッションから動画入力状態を復元: {video_path}")

        if self.session_manager.get_transcription_result():
            self.view_model.complete_transcription()
            logger.info("セッションから文字起こし状態を復元")

        # テキスト編集完了フラグが明示的に設定されている場合のみ遷移
        if self.session_manager.get("text_edit_completed", False):
            self.view_model.complete_text_edit()
            logger.info("セッションからテキスト編集状態を復元")

        # 初期化完了
        self.view_model.is_initialized = True

    def _subscribe_to_events(self) -> None:
        """各Presenterのイベントをサブスクライブ"""
        # オブザーバーとして自分自身を登録する必要がある
        # ただし、ViewModelObserverプロトコルを実装する必要がある
        pass  # 一時的に無効化

    def _on_video_input_changed(self) -> None:
        """動画入力の変更イベントハンドラ"""
        try:
            vm = self.video_input_presenter.view_model
            if vm.file_path and vm.is_valid:
                # 動画入力が完了
                self.view_model.complete_video_input(vm.file_path, vm.duration)

                # SessionManagerに保存
                self.session_manager.set_video_path(str(vm.file_path))
                self.session_manager.set("video_duration", vm.duration)
                self.session_manager.set("video_input_completed", True)

                logger.info(f"動画入力完了: {vm.file_path}")
        except Exception as e:
            self._handle_error("動画入力の処理中にエラーが発生しました", e)

    def _on_transcription_changed(self) -> None:
        """文字起こしの変更イベントハンドラ"""
        try:
            vm = self.transcription_presenter.view_model
            if vm.has_result and vm.transcription_result:
                # 文字起こしが完了
                self.view_model.complete_transcription()
                logger.info("文字起こし完了")
        except Exception as e:
            self._handle_error("文字起こしの処理中にエラーが発生しました", e)

    def _on_text_editor_changed(self) -> None:
        """テキスト編集の変更イベントハンドラ"""
        try:
            vm = self.text_editor_presenter.view_model
            if vm.has_edited_text:
                # テキスト編集が完了
                self.view_model.complete_text_edit()
                logger.info("テキスト編集完了")
        except Exception as e:
            self._handle_error("テキスト編集の処理中にエラーが発生しました", e)

    def _on_export_settings_changed(self) -> None:
        """エクスポート設定の変更イベントハンドラ"""
        try:
            vm = self.export_settings_presenter.view_model
            if vm.export_results:
                # エクスポートが完了
                self.view_model.complete_export()
                logger.info(f"エクスポート完了: {len(vm.export_results)}ファイル")
        except Exception as e:
            self._handle_error("エクスポートの処理中にエラーが発生しました", e)

    def _handle_error(self, message: str, error: Exception) -> None:
        """エラーハンドリング"""
        logger.error(f"{message}: {error}", exc_info=True)
        error_message = self.error_handler.handle_error(error, context=message)
        self.view_model.set_error(error_message, context=message)

    def navigate_to_step(self, step: str) -> None:
        """
        指定されたステップに移動

        Args:
            step: 移動先のステップ (video_input, transcription, text_edit, export)
        """
        try:
            # 移動可能かチェック
            if step == "transcription" and not self.view_model.can_proceed_to_transcription:
                self.view_model.set_error("動画を選択してください")
                return

            if step == "text_edit" and not self.view_model.can_proceed_to_text_edit:
                self.view_model.set_error("文字起こしを完了してください")
                return

            if step == "export" and not self.view_model.can_proceed_to_export:
                self.view_model.set_error("テキスト編集を完了してください")
                return

            # ステップを変更
            self.view_model.set_current_step(step)
            logger.info(f"ステップ変更: {step}")

        except Exception as e:
            self._handle_error("ステップ変更中にエラーが発生しました", e)

    def reset_workflow(self) -> None:
        """ワークフローをリセット"""
        try:
            # 各Presenterをリセット
            self.video_input_presenter.reset()
            self.transcription_presenter.reset()
            self.text_editor_presenter.reset()
            self.export_settings_presenter.reset()

            # SessionManagerをクリア
            self.session_manager.clear()

            # MainViewModelをリセット
            self.view_model.reset_workflow()

            logger.info("ワークフローをリセットしました")

        except Exception as e:
            self._handle_error("ワークフローのリセット中にエラーが発生しました", e)

    def handle_help_toggle(self) -> None:
        """ヘルプ表示の切り替え"""
        self.view_model.toggle_help()

    def handle_settings_toggle(self) -> None:
        """設定表示の切り替え"""
        self.view_model.toggle_settings()

    def handle_dark_mode_toggle(self, enabled: bool) -> None:
        """ダークモードの切り替え"""
        self.view_model.set_dark_mode(enabled)
        # TODO: 実際のダークモード切り替え処理を実装

    def get_current_presenter(self) -> Any | None:
        """
        現在のステップに対応するPresenterを取得

        Returns:
            現在のステップのPresenter
        """
        presenter_map = {
            "video_input": self.video_input_presenter,
            "transcription": self.transcription_presenter,
            "text_edit": self.text_editor_presenter,
            "export": self.export_settings_presenter,
        }
        return presenter_map.get(self.view_model.current_step)

    def validate_workflow_state(self) -> bool:
        """
        ワークフロー状態の整合性を検証

        Returns:
            整合性が取れている場合True
        """
        # MainViewModelの検証
        validation_error = self.view_model.validate()
        if validation_error:
            logger.warning(f"MainViewModelの検証に失敗しました: {validation_error}")
            return False

        # 各Presenterの状態との整合性チェック
        if self.view_model.video_input_completed:
            if not self.video_input_presenter.view_model.is_valid:
                logger.warning("動画入力の状態が不整合です")
                return False

        if self.view_model.transcription_completed:
            if not self.transcription_presenter.view_model.has_result:
                logger.warning("文字起こしの状態が不整合です")
                return False

        if self.view_model.text_edit_completed:
            if not self.text_editor_presenter.view_model.has_edited_text:
                logger.warning("テキスト編集の状態が不整合です")
                return False

        return True

    def initialize_step(self, step: str) -> None:
        """
        指定されたステップを初期化

        Args:
            step: 初期化するステップ
        """
        try:
            if step == "video_input":
                self.video_input_presenter.initialize()
            elif step == "transcription":
                self.transcription_presenter.initialize()
            elif step == "text_edit":
                # SessionManagerから文字起こし結果を取得
                transcription_result = self.session_manager.get_transcription_result()
                if transcription_result:
                    self.text_editor_presenter.initialize(transcription_result)
                else:
                    logger.warning("文字起こし結果が見つかりません")
            elif step == "export":
                self.export_settings_presenter.initialize()

            logger.info(f"ステップ初期化完了: {step}")

        except Exception as e:
            self._handle_error(f"{step}の初期化中にエラーが発生しました", e)

    def get_workflow_summary(self) -> dict:
        """
        ワークフローの現在状態のサマリーを取得

        Returns:
            ワークフロー状態のサマリー
        """
        return {
            "current_step": self.view_model.current_step,
            "progress": self.view_model.workflow_progress,
            "video_selected": bool(self.view_model.video_path),
            "transcription_done": self.view_model.transcription_completed,
            "text_edited": self.view_model.text_edit_completed,
            "export_done": self.view_model.export_completed,
            "has_error": self.view_model.has_error,
        }
