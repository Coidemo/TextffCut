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
            "  Homebrew でインストールした場合は再インストールをお試しください:\n"
            "    brew reinstall textffcut",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a"]


def _collect_video_paths(inputs: list[str]) -> list[Path]:
    """
    引数として渡されたファイル・フォルダ・グロブパターンから動画ファイルを収集する。
    重複は除去し、元の順序を保持する。
    """
    seen: set[Path] = set()
    paths: list[Path] = []

    for inp in inputs:
        # グロブ展開（シェルが展開しなかった場合に備えて Python 側でも実行）
        # recursive=True にすることで **/*.mp4 などの再帰パターンも機能する
        expanded = glob.glob(inp, recursive=True)
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
            "コマンド:\n"
            "  textffcut gui                        GUIを起動\n"
            "  textffcut clip [ファイル ...]          AI自動切り抜き→FCPXML出力\n"
            "  textffcut setup                      初期設定ウィザード\n"
            "  textffcut activate KEY               ライセンスキーを登録\n"
            "  textffcut models                     使用可能なモデル一覧を表示\n"
            "  textffcut [ファイル ...]              文字起こし（メイン機能）\n\n"
            "例:\n"
            "  textffcut gui\n"
            "  textffcut video1.mp4 video2.mp4\n"
            "  textffcut -m large-v3 ./videos/*.mp4\n"
            "  textffcut -s ./videos/               # シミュレート\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    try:
        from importlib.metadata import version as _pkg_version
        _version = _pkg_version("textffcut")
    except Exception:
        _version = "unknown"
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {_version}",
    )

    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE_OR_DIR",
        help="処理する動画ファイルまたはフォルダのパス（グロブパターン可）",
    )

    parser.add_argument(
        "-m", "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        metavar="MODEL",
        help="使用するモデルサイズ（デフォルト: medium）tiny/base/small/medium/large-v3/large-v3-turbo",
    )
    parser.add_argument(
        "-n", "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
        help="キャッシュを無視して再処理",
    )
    parser.add_argument(
        "-s", "--simulate",
        action="store_true",
        default=False,
        help="ファイルを処理せず、対象ファイル一覧のみ表示",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="進捗出力を抑制する（デフォルト: 表示あり）",
    )

    return parser


def _print_dry_run(paths: list[Path], args: argparse.Namespace) -> None:
    from rich.console import Console
    from rich.table import Table

    con = Console()
    con.print("\n[bold]シミュレート[/] — 実際の処理は行いません\n")
    con.print(f"モデル: [cyan]{args.model}[/]")
    con.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("ファイル")
    table.add_column("パス", style="dim")

    for i, p in enumerate(paths, 1):
        table.add_row(str(i), p.name, str(p.parent))

    con.print(table)
    if paths:
        con.print(f"\n合計: [bold]{len(paths)}[/] ファイル")
    else:
        con.print("\n[yellow]対象ファイルが見つかりませんでした[/]")


def _cmd_models() -> None:
    """使用可能なモデル一覧を表示する。"""
    from rich.console import Console
    from rich.table import Table

    models = [
        ("tiny",           "39M",   "最速・低精度。動作確認用"),
        ("base",           "74M",   "高速・やや低精度"),
        ("small",          "244M",  "バランス型"),
        ("medium",         "769M",  "推奨。精度と速度のバランスが良い"),
        ("large-v3",       "1.5G",  "高精度・低速"),
        ("large-v3-turbo", "809M",  "large-v3 の高速版（推奨）"),
    ]

    con = Console()
    con.print("\n[bold]使用可能なモデル[/]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("モデル名", style="cyan")
    table.add_column("サイズ", justify="right")
    table.add_column("説明")

    for name, size, desc in models:
        marker = " ◀ デフォルト" if name == "medium" else ""
        table.add_row(name, size, desc + marker)

    con.print(table)
    con.print("\n使い方: [cyan]textffcut -m large-v3-turbo 動画.mp4[/]\n")


def _cmd_gui() -> None:
    """Streamlit GUIを起動する。カレントディレクトリに videos/ を作成してFinderで開く。"""
    import subprocess
    import importlib.util

    # videos/ フォルダをカレントディレクトリに作成
    videos_dir = Path.cwd() / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir(parents=True)
        print(f"✓ 動画フォルダを作成しました: {videos_dir}")
        print("  ↑ ここに処理したい動画ファイルを入れてください")
        subprocess.run(["open", str(videos_dir)], check=False)
    else:
        print(f"動画フォルダ: {videos_dir}")

    # main.py のパスを解決（py-modules でインストール済み）
    spec = importlib.util.find_spec("main")
    if spec is None or spec.origin is None:
        print("エラー: GUIモジュール（main.py）が見つかりません。", file=sys.stderr)
        sys.exit(1)
    main_py = Path(spec.origin)

    print("\nGUIを起動中... http://localhost:8501")
    print("停止するには Ctrl+C を押してください\n")

    try:
        # subprocess.run はブロッキング呼び出し。
        # Ctrl+C は子プロセス（streamlit）に直接 SIGINT が届くため、
        # 通常は KeyboardInterrupt ではなく subprocess.run が正常に return する。
        # どちらのケースでも停止メッセージを表示する。
        subprocess.run(["streamlit", "run", str(main_py)], check=False)
        print("\n✓ GUIを停止しました")
    except KeyboardInterrupt:
        print("\n✓ GUIを停止しました")
    except FileNotFoundError:
        print(
            "エラー: streamlit が見つかりません。\n"
            "  Homebrew でインストールした場合: brew reinstall textffcut\n"
            "  直接インストールした場合: pip install 'textffcut[ui]'",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """CLI メインエントリーポイント"""
    # 引数なし時のガイド表示（parse_args より先に確認）
    if len(sys.argv) == 1:
        print(
            "使い方:\n"
            "  GUI モード:  textffcut gui                    # ブラウザで操作\n"
            "  CLIモード:   textffcut [動画ファイル ...]       # 文字起こし\n"
            "  AI切り抜き:  textffcut clip [動画ファイル ...]    # AI自動切り抜き→FCPXML\n"
            "  初期設定:    textffcut setup                   # 対話型初期設定\n"
            "\n"
            "例:\n"
            "  textffcut gui\n"
            "  textffcut ./動画.mp4\n"
            "  textffcut clip ./動画.mp4\n"
            "  textffcut clip -m large-v3 --ai-model gpt-4.1 ./videos/*.mp4\n"
            "\n"
            "詳しくは: textffcut --help"
        )
        sys.exit(0)

    # activate / gui / models は argparse の前に手動ルーティング（subparsers を使わない理由:
    # subparsers にすると positional argument としてのファイルパスと競合するため）。
    # これらのサブコマンドは MLX ライブラリを使わないので _check_environment() は呼ばない。
    # （gui は open / streamlit のみ使用、activate / models は純粋な入出力）
    if sys.argv[1] == "models":
        if len(sys.argv) > 2 and sys.argv[2] in ("-h", "--help"):
            print("使い方: textffcut models\n使用可能なモデル一覧を表示します。")
            return
        _cmd_models()
        return

    if sys.argv[1] == "activate":
        if len(sys.argv) > 2 and sys.argv[2] in ("-h", "--help"):
            print("使い方: textffcut activate XXXXX-XXXXX-XXXXX-XXXXX\nライセンスキーを登録します。")
            return
        key = sys.argv[2] if len(sys.argv) > 2 else ""
        if not key:
            print("使い方: textffcut activate XXXXX-XXXXX-XXXXX-XXXXX", file=sys.stderr)
            sys.exit(1)
        from textffcut_cli.license import activate
        if activate(key):
            print(
                "✓ ライセンスを登録しました。\n"
                "\n"
                "次のステップ:\n"
                "  GUIで使う:   textffcut gui\n"
                "  CLIで使う:   textffcut ./動画.mp4\n"
                "  ヘルプ:      textffcut --help"
            )
        else:
            print("エラー: 無効なキーです。", file=sys.stderr)
            sys.exit(1)
        return

    if sys.argv[1] == "setup":
        from textffcut_cli.setup_command import run_setup
        run_setup()
        return

    if sys.argv[1] in ("clip", "suggest"):
        from textffcut_cli.suggest_command import run_suggest
        run_suggest(sys.argv[2:])
        return

    if sys.argv[1] == "gui":
        # --help フラグを確認してからGUIを起動
        if len(sys.argv) > 2 and sys.argv[2] in ("-h", "--help"):
            print("使い方: textffcut gui\nStreamlit GUIを起動します。カレントディレクトリに videos/ フォルダを作成します。")
            return
        _cmd_gui()
        return

    parser = build_parser()
    args = parser.parse_args()

    # 通常コマンド: 環境チェック → ライセンスチェックの順
    _check_environment()
    from textffcut_cli.license import require_license
    require_license()

    # ファイル収集
    video_paths_raw = _collect_video_paths(args.files)

    # シミュレートはファイルが0件でも表示（エラーにしない）
    if args.simulate:
        _print_dry_run(video_paths_raw, args)
        sys.exit(0)

    if not video_paths_raw:
        print("エラー: 処理対象の動画ファイルが見つかりませんでした。", file=sys.stderr)
        sys.exit(1)

    # DIコンテナ・ユースケース初期化
    from di.bootstrap import bootstrap_di
    from domain.value_objects import FilePath
    from use_cases.transcription.batch_transcribe import BatchTranscribeRequest, BatchTranscribeUseCase
    from textffcut_cli.progress_display import ProgressDisplay

    container = bootstrap_di(modules_to_wire=["textffcut_cli.command"])
    gateway = container.gateways.transcription_gateway()
    use_case = BatchTranscribeUseCase(gateway)

    display = ProgressDisplay(quiet=args.quiet, json_progress=False)
    display.start(total=len(video_paths_raw), model=args.model)

    def on_progress(progress):
        display.update(progress)

    # Path → FilePath の変換（二重変換を避けるため直接 FilePath に渡す）
    request = BatchTranscribeRequest(
        video_paths=[FilePath(str(p)) for p in video_paths_raw],
        model_size=args.model,
        language=None,
        use_cache=args.use_cache,
        max_workers=1,
        retry_count=0,
        fail_fast=False,
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


