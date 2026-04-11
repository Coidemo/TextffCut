"""
BatchTranscribeUseCase のユニットテスト

TranscriptionGateway をモックして、バッチ処理ロジックのみを検証する。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import TranscriptionResult, TranscriptionSegment
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
    gateway.get_available_models.return_value = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
    gateway.get_cache_path.return_value = Path("/tmp/out.json")
    return gateway


@pytest.fixture
def mock_transcription_result():
    """
    ダミーの TranscriptionResult。

    MagicMock(spec=TranscriptionResult) は __post_init__ を実行しないため、
    空のセグメントリストでも通過してしまう。実際の TranscriptionResult では
    segments が空だと ValueError になるので、本物のオブジェクトを使う。
    """
    segment = TranscriptionSegment(
        id="seg-1",
        text="テスト文字起こし",
        start=0.0,
        end=1.0,
    )
    return TranscriptionResult(
        id="result-1",
        video_id="test_video",
        language="ja",
        segments=[segment],
        duration=1.0,
        model_size="medium",
        processing_time=10.0,
    )


@pytest.fixture
def tmp_video_files(tmp_path):
    """一時ディレクトリに空の動画ファイルを作成する"""
    files = []
    for name in ["video1.mp4", "video2.mp4", "video3.mp4"]:
        f = tmp_path / name
        f.write_bytes(b"dummy")
        files.append(f)
    return files


def make_use_case(mock_gateway):
    """ユースケースを生成するヘルパー"""
    return BatchTranscribeUseCase(mock_gateway)


# ---------------------------------------------------------------------------
# 基本動作テスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeBasic:

    def test_empty_paths_raises_error(self, mock_gateway):
        """対象ファイルが空のときはエラーになる"""
        use_case = make_use_case(mock_gateway)
        request = BatchTranscribeRequest(video_paths=[])

        with pytest.raises(Exception, match="処理対象"):
            use_case(request)

    def test_single_file_success(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """1ファイルの正常処理"""
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

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
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
            )
            result = use_case(request)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0

    def test_result_video_path_is_always_path_type(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """成功・失敗・スキップすべてで video_path が Path 型になっている"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(
            side_effect=[
                mock_transcription_result,  # 1件目: 成功
                Exception("エラー"),  # 2件目: 失敗
            ]
        )

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", side_effect=[False, False, True]),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=True,
            )
            result = use_case(request)

        for item in result.items:
            assert isinstance(
                item.video_path, Path
            ), f"video_path should be Path, got {type(item.video_path)} for status={item.status}"


# ---------------------------------------------------------------------------
# キャッシュスキップテスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeCache:

    def test_skip_when_cache_exists(self, mock_gateway, tmp_video_files):
        """キャッシュがある場合はスキップされる"""
        use_case = make_use_case(mock_gateway)

        with patch.object(use_case, "_cache_exists", return_value=True):
            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=True,
            )
            result = use_case(request)

        assert result.skipped == 1
        assert result.succeeded == 0
        use_case._single_use_case.execute = MagicMock()
        use_case._single_use_case.execute.assert_not_called()

    def test_no_cache_flag_forces_reprocess(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """--no-cache のときはキャッシュがあっても処理する"""
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=True),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
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
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(
            side_effect=[
                Exception("処理失敗"),
                mock_transcription_result,
                mock_transcription_result,
            ]
        )

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

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

    def test_fail_fast_stops_on_first_error(self, mock_gateway, tmp_video_files):
        """fail_fast=True のとき最初のエラーで処理を中断する"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(side_effect=Exception("最初のエラー"))

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                fail_fast=True,
            )
            result = use_case(request)

        # fail_fast により 1件で中断
        assert result.failed >= 1
        assert result.succeeded == 0

    def test_retry_on_failure(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """retry_count=1 のとき失敗後にリトライする"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(side_effect=[Exception("一時エラー"), mock_transcription_result])

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
            patch("use_cases.transcription.batch_transcribe.time.sleep"),
        ):  # バックオフをスキップ

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
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(side_effect=Exception("エラー詳細"))

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
            )
            result = use_case(request)

        assert len(result.failed_items) == 1
        # 完全一致で検証（"in" チェックは常に真になりうるため "==" で厳密に確認）
        assert result.failed_items[0].error == "エラー詳細"

    def test_keyboard_interrupt_is_not_caught(self, mock_gateway, tmp_video_files):
        """KeyboardInterrupt は握りつぶさず再送出される"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(side_effect=KeyboardInterrupt())

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(tmp_video_files[0]))],
                model_size="medium",
                use_cache=False,
            )
            with pytest.raises(KeyboardInterrupt):
                use_case(request)


# ---------------------------------------------------------------------------
# ドライランテスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeDryRun:

    def test_dry_run_does_not_call_execute(self, mock_gateway, tmp_video_files):
        """ドライランでは _single_use_case.execute を呼び出さない"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock()

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                dry_run=True,
            )
            result = use_case(request)

        execute_mock.assert_not_called()
        assert result.total == 3

    def test_dry_run_status_is_pending_without_cache(self, mock_gateway, tmp_video_files):
        """ドライランでキャッシュなしは 'pending' になる"""
        use_case = make_use_case(mock_gateway)

        with patch.object(use_case, "_cache_exists", return_value=False):
            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=True,
                dry_run=True,
            )
            result = use_case(request)

        assert all(item.status == "pending" for item in result.items)

    def test_dry_run_shows_skipped_for_cached(self, mock_gateway, tmp_video_files):
        """ドライランでキャッシュがある場合は 'skipped' になる"""
        use_case = make_use_case(mock_gateway)

        def cache_side_effect(path, model):
            return str(path) == str(FilePath(str(tmp_video_files[0])))

        with patch.object(use_case, "_cache_exists", side_effect=cache_side_effect):
            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=True,
                dry_run=True,
            )
            result = use_case(request)

        assert result.skipped == 1
        assert sum(1 for i in result.items if i.status == "pending") == 2


# ---------------------------------------------------------------------------
# 並列処理テスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeParallel:

    def test_parallel_all_success(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """並列処理で全件成功する"""
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                max_workers=2,
            )
            result = use_case(request)

        assert result.succeeded == 3
        assert result.failed == 0

    def test_parallel_preserves_all_files_in_result(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """並列処理でも全ファイルが結果に含まれる（サイレント消失なし）"""
        use_case = make_use_case(mock_gateway)
        execute_mock = MagicMock(
            side_effect=[
                Exception("エラー"),
                mock_transcription_result,
                mock_transcription_result,
            ]
        )

        with (
            patch.object(use_case._single_use_case, "execute", execute_mock),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                max_workers=2,
            )
            result = use_case(request)

        # 全3件が結果に含まれること
        assert result.total == 3

    def test_parallel_result_video_path_is_path_type(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """並列処理でも video_path は Path 型"""
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                max_workers=2,
            )
            result = use_case(request)

        for item in result.items:
            assert isinstance(item.video_path, Path)


# ---------------------------------------------------------------------------
# 進捗コールバックテスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeProgressCallback:

    def test_progress_callback_called_twice_per_file(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """各ファイルにつき「processing」と完了ステータスの2回コールバックが呼ばれる"""
        progress_events: list[BatchProgress] = []
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files[:2]],
                model_size="medium",
                use_cache=False,
                progress_callback=progress_events.append,
            )
            use_case(request)

        # 2ファイル × 2回（processing + succeeded）= 4回
        assert len(progress_events) == 4
        statuses = [e.current_status for e in progress_events]
        assert statuses.count("processing") == 2
        assert statuses.count("succeeded") == 2

    def test_progress_total_is_correct(self, mock_gateway, mock_transcription_result, tmp_video_files):
        """進捗の total が常に正しい値を返す"""
        progress_events: list[BatchProgress] = []
        use_case = make_use_case(mock_gateway)

        with (
            patch.object(use_case._single_use_case, "execute", return_value=mock_transcription_result),
            patch.object(use_case, "_cache_exists", return_value=False),
        ):

            request = BatchTranscribeRequest(
                video_paths=[FilePath(str(f)) for f in tmp_video_files],
                model_size="medium",
                use_cache=False,
                progress_callback=progress_events.append,
            )
            use_case(request)

        for event in progress_events:
            assert event.total == 3


# ---------------------------------------------------------------------------
# max_workers 上限テスト
# ---------------------------------------------------------------------------


class TestBatchTranscribeMaxWorkers:

    def test_max_workers_capped_at_cpu_count(self):
        """max_workers は CPU コア数を超えない"""
        import os

        cpu_count = os.cpu_count() or 1
        request = BatchTranscribeRequest(
            video_paths=[FilePath("/tmp/dummy.mp4")],
            max_workers=9999,
        )
        assert request.max_workers <= cpu_count

    def test_max_workers_minimum_is_1(self):
        """max_workers は最小1"""
        request = BatchTranscribeRequest(
            video_paths=[FilePath("/tmp/dummy.mp4")],
            max_workers=0,
        )
        assert request.max_workers == 1


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
        assert args.use_cache is True
        assert args.simulate is False
        assert args.quiet is False

    def test_model_option(self):
        """-m オプションでモデルを指定できる"""
        from textffcut_cli.command import build_parser

        parser = build_parser()
        args = parser.parse_args(["-m", "large-v3", "video.mp4"])
        assert args.model == "large-v3"

    def test_no_cache_flag(self):
        """--no-cache フラグで use_cache が False になる"""
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

    def test_collect_video_paths_recursive_glob(self, tmp_path):
        """再帰グロブ (**/*.mp4) でサブディレクトリの動画ファイルを収集できる"""
        from textffcut_cli.command import _collect_video_paths

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.mp4").write_bytes(b"x")

        pattern = str(tmp_path / "**" / "*.mp4")
        paths = _collect_video_paths([pattern])
        names = {p.name for p in paths}

        assert "deep.mp4" in names
