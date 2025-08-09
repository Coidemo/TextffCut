"""
クリーンアーキテクチャの統合テスト

各層が正しく連携して動作することを確認します。
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from di.bootstrap import bootstrap_di
from domain.entities.text_difference import DifferenceType, TextDifference
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.value_objects.duration import Duration
from domain.value_objects.time_range import TimeRange
from use_cases.transcription.transcribe_video import TranscribeVideoRequest


class TestCleanArchitectureFlow:
    """クリーンアーキテクチャの統合フローテスト"""

    @pytest.fixture
    def app_container(self):
        """DIコンテナを初期化"""
        container = bootstrap_di()
        return container

    @pytest.fixture
    def sample_video_path(self):
        """テスト用の動画パスを作成"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            return Path(f.name)

    @pytest.fixture
    def sample_transcription_result(self):
        """サンプルの文字起こし結果を作成"""
        segments = [
            TranscriptionSegment(id="seg1", start=0.0, end=5.0, text="これはテストです。"),
            TranscriptionSegment(id="seg2", start=5.0, end=10.0, text="統合テストを実行しています。"),
            TranscriptionSegment(id="seg3", start=10.0, end=15.0, text="クリーンアーキテクチャの確認。"),
        ]
        return TranscriptionResult(
            segments=segments, language="ja", duration=Duration(seconds=15.0), model_size="medium"
        )

    def test_video_input_to_transcription_flow(self, app_container, sample_video_path, sample_transcription_result):
        """動画入力から文字起こしまでのフローをテスト"""
        # Gatewayをモック
        with patch.object(
            app_container.gateways.transcription_gateway(), "transcribe", return_value=sample_transcription_result
        ):
            # PresenterとUseCaseを取得
            presentation = app_container.presentation()
            video_input_presenter = presentation.video_input_presenter()
            transcription_presenter = presentation.transcription_presenter()

            # 動画を選択
            video_input_presenter.handle_video_selection(str(sample_video_path))
            assert video_input_presenter.view_model.has_video is True
            assert video_input_presenter.view_model.video_path == sample_video_path

            # 文字起こしを実行
            transcription_presenter.initialize(sample_video_path)
            transcription_presenter.start_transcription("medium", "ja")

            # 結果を確認
            assert transcription_presenter.view_model.has_transcription is True
            assert transcription_presenter.view_model.transcription_result is not None
            assert len(transcription_presenter.view_model.transcription_result.segments) == 3

    def test_transcription_to_text_editing_flow(self, app_container, sample_transcription_result):
        """文字起こしからテキスト編集までのフローをテスト"""
        # Gatewayをモック
        mock_text_diff = TextDifference(
            original_text="これはテストです。統合テストを実行しています。クリーンアーキテクチャの確認。",
            edited_text="統合テストを実行しています。",
            differences=[
                (DifferenceType.DELETED, "これはテストです。", 0),
                (DifferenceType.UNCHANGED, "統合テストを実行しています。", 1),
                (DifferenceType.DELETED, "クリーンアーキテクチャの確認。", 2),
            ],
        )

        with (
            patch.object(
                app_container.gateways.text_processor_gateway(), "find_differences", return_value=mock_text_diff
            ),
            patch.object(
                app_container.gateways.text_processor_gateway(),
                "get_time_ranges_from_differences",
                return_value=[TimeRange(start=5.0, end=10.0)],
            ),
        ):
            # PresenterとUseCaseを取得
            presentation = app_container.presentation()
            text_editor_presenter = presentation.text_editor_presenter()

            # 文字起こし結果を設定してテキスト編集を初期化
            text_editor_presenter.initialize(sample_transcription_result)

            # テキストを編集
            edited_text = "統合テストを実行しています。"
            text_editor_presenter.update_edited_text(edited_text)

            # 結果を確認
            assert text_editor_presenter.view_model.has_edited_text is True
            assert text_editor_presenter.view_model.edited_text == edited_text
            assert len(text_editor_presenter.view_model.time_ranges) == 1
            assert text_editor_presenter.view_model.time_ranges[0].start == 5.0
            assert text_editor_presenter.view_model.time_ranges[0].end == 10.0

    def test_text_editing_to_export_flow(self, app_container, sample_video_path, sample_transcription_result):
        """テキスト編集からエクスポートまでのフローをテスト"""
        time_ranges = [TimeRange(start=5.0, end=10.0), TimeRange(start=15.0, end=20.0)]

        # モックの設定
        with patch.object(
            app_container.gateways.fcpxml_export_gateway(), "export", return_value=Path("/tmp/output.fcpxml")
        ) as mock_export:
            # PresenterとUseCaseを取得
            presentation = app_container.presentation()
            export_presenter = presentation.export_settings_presenter()

            # エクスポート設定を初期化
            export_presenter.initialize(
                video_path=sample_video_path, time_ranges=time_ranges, transcription_result=sample_transcription_result
            )

            # FCPXMLエクスポートを実行
            export_presenter.export_fcpxml(output_path=Path("/tmp/output.fcpxml"), remove_silence=False)

            # エクスポートが呼ばれたことを確認
            mock_export.assert_called_once()
            assert export_presenter.view_model.export_completed is True

    def test_complete_workflow_with_silence_removal(
        self, app_container, sample_video_path, sample_transcription_result
    ):
        """無音削除を含む完全なワークフローをテスト"""
        # 各種モックの設定
        with (
            patch.object(
                app_container.gateways.transcription_gateway(), "transcribe", return_value=sample_transcription_result
            ),
            patch.object(
                app_container.gateways.text_processor_gateway(),
                "find_differences",
                return_value=TextDifference(
                    original_text="これはテストです。統合テストを実行しています。",
                    edited_text="統合テストを実行しています。",
                    differences=[(DifferenceType.UNCHANGED, "統合テストを実行しています。", 1)],
                ),
            ),
            patch.object(
                app_container.gateways.text_processor_gateway(),
                "get_time_ranges_from_differences",
                return_value=[TimeRange(start=5.0, end=10.0)],
            ),
            patch.object(app_container.gateways.video_processor_gateway(), "extract_audio_segment", return_value=None),
            patch.object(
                app_container.gateways.video_processor_gateway(),
                "detect_silence_in_audio",
                return_value=[{"start": 2.0, "end": 3.0, "duration": 1.0}],
            ),
            patch.object(app_container.gateways.video_export_gateway(), "export", return_value=Path("/tmp/output.mp4")),
        ):
            # MainPresenterを取得
            presentation = app_container.presentation()
            main_presenter = presentation.main_presenter()

            # ワークフロー全体を実行
            # 1. 動画選択
            video_input_presenter = presentation.video_input_presenter()
            video_input_presenter.handle_video_selection(str(sample_video_path))

            # 2. 文字起こし
            transcription_presenter = presentation.transcription_presenter()
            transcription_presenter.initialize(sample_video_path)
            transcription_presenter.start_transcription("medium", "ja")

            # 3. テキスト編集
            text_editor_presenter = presentation.text_editor_presenter()
            text_editor_presenter.initialize(sample_transcription_result)
            text_editor_presenter.update_edited_text("統合テストを実行しています。")

            # 4. エクスポート（無音削除あり）
            export_presenter = presentation.export_settings_presenter()
            export_presenter.initialize(
                video_path=sample_video_path,
                time_ranges=[TimeRange(start=5.0, end=10.0)],
                transcription_result=sample_transcription_result,
            )
            export_presenter.export_video(
                output_path=Path("/tmp/output.mp4"), remove_silence=True, silence_threshold=-40.0
            )

            # 全体の状態を確認
            summary = main_presenter.get_workflow_summary()
            assert summary["video_selected"] is True
            assert summary["transcription_completed"] is True
            assert summary["text_edited"] is True
            assert summary["completed_steps_count"] >= 3

    def test_error_handling_across_layers(self, app_container, sample_video_path):
        """各層でのエラーハンドリングをテスト"""
        # 文字起こしでエラーを発生させる
        with patch.object(
            app_container.gateways.transcription_gateway(), "transcribe", side_effect=Exception("Transcription failed")
        ):
            presentation = app_container.presentation()
            transcription_presenter = presentation.transcription_presenter()

            # エラーが適切に処理されることを確認
            try:
                transcription_presenter.start_transcription("medium", "ja")
            except Exception:
                # エラーが伝搬されることを確認
                pass

            # エラーメッセージが設定されることを確認
            assert transcription_presenter.view_model.error_message is not None
            assert "Transcription failed" in transcription_presenter.view_model.error_message
            assert transcription_presenter.view_model.has_transcription is False

    def test_dependency_injection_integrity(self, app_container):
        """依存性注入の整合性をテスト"""
        # 同じインスタンスが共有されていることを確認
        gateways = app_container.gateways()
        use_cases = app_container.use_cases()

        # Gatewayがシングルトンであることを確認
        gateway1 = gateways.transcription_gateway()
        gateway2 = gateways.transcription_gateway()
        assert gateway1 is gateway2

        # UseCaseは毎回新しいインスタンスであることを確認
        use_case1 = use_cases.transcribe_video()
        use_case2 = use_cases.transcribe_video()
        assert use_case1 is not use_case2

        # しかし、同じGatewayを使用していることを確認
        assert use_case1.transcription_gateway is use_case2.transcription_gateway

    def test_session_management(self, app_container):
        """セッション管理の動作をテスト"""
        presentation = app_container.presentation()
        session_manager = presentation.session_manager()

        # データの保存と取得
        session_manager.set("test_key", "test_value")
        assert session_manager.get("test_key") == "test_value"

        # データのクリア
        session_manager.clear()
        assert session_manager.get("test_key") is None

    def test_concurrent_operations(self, app_container, sample_video_path):
        """並行操作の安全性をテスト"""
        import threading

        results = []
        errors = []

        def transcribe_task():
            try:
                use_cases = app_container.use_cases()
                use_case = use_cases.transcribe_video()
                request = TranscribeVideoRequest(video_path=sample_video_path, model_size="medium")
                response = use_case.execute(request)
                results.append(response)
            except Exception as e:
                errors.append(e)

        # 複数のスレッドで同時実行
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=transcribe_task)
            threads.append(thread)
            thread.start()

        # 全スレッドの完了を待つ
        for thread in threads:
            thread.join()

        # エラーがないことを確認
        assert len(errors) == 0
        # 全ての操作が完了していることを確認
        assert len(results) == 5
