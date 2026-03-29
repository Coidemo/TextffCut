"""
BatchTranscribeUseCase のユニットテスト

TranscriptionGateway をモックして、バッチ処理ロジックのみを検証する。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.transcription.batch_transcribe import (
    BatchItemResult,
    BatchProgress,
    BatchTranscribeRequest,
    BatchTranscribeResult,
    BatchTranscribeUseCase,
)


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gateway():
    """モックの TranscriptionGateway"""
    gateway = MagicMock()
    gateway.get_available_models.return_value = [
        "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"
    ]
    return gateway


@pytest.fixture
def mock_transcription_result():
    """ダミーの TranscriptionResult"""
    result = MagicMock(spec=TranscriptionResult)
    result.language = "ja"
    result.segments = []
    result.model_size = "medium"
    result.processing_time = 10.0
    return result


@pytest.fixture
def tmp_video_files(tmp_path):
    """一時ディレクトリに空の動画ファイルを作成する"""
    files = []
    for name in ["video1.mp4", "video2.mp4", "video3.mp4"]:
        f = tmp_path / name
        f.write_bytes(b"dummy")
        files.append(f)
    return files


# ---------------------------------------------------------------------------
# 基本動作テスト
# ---------------------------------------------------------------------------

class TestBatchTranscribeBasic:

    def test_empty_paths_raises_error(self, mock_gateway):
        """対象ファイルが空のときはエラーになる"""
        use_case = BatchTranscribeUseCase(mock_gateway)
        request = BatchTranscribeRequest(video_paths=[])

        with pytest.raises(Exception, match="処理対象"):
            use_case(request)

    def test_single_file_success(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """1ファイルの正常処理"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        # _single_use_case.execute を直接モックして TranscribeVideoUseCase の検証をバイパス
        with patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
            )
            result = use_case(request)

        assert result.total == 1
        assert result.succeeded == 1
        assert result.failed == 0
        assert result.skipped == 0

    def test_multiple_files_all_success(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """複数ファイルの全件成功"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        with patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
            )
            result = use_case(request)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0


# ---------------------------------------------------------------------------
# キャッシュスキップテスト
# ---------------------------------------------------------------------------

class TestBatchTranscribeCache:

    def test_skip_when_cache_exists(self, mock_gateway, tmp_video_files):
        """キャッシュがある場合はスキップされる"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        with patch.object(use_case, "_cache_exists", return_value=True), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=True,
            )
            result = use_case(request)

        assert result.skipped == 1
        assert result.succeeded == 0
        mock_gateway.transcribe.assert_not_called()

    def test_no_cache_flag_forces_reprocess(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """--no-cache のときはキャッシュがあっても処理する"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        with patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result), \
             patch.object(use_case, "_cache_exists", return_value=True), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,   # キャッシュ無効
            )
            result = use_case(request)

        assert result.succeeded == 1
        assert result.skipped == 0


# ---------------------------------------------------------------------------
# エラーハンドリングテスト
# ---------------------------------------------------------------------------

class TestBatchTranscribeErrorHandling:

    def test_one_failure_continues_processing(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """1件失敗しても他のファイルは処理継続される"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        # 1件目は失敗、2件目以降は成功
        execute_calls = [
            Exception("処理失敗"),
            mock_transcription_result,
            mock_transcription_result,
        ]
        execute_mock = MagicMock(side_effect=execute_calls)

        with patch.object(use_case._single_use_case, "execute", execute_mock), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                fail_fast=False,
            )
            result = use_case(request)

        assert result.total == 3
        assert result.failed == 1
        assert result.succeeded == 2

    def test_fail_fast_stops_on_first_error(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """fail_fast=True のとき最初のエラーで処理を中断する"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        execute_mock = MagicMock(side_effect=Exception("最初のエラー"))

        with patch.object(use_case._single_use_case, "execute", execute_mock), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                fail_fast=True,
            )
            result = use_case(request)

        # fail_fast により 1件で中断（2件目・3件目は処理されない）
        assert result.failed == 1
        assert result.succeeded == 0

    def test_retry_on_failure(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """retry_count=1 のとき失敗後にリトライする"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        # 1回目は失敗、2回目（リトライ）は成功
        execute_mock = MagicMock(side_effect=[Exception("一時エラー"), mock_transcription_result])

        with patch.object(use_case._single_use_case, "execute", execute_mock), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
                retry_count=1,
            )
            result = use_case(request)

        assert result.succeeded == 1
        assert result.failed == 0
        assert execute_mock.call_count == 2

    def test_failed_items_accessible(self, mock_gateway, tmp_video_files):
        """failed_items で失敗したファイルの詳細を取得できる"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        execute_mock = MagicMock(side_effect=Exception("エラー詳細"))

        with patch.object(use_case._single_use_case, "execute", execute_mock), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=None):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
            )
            result = use_case(request)

        assert len(result.failed_items) == 1
        assert "エラー詳細" in result.failed_items[0].error


# ---------------------------------------------------------------------------
# ドライランテスト
# ---------------------------------------------------------------------------

class TestBatchTranscribeDryRun:

    def test_dry_run_does_not_call_gateway(self, mock_gateway, tmp_video_files):
        """ドライランでは Gateway を呼び出さない"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        with patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                dry_run=True,
            )
            result = use_case(request)

        mock_gateway.transcribe.assert_not_called()
        assert result.total == 3

    def test_dry_run_shows_skipped_for_cached(self, mock_gateway, tmp_video_files):
        """ドライランでキャッシュがある場合はスキップと表示される"""
        use_case = BatchTranscribeUseCase(mock_gateway)

        # 最初の1件だけキャッシュあり
        def cache_exists_side_effect(path, model):
            return str(path) == str(FilePath(str(tmp_video_files[0])))

        with patch.object(use_case, "_cache_exists", side_effect=cache_exists_side_effect), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=True,
                dry_run=True,
            )
            result = use_case(request)

        assert result.skipped == 1
        assert result.succeeded == 2  # ドライランでは残りは "succeeded" 扱い


# ---------------------------------------------------------------------------
# 進捗コールバックテスト
# ---------------------------------------------------------------------------

class TestBatchTranscribeProgressCallback:

    def test_progress_callback_called(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """進捗コールバックが呼ばれる"""
        progress_events: list[BatchProgress] = []
        use_case = BatchTranscribeUseCase(mock_gateway)

        with patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result), \
             patch.object(use_case, "_cache_exists", return_value=False), \
             patch.object(use_case, "_get_output_path", return_value=Path("/tmp/out.json")):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files[:2]],
                model_size="medium",
                use_cache=False,
                progress_callback=progress_events.append,
            )
            use_case(request)

        # 各ファイルにつき「処理中」と「完了」の2回呼ばれる
        assert len(progress_events) >= 2
        statuses = [e.current_status for e in progress_events]
        assert "processing" in statuses
        assert "succeeded" in statuses


# ---------------------------------------------------------------------------
# CLIオプション解析テスト
# ---------------------------------------------------------------------------

class TestCLIParser:

    def test_default_options(self):
        """デフォルトオプションの確認"""
        from textffcut_cli.command import build_parser
        parser = build_parser()
        args = parser.parse_args(["video.mp4"])

        assert args.model == "medium"
        assert args.workers == 1
        assert args.use_cache is True
        assert args.retry == 0
        assert args.fail_fast is False
        assert args.dry_run is False
        assert args.quiet is False
        assert args.json_progress is False

    def test_model_option(self):
        """モデル指定オプション"""
        from textffcut_cli.command import build_parser
        parser = build_parser()
        args = parser.parse_args(["-m", "large-v3", "video.mp4"])
        assert args.model == "large-v3"

    def test_no_cache_flag(self):
        """--no-cache フラグ"""
        from textffcut_cli.command import build_parser
        parser = build_parser()
        args = parser.parse_args(["--no-cache", "video.mp4"])
        assert args.use_cache is False

    def test_collect_video_paths_from_directory(self, tmp_path):
        """フォルダからの動画ファイル収集"""
        from textffcut_cli.command import _collect_video_paths

        (tmp_path / "a.mp4").write_bytes(b"x")
        (tmp_path / "b.mov").write_bytes(b"x")
        (tmp_path / "c.txt").write_bytes(b"x")  # 除外されるべき

        paths = _collect_video_paths([str(tmp_path)])
        names = {p.name for p in paths}

        assert "a.mp4" in names
        assert "b.mov" in names
        assert "c.txt" not in names

    def test_collect_video_paths_deduplication(self, tmp_path):
        """重複ファイルの除去"""
        from textffcut_cli.command import _collect_video_paths

        f = tmp_path / "video.mp4"
        f.write_bytes(b"x")

        paths = _collect_video_paths([str(f), str(f)])
        assert len(paths) == 1
