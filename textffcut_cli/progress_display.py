"""
バッチ処理の進捗表示

rich ライブラリを使ってターミナルに進捗を表示する。
--quiet モードでは何も表示しない。
--json-progress モードでは JSON Lines 形式で標準出力に出力する。
"""

import json
import sys
import time
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from use_cases.transcription.batch_transcribe import BatchItemResult, BatchProgress

console = Console(stderr=True)   # 進捗は stderr に出力（stdout はデータ用に空ける）


class ProgressDisplay:
    """バッチ処理の進捗表示を管理するクラス"""

    def __init__(self, *, quiet: bool = False, json_progress: bool = False) -> None:
        self.quiet = quiet
        self.json_progress = json_progress
        self._progress: Progress | None = None
        self._live: Live | None = None
        self._task_id: TaskID | None = None
        self._file_statuses: list[dict] = []
        self._start_time: float = time.time()

    def start(self, total: int, model: str) -> None:
        if self.json_progress:
            self._emit_json({
                "type": "start",
                "total": total,
                "model": model,
                "timestamp": datetime.now().isoformat(),
            })
            return

        if self.quiet:
            return

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._task_id = self._progress.add_task(
            f"バッチ文字起こし（モデル: {model}）",
            total=total,
        )
        self._live = Live(self._progress, console=console, refresh_per_second=4)
        self._live.start()

    def update(self, progress: "BatchProgress") -> None:
        if self.json_progress:
            self._emit_json({
                "type": "progress",
                "file": progress.current_file,
                "status": progress.current_status,
                "index": progress.completed + progress.failed + progress.skipped,
                "total": progress.total,
                "elapsed": round(progress.elapsed_seconds, 1),
            })
            return

        if self.quiet or self._progress is None or self._task_id is None:
            return

        completed_total = progress.completed + progress.failed + progress.skipped
        status_icon = {
            "processing": "[yellow]処理中[/]",
            "succeeded": "[green]✓ 完了[/]",
            "failed": "[red]✗ 失敗[/]",
            "skipped": "[dim]- スキップ[/]",
        }.get(progress.current_status, progress.current_status)

        desc = (
            f"[{completed_total}/{progress.total}] "
            f"{status_icon}  {progress.current_file or ''}"
        )
        self._progress.update(self._task_id, description=desc, completed=completed_total)

    def finish(self, result: "BatchTranscribeResult") -> None:  # type: ignore[name-defined]
        if self.json_progress:
            self._emit_json({
                "type": "summary",
                "succeeded": result.succeeded,
                "failed": result.failed,
                "skipped": result.skipped,
                "total_elapsed": round(result.total_processing_time, 1),
            })
            return

        if self._live is not None:
            self._live.stop()

        if self.quiet:
            return

        self._print_summary(result)

    def _print_summary(self, result: "BatchTranscribeResult") -> None:  # type: ignore[name-defined]
        console.print()
        console.rule("[bold]処理完了")

        # サマリーテーブル
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("完了", f"[green]{result.succeeded}[/] 件")
        table.add_row("スキップ", f"[dim]{result.skipped}[/] 件（キャッシュあり）")
        table.add_row("失敗", f"[red]{result.failed}[/] 件")
        table.add_row("処理時間", f"{result.total_processing_time:.1f} 秒")
        console.print(table)

        if result.failed_items:
            console.print()
            console.print("[bold red]失敗したファイル:[/]")
            for item in result.failed_items:
                console.print(f"  [red]✗[/] {item.video_path.name}")
                if item.error:
                    console.print(f"    [dim]{item.error}[/]")

    @staticmethod
    def _emit_json(data: dict) -> None:
        print(json.dumps(data, ensure_ascii=False), flush=True)
