"""
textffcut CLI コマンド定義

argparse でオプションを解析し、BatchTranscribeUseCase を実行する。
Apple Silicon Mac専用（MLX強制）。非対応環境では起動時にエラー終了する。
"""

import argparse
import glob
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 環境チェック（起動時に即座に確認）
# ---------------------------------------------------------------------------

def _check_environment() -> None:
    """Apple Silicon + MLX の確認。非対応環境ではエラー終了する。"""
    import platform

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        print(
            "エラー: textffcut CLI は Apple Silicon Mac 専用です。\n"
            "  対応環境: macOS (arm64)\n"
            f"  現在の環境: {platform.system()} ({platform.machine()})",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import mlx_whisper  # noqa: F401
        from mlx_forced_aligner import ForcedAligner  # noqa: F401
    except ImportError as e:
        print(
            f"エラー: MLX ライブラリが見つかりません: {e}\n"
            "  インストール方法:\n"
            "    pip install -r requirements-mlx.txt",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}


def _collect_video_paths(inputs: list[str]) -> list[Path]:
    """
    引数として渡されたファイル・フォルダ・グロブパターンから動画ファイルを収集する。
    重複は除去し、元の順序を保持する。
    """
    seen: set[Path] = set()
    paths: list[Path] = []

    for inp in inputs:
        # グロブ展開（シェルが展開しなかった場合に備えて Python 側でも実行）
        expanded = glob.glob(inp, recursive=False)
        candidates = [Path(p) for p in expanded] if expanded else [Path(inp)]

        for candidate in candidates:
            if candidate.is_dir():
                # ディレクトリの場合は直下の動画ファイルを収集（再帰なし）
                for ext in SUPPORTED_EXTENSIONS:
                    for f in sorted(candidate.glob(f"*{ext}")):
                        if f not in seen:
                            seen.add(f)
                            paths.append(f)
            elif candidate.is_file():
                if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                    if candidate not in seen:
                        seen.add(candidate)
                        paths.append(candidate)
                else:
                    print(
                        f"警告: 対応していない形式のためスキップします: {candidate}",
                        file=sys.stderr,
                    )
            else:
                print(f"警告: ファイルが見つかりません: {candidate}", file=sys.stderr)

    return paths


# ---------------------------------------------------------------------------
# CLI エントリーポイント
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textffcut",
        description=(
            "TextffCut CLIバッチ文字起こし\n"
            "Apple Silicon Mac専用（MLX高速モード）\n\n"
            "例:\n"
            "  textffcut video1.mp4 video2.mp4\n"
            "  textffcut -m large-v3 ./videos/*.mp4\n"
            "  textffcut --dry-run ./videos/\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE_OR_DIR",
        help="処理する動画ファイルまたはフォルダのパス（グロブパターン可）",
    )

    # 文字起こし設定
    transcription = parser.add_argument_group("文字起こし設定")
    transcription.add_argument(
        "-m", "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        metavar="MODEL",
        help="使用するモデルサイズ（デフォルト: medium）",
    )
    transcription.add_argument(
        "-l", "--language",
        default=None,
        metavar="LANG",
        help="言語コード（例: ja, en）。省略時は自動検出",
    )

    # バッチ制御
    batch = parser.add_argument_group("バッチ制御")
    batch.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        metavar="N",
        help="同時処理数（デフォルト: 1）",
    )
    cache_group = batch.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--use-cache",
        dest="use_cache",
        action="store_true",
        default=True,
        help="キャッシュがあればスキップ（デフォルト）",
    )
    cache_group.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        help="キャッシュを無視して常に再処理",
    )
    batch.add_argument(
        "--retry",
        type=int,
        default=0,
        metavar="N",
        help="失敗時のリトライ回数（デフォルト: 0）",
    )
    batch.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="最初のエラーで処理を中断",
    )
    batch.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="ファイルを処理せず、対象ファイル一覧のみ表示",
    )

    # 表示制御
    display = parser.add_argument_group("表示制御")
    display.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="エラー以外の出力を抑制",
    )
    display.add_argument(
        "--json-progress",
        action="store_true",
        default=False,
        help="進捗を JSON Lines 形式で標準出力（外部ツール連携用）",
    )

    return parser


def main() -> None:
    """CLI メインエントリーポイント"""
    _check_environment()

    parser = build_parser()
    args = parser.parse_args()

    # ファイル収集
    video_paths_raw = _collect_video_paths(args.files)
    if not video_paths_raw:
        print("エラー: 処理対象の動画ファイルが見つかりませんでした。", file=sys.stderr)
        sys.exit(1)

    # ドライランは早期リターン
    if args.dry_run:
        _print_dry_run(video_paths_raw, args)
        sys.exit(0)

    # DIコンテナ・ユースケース初期化
    from di.bootstrap import bootstrap_di
    from domain.value_objects import FilePath
    from use_cases.transcription.batch_transcribe import BatchTranscribeRequest, BatchTranscribeUseCase
    from textffcut_cli.progress_display import ProgressDisplay

    container = bootstrap_di()
    gateway = container.gateways.transcription_gateway()
    use_case = BatchTranscribeUseCase(gateway)

    display = ProgressDisplay(quiet=args.quiet, json_progress=args.json_progress)
    display.start(total=len(video_paths_raw), model=args.model)

    def on_progress(progress):
        display.update(progress)

    request = BatchTranscribeRequest(
        video_paths=[FilePath(str(p)) for p in video_paths_raw],
        model_size=args.model,
        language=args.language,
        use_cache=args.use_cache,
        max_workers=args.workers,
        retry_count=args.retry,
        fail_fast=args.fail_fast,
        progress_callback=on_progress,
    )

    result = use_case(request)
    display.finish(result)

    # 終了コード: 全成功=0、一部失敗=1、全件失敗=2
    if result.failed == 0:
        sys.exit(0)
    elif result.succeeded == 0 and result.skipped == 0:
        sys.exit(2)
    else:
        sys.exit(1)


def _print_dry_run(paths: list[Path], args: argparse.Namespace) -> None:
    from rich.console import Console
    from rich.table import Table

    con = Console()
    con.print(f"\n[bold]ドライラン[/] — 実際の処理は行いません\n")
    con.print(f"モデル: [cyan]{args.model}[/]  workers: {args.workers}")
    con.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("ファイル")
    table.add_column("パス", style="dim")

    for i, p in enumerate(paths, 1):
        table.add_row(str(i), p.name, str(p.parent))

    con.print(table)
    con.print(f"\n合計: [bold]{len(paths)}[/] ファイル")
