"""`textffcut relink` サブコマンド。

FCPXML内の絶対パスを現在のマシン用に書き換える。別マシンで生成された
キャッシュフォルダを受け取ったときに使う。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.fcpxml_relink import (
    RelinkResult,
    RelinkStatus,
    relink_all_in_videos_root,
    relink_folder,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textffcut relink",
        description=(
            "FCPXML内の絶対パスを現在のマシン用に書き換える。\n"
            "別マシンで生成されたキャッシュフォルダを受け取ったときに使う。\n\n"
            "例:\n"
            "  textffcut relink ./videos/動画名_TextffCut\n"
            "  textffcut relink --all              # videos/配下を全て\n"
            "  textffcut relink --all ./videos\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="対象フォルダ。通常は `{動画名}_TextffCut` フォルダ。--all 時は videos/ を指す（省略時は ./videos）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="videos/ 配下の全 *_TextffCut フォルダを対象にする",
    )
    parser.add_argument(
        "--preset-dir",
        metavar="DIR",
        help="preset/ フォルダを明示指定（省略時は videos/ の親配下の preset/）",
    )
    return parser


def _print_result(result: RelinkResult) -> None:
    """RelinkResult を人間向けに表示。"""
    try:
        from rich.console import Console

        con = Console()
    except ImportError:
        con = None

    name = result.cache_dir.name

    def echo(msg: str) -> None:
        if con:
            con.print(msg)
        else:
            # rich が無い場合はマークアップを簡易に除去
            import re as _re

            print(_re.sub(r"\[/?[^\]]+\]", "", msg))

    if result.status == RelinkStatus.ERROR:
        echo(f"[red]✗[/] {name}: {result.error_message}")
        return
    if result.status == RelinkStatus.UP_TO_DATE:
        echo(f"[dim]・[/] {name}: 変更なし ({result.fcpxml_count}ファイル確認)")
        return
    if result.status == RelinkStatus.RELINKED:
        echo(f"[green]✓[/] {name}: {result.rewritten_count}/{result.fcpxml_count} ファイルを更新")
    if result.status == RelinkStatus.MISSING_FILES:
        echo(f"[yellow]⚠[/] {name}: {result.rewritten_count}/{result.fcpxml_count} ファイル更新（一部参照先なし）")
        for missing in result.missing_files[:5]:
            echo(f"    [dim]missing: {missing}[/]")
        if len(result.missing_files) > 5:
            echo(f"    [dim]... 他 {len(result.missing_files) - 5} 件[/]")
    if result.unmapped_uris:
        echo(f"    [dim]分類できなかったURI: {len(result.unmapped_uris)} 件（そのまま）[/]")


def run_relink(argv: list[str]) -> None:
    """`textffcut relink` のエントリポイント。"""
    args = _build_parser().parse_args(argv)

    preset_root = Path(args.preset_dir).resolve() if args.preset_dir else None

    if args.all:
        videos_root = Path(args.target).resolve() if args.target else Path.cwd() / "videos"
        if not videos_root.is_dir():
            print(f"エラー: videos/ フォルダが見つかりません: {videos_root}", file=sys.stderr)
            sys.exit(1)
        results = relink_all_in_videos_root(videos_root)
        if not results:
            print(f"対象フォルダがありません（*_TextffCut が無い）: {videos_root}")
            return
        for r in results:
            _print_result(r)
        relinked = sum(1 for r in results if r.status == RelinkStatus.RELINKED)
        missing = sum(1 for r in results if r.status == RelinkStatus.MISSING_FILES)
        print(f"\n完了: {len(results)} フォルダ処理 / 更新 {relinked} / 欠損あり {missing}")
        return

    if not args.target:
        print("エラー: 対象フォルダを指定してください（--all もしくはフォルダパス）", file=sys.stderr)
        sys.exit(1)

    cache_dir = Path(args.target).resolve()
    result = relink_folder(cache_dir, preset_root=preset_root)
    _print_result(result)
    if result.status == RelinkStatus.ERROR:
        sys.exit(1)
