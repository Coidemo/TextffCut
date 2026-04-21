"""
バッチ文字起こしユースケース

複数の動画ファイルを順次（または並列に）文字起こしする。
出力は動画ファイルと同じディレクトリの {動画名}_TextffCut/transcriptions/{model}.json に保存される。
これはStreamlit UIのキャッシュと同一フォーマットのため、後でUIで再利用可能。

Apple Silicon Mac専用（MLX強制）。
"""

from __future__ import annotations

import os
import random
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
    model_size: str = "large-v3"
    language: str | None = None
    use_cache: bool = True  # バッチではキャッシュ活用がデフォルト
    max_workers: int = 1  # MLXのメモリ効率のためデフォルト1
    retry_count: int = 0
    fail_fast: bool = False
    dry_run: bool = False
    progress_callback: Callable[[BatchProgress], None] | None = None

    def __post_init__(self) -> None:
        self.video_paths = [FilePath(str(p)) if not isinstance(p, FilePath) else p for p in self.video_paths]
        # 上限: CPUコア数またはファイル数のいずれか小さい方
        cpu_count = os.cpu_count() or 1
        self.max_workers = max(1, min(self.max_workers, cpu_count))
        self.retry_count = max(0, self.retry_count)


@dataclass
class BatchProgress:
    """バッチ処理の進捗情報"""

    total: int
    completed: int
    failed: int
    skipped: int
    current_file: str | None
    current_status: str  # "processing" | "retrying" | "succeeded" | "failed" | "skipped"
    elapsed_seconds: float
    estimated_remaining_seconds: float | None


@dataclass
class BatchItemResult:
    """1ファイル分の処理結果"""

    video_path: Path
    status: str  # "succeeded" | "failed" | "skipped" | "pending"
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
            result = self._dry_run(request)
            result.total_processing_time = time.time() - batch_start
            return result

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
            estimated = self._estimate_remaining(elapsed, completed + failed + skipped, len(request.video_paths))

            self._notify(
                request,
                BatchProgress(
                    total=len(request.video_paths),
                    completed=completed,
                    failed=failed,
                    skipped=skipped,
                    current_file=video_path.name,
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
                    current_file=video_path.name,
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
        # 元の順序を保つため、入力順にインデックスを付ける
        indexed_paths = list(enumerate(request.video_paths))
        items_map: dict[int, BatchItemResult] = {}
        stop_flag = False

        completed = 0
        failed = 0
        skipped = 0

        with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
            futures = {executor.submit(self._process_one, request, vp): (idx, vp) for idx, vp in indexed_paths}

            for future in as_completed(futures):
                idx, video_path = futures[future]

                try:
                    item = future.result()
                except Exception as e:
                    # スレッド内で捕捉されなかった例外を BatchItemResult に変換
                    item = BatchItemResult(
                        video_path=video_path.to_path(),
                        status="failed",
                        error=str(e),
                    )

                items_map[idx] = item

                if item.status == "succeeded":
                    completed += 1
                elif item.status == "failed":
                    failed += 1
                    if request.fail_fast:
                        stop_flag = True
                        # Future.cancel() はキュー待機中のタスクのみキャンセルできる。
                        # 既に実行中のスレッドは最後まで走るが、新規タスクの開始は防げる。
                        for f in futures:
                            f.cancel()
                else:
                    skipped += 1

                self._notify(
                    request,
                    BatchProgress(
                        total=len(request.video_paths),
                        completed=completed,
                        failed=failed,
                        skipped=skipped,
                        current_file=video_path.name,
                        current_status=item.status,
                        elapsed_seconds=time.time() - batch_start,
                        estimated_remaining_seconds=None,
                    ),
                )

                if stop_flag:
                    break

        # 元の入力順序を保って結果リストに追加
        # futures にあった全パスを網羅（処理されなかったものは "failed" として補完）
        for idx, vp in indexed_paths:
            if idx in items_map:
                result.items.append(items_map[idx])
            else:
                # fail_fast でキャンセルされたファイルは failed として記録
                result.items.append(
                    BatchItemResult(
                        video_path=Path(str(vp)),
                        status="failed",
                        error="キャンセルされました（fail_fast）",
                    )
                )

    # ------------------------------------------------------------------
    # 1ファイル処理（リトライ込み）
    # ------------------------------------------------------------------

    def _process_one(self, request: BatchTranscribeRequest, video_path: FilePath) -> BatchItemResult:
        start = time.time()

        # キャッシュ確認（use_cache=True のときはキャッシュがあればスキップ）
        if request.use_cache and self._cache_exists(video_path, request.model_size):
            self.logger.info(f"キャッシュあり、スキップ: {video_path}")
            return BatchItemResult(
                video_path=video_path.to_path(),
                status="skipped",
                output_path=self._get_output_path(video_path, request.model_size),
            )

        last_error: Exception | None = None
        for attempt in range(request.retry_count + 1):
            try:
                if attempt > 0:
                    # リトライ前に指数バックオフ（ 2^(attempt-1) + jitter 秒）
                    wait = (2 ** (attempt - 1)) + random.uniform(0.0, 1.0)
                    self.logger.info(f"リトライ {attempt}/{request.retry_count} ({wait:.1f}秒後): {video_path}")
                    self._notify(
                        request,
                        BatchProgress(
                            total=len(request.video_paths),
                            completed=0,
                            failed=0,
                            skipped=0,
                            current_file=video_path.name,
                            current_status="retrying",
                            elapsed_seconds=time.time() - start,
                            estimated_remaining_seconds=None,
                        ),
                    )
                    time.sleep(wait)

                transcription_request = TranscribeVideoRequest(
                    video_path=video_path,
                    model_size=request.model_size,
                    language=request.language,
                    use_cache=False,  # ここではキャッシュ確認済みのため無効化
                )
                self._single_use_case.execute(transcription_request)

                output_path = self._get_output_path(video_path, request.model_size)
                return BatchItemResult(
                    video_path=video_path.to_path(),
                    status="succeeded",
                    output_path=output_path,
                    processing_time=time.time() - start,
                )

            except (KeyboardInterrupt, SystemExit):
                # 中断シグナルは再送出（飲み込まない）
                raise
            except Exception as e:
                last_error = e
                self.logger.warning(f"処理失敗 (attempt {attempt + 1}): {video_path} - {e}")

        return BatchItemResult(
            video_path=video_path.to_path(),
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
            # ドライランでは実際に処理しないため "pending"（キャッシュありは "skipped"）
            status = "skipped" if (request.use_cache and has_cache) else "pending"
            result.items.append(
                BatchItemResult(
                    video_path=video_path.to_path(),
                    status=status,
                    output_path=self._get_output_path(video_path, request.model_size),
                )
            )
        return result

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    def _cache_exists(self, video_path: FilePath, model_size: str) -> bool:
        """ゲートウェイ経由でキャッシュの存在を確認する"""
        try:
            output_path = self.gateway.get_cache_path(video_path, model_size)
            return output_path.exists()
        except Exception:
            return False

    def _get_output_path(self, video_path: FilePath, model_size: str) -> Path | None:
        """
        ゲートウェイ経由でキャッシュパスを取得する。
        （UIキャッシュと互換性を持たせるため、Transcriber.get_cache_path() と同一ロジック）
        """
        try:
            return self.gateway.get_cache_path(video_path, model_size)
        except Exception as e:
            self.logger.warning(f"キャッシュパスの取得に失敗: {video_path} - {e}")
            return None

    @staticmethod
    def _estimate_remaining(elapsed: float, processed: int, total: int) -> float | None:
        if processed == 0:
            return None
        avg_per_item = elapsed / processed
        remaining = total - processed
        return avg_per_item * remaining

    @staticmethod
    def _notify(request: BatchTranscribeRequest, progress: BatchProgress) -> None:
        if request.progress_callback:
            request.progress_callback(progress)
