"""
バッチ文字起こしユースケース

複数の動画ファイルを順次（または並列に）文字起こしする。
出力は動画ファイルと同じディレクトリの {動画名}_TextffCut/transcriptions/{model}.json に保存される。
これはStreamlit UIのキャッシュと同一フォーマットのため、後でUIで再利用可能。

Apple Silicon Mac専用（MLX強制）。
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.base import UseCase
from use_cases.exceptions import TranscriptionError
from use_cases.interfaces import ITranscriptionGateway
from use_cases.transcription.transcribe_video import TranscribeVideoRequest, TranscribeVideoUseCase


@dataclass
class BatchTranscribeRequest:
    """バッチ文字起こしリクエスト"""

    video_paths: list[FilePath]
    model_size: str = "medium"
    language: str | None = None
    use_cache: bool = True           # バッチではキャッシュ活用がデフォルト
    max_workers: int = 1             # MLXのメモリ効率のためデフォルト1
    retry_count: int = 0
    fail_fast: bool = False
    dry_run: bool = False
    progress_callback: "Callable[[BatchProgress], None] | None" = None

    def __post_init__(self) -> None:
        self.video_paths = [
            FilePath(str(p)) if not isinstance(p, FilePath) else p
            for p in self.video_paths
        ]
        self.max_workers = max(1, self.max_workers)
        self.retry_count = max(0, self.retry_count)


@dataclass
class BatchProgress:
    """バッチ処理の進捗情報"""

    total: int
    completed: int
    failed: int
    skipped: int
    current_file: str | None
    current_status: str              # "processing" | "completed" | "failed" | "skipped"
    elapsed_seconds: float
    estimated_remaining_seconds: float | None


@dataclass
class BatchItemResult:
    """1ファイル分の処理結果"""

    video_path: Path
    status: str                      # "succeeded" | "failed" | "skipped"
    output_path: Path | None = None
    error: str | None = None
    processing_time: float = 0.0


@dataclass
class BatchTranscribeResult:
    """バッチ処理全体の結果"""

    items: list[BatchItemResult] = field(default_factory=list)
    total_processing_time: float = 0.0

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.items if r.status == "succeeded")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.items if r.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.items if r.status == "skipped")

    @property
    def failed_items(self) -> list[BatchItemResult]:
        return [r for r in self.items if r.status == "failed"]


class BatchTranscribeUseCase(UseCase[BatchTranscribeRequest, BatchTranscribeResult]):
    """
    複数動画のバッチ文字起こしユースケース

    - Apple Silicon Mac専用（MLX強制）
    - 出力は動画と同じディレクトリの {動画名}_TextffCut/transcriptions/{model}.json
    - Streamlit UIのキャッシュと同一フォーマットのため後でUI再利用可能
    """

    def __init__(self, transcription_gateway: ITranscriptionGateway) -> None:
        super().__init__()
        self.gateway = transcription_gateway
        self._single_use_case = TranscribeVideoUseCase(transcription_gateway)

    def validate_request(self, request: BatchTranscribeRequest) -> None:
        if not request.video_paths:
            raise TranscriptionError("処理対象の動画ファイルが指定されていません")

    def execute(self, request: BatchTranscribeRequest) -> BatchTranscribeResult:
        result = BatchTranscribeResult()
        batch_start = time.time()

        if request.dry_run:
            return self._dry_run(request)

        if request.max_workers > 1:
            self._execute_parallel(request, result, batch_start)
        else:
            self._execute_sequential(request, result, batch_start)

        result.total_processing_time = time.time() - batch_start
        return result

    # ------------------------------------------------------------------
    # 順次処理
    # ------------------------------------------------------------------

    def _execute_sequential(
        self,
        request: BatchTranscribeRequest,
        result: BatchTranscribeResult,
        batch_start: float,
    ) -> None:
        completed = 0
        failed = 0
        skipped = 0

        for video_path in request.video_paths:
            elapsed = time.time() - batch_start
            estimated = self._estimate_remaining(elapsed, completed, len(request.video_paths))

            self._notify(
                request,
                BatchProgress(
                    total=len(request.video_paths),
                    completed=completed,
                    failed=failed,
                    skipped=skipped,
                    current_file=Path(str(video_path)).name,
                    current_status="processing",
                    elapsed_seconds=elapsed,
                    estimated_remaining_seconds=estimated,
                ),
            )

            item = self._process_one(request, video_path)
            result.items.append(item)

            if item.status == "succeeded":
                completed += 1
            elif item.status == "failed":
                failed += 1
                if request.fail_fast:
                    self.logger.warning("fail_fast が有効のため処理を中断します")
                    break
            else:
                skipped += 1

            self._notify(
                request,
                BatchProgress(
                    total=len(request.video_paths),
                    completed=completed,
                    failed=failed,
                    skipped=skipped,
                    current_file=Path(str(video_path)).name,
                    current_status=item.status,
                    elapsed_seconds=time.time() - batch_start,
                    estimated_remaining_seconds=None,
                ),
            )

    # ------------------------------------------------------------------
    # 並列処理
    # ------------------------------------------------------------------

    def _execute_parallel(
        self,
        request: BatchTranscribeRequest,
        result: BatchTranscribeResult,
        batch_start: float,
    ) -> None:
        items_map: dict[str, BatchItemResult] = {}

        with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
            futures = {
                executor.submit(self._process_one, request, vp): vp
                for vp in request.video_paths
            }

            completed = 0
            failed = 0
            skipped = 0

            for future in as_completed(futures):
                video_path = futures[future]
                item = future.result()
                items_map[str(video_path)] = item

                if item.status == "succeeded":
                    completed += 1
                elif item.status == "failed":
                    failed += 1
                    if request.fail_fast:
                        for f in futures:
                            f.cancel()
                        break
                else:
                    skipped += 1

                self._notify(
                    request,
                    BatchProgress(
                        total=len(request.video_paths),
                        completed=completed,
                        failed=failed,
                        skipped=skipped,
                        current_file=Path(str(video_path)).name,
                        current_status=item.status,
                        elapsed_seconds=time.time() - batch_start,
                        estimated_remaining_seconds=None,
                    ),
                )

        # 元の順序を保って結果リストに追加
        for vp in request.video_paths:
            if str(vp) in items_map:
                result.items.append(items_map[str(vp)])

    # ------------------------------------------------------------------
    # 1ファイル処理（リトライ込み）
    # ------------------------------------------------------------------

    def _process_one(
        self, request: BatchTranscribeRequest, video_path: FilePath
    ) -> BatchItemResult:
        start = time.time()

        # キャッシュ確認（use_cache=True のときはキャッシュがあればスキップ）
        if request.use_cache and self._cache_exists(video_path, request.model_size):
            self.logger.info(f"キャッシュあり、スキップ: {video_path}")
            return BatchItemResult(
                video_path=Path(str(video_path)),
                status="skipped",
                output_path=self._get_output_path(video_path, request.model_size),
            )

        last_error: Exception | None = None
        for attempt in range(request.retry_count + 1):
            try:
                if attempt > 0:
                    self.logger.info(f"リトライ {attempt}/{request.retry_count}: {video_path}")

                transcription_request = TranscribeVideoRequest(
                    video_path=video_path,
                    model_size=request.model_size,
                    language=request.language,
                    use_cache=False,   # ここではキャッシュ確認済みのため無効化
                )
                self._single_use_case.execute(transcription_request)

                output_path = self._get_output_path(video_path, request.model_size)
                return BatchItemResult(
                    video_path=Path(str(video_path)),
                    status="succeeded",
                    output_path=output_path,
                    processing_time=time.time() - start,
                )

            except Exception as e:
                last_error = e
                self.logger.warning(f"処理失敗 (attempt {attempt + 1}): {video_path} - {e}")

        return BatchItemResult(
            video_path=video_path.path,
            status="failed",
            error=str(last_error),
            processing_time=time.time() - start,
        )

    # ------------------------------------------------------------------
    # ドライラン
    # ------------------------------------------------------------------

    def _dry_run(self, request: BatchTranscribeRequest) -> BatchTranscribeResult:
        result = BatchTranscribeResult()
        for video_path in request.video_paths:
            has_cache = self._cache_exists(video_path, request.model_size)
            status = "skipped" if (request.use_cache and has_cache) else "succeeded"
            result.items.append(
                BatchItemResult(
                    video_path=Path(str(video_path)),
                    status=status,
                    output_path=self._get_output_path(video_path, request.model_size),
                )
            )
        return result

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    def _cache_exists(self, video_path: FilePath, model_size: str) -> bool:
        output_path = self._get_output_path(video_path, model_size)
        return output_path is not None and output_path.exists()

    def _get_output_path(self, video_path: FilePath, model_size: str) -> Path | None:
        """
        Transcriber.get_cache_path() と同じロジックでパスを計算する。
        （UIキャッシュと互換性を持たせるため）
        """
        try:
            from core.transcription import Transcriber
            from config import Config
            transcriber = Transcriber(Config())
            return transcriber.get_cache_path(str(video_path), model_size)
        except Exception:
            return None

    @staticmethod
    def _estimate_remaining(
        elapsed: float, completed: int, total: int
    ) -> float | None:
        if completed == 0:
            return None
        avg_per_item = elapsed / completed
        remaining = total - completed
        return avg_per_item * remaining

    @staticmethod
    def _notify(request: BatchTranscribeRequest, progress: BatchProgress) -> None:
        if request.progress_callback:
            request.progress_callback(progress)
