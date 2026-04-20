"""
textffcut upgrade サブコマンド

Homebrewを使ったバージョンアップと更新チェック。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console

console = Console(stderr=True)

LAST_CHECK_FILE = Path.home() / ".textffcut" / "last_version_check.json"
CHECK_INTERVAL_HOURS = 24


def _is_newer(latest: str, current: str) -> bool:
    """latestがcurrentより新しいかセマンティックバージョンで比較"""
    try:
        lat = tuple(int(x) for x in latest.split("."))
        cur = tuple(int(x) for x in current.split("."))
        return lat > cur
    except (ValueError, AttributeError):
        return latest != current


def _get_current_version() -> str:
    """現在のバージョンを取得"""
    from utils.version_helpers import get_app_version

    return get_app_version(default_version="unknown")


def _check_latest_version() -> str | None:
    """GitHub Releases APIから最新バージョンを取得"""
    try:
        result = subprocess.run(
            ["gh", "api", "repos/Coidemo/TextffCut/releases/latest", "--jq", ".tag_name"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            tag = result.stdout.strip()
            return tag[1:] if tag.startswith("v") else tag
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # gh CLI がない場合は curl で取得
    try:
        result = subprocess.run(
            ["curl", "-sL", "https://api.github.com/repos/Coidemo/TextffCut/releases/latest"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            tag = data.get("tag_name", "")
            return tag[1:] if tag.startswith("v") else tag if tag else None
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        pass

    return None


def _save_check_result(current: str, latest: str | None) -> None:
    """チェック結果を保存"""
    LAST_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "checked_at": time.time(),
        "current_version": current,
        "latest_version": latest,
    }
    LAST_CHECK_FILE.write_text(json.dumps(data), encoding="utf-8")


def _load_last_check() -> dict | None:
    """前回のチェック結果を読み込む"""
    if LAST_CHECK_FILE.exists():
        try:
            return json.loads(LAST_CHECK_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def check_for_updates_on_startup() -> None:
    """起動時の更新チェック（24時間ごと）"""
    last = _load_last_check()
    if last:
        elapsed_hours = (time.time() - last.get("checked_at", 0)) / 3600
        if elapsed_hours < CHECK_INTERVAL_HOURS:
            # 前回チェックから24時間経過していない
            # ただし新しいバージョンがある場合は通知
            latest = last.get("latest_version")
            current = _get_current_version()
            if latest and current != "unknown" and _is_newer(latest, current):
                console.print(f"[yellow]💡 TextffCut {latest} が利用可能です " f"(現在: {current})[/]")
                console.print("   更新: [cyan]textffcut upgrade[/]\n")
            return

    # チェック実行
    current = _get_current_version()
    latest = _check_latest_version()
    _save_check_result(current, latest)

    if latest and current != "unknown" and _is_newer(latest, current):
        console.print(f"[yellow]💡 TextffCut {latest} が利用可能です " f"(現在: {current})[/]")
        console.print("   更新: [cyan]textffcut upgrade[/]\n")


def run_upgrade(argv: list[str]) -> None:
    """upgradeサブコマンドを実行する"""
    check_only = "--check" in argv

    # キャッシュをクリアして常に最新を取得
    if LAST_CHECK_FILE.exists():
        LAST_CHECK_FILE.unlink(missing_ok=True)

    current = _get_current_version()
    console.print(f"現在のバージョン: [cyan]{current}[/]")

    if check_only:
        console.print("最新バージョンを確認中...")
        latest = _check_latest_version()
        _save_check_result(current, latest)

        if latest is None:
            console.print("[yellow]最新バージョンの取得に失敗しました[/]")
            sys.exit(1)

        if not _is_newer(latest, current):
            console.print(f"[green]✓ 最新バージョンです ({current})[/]")
        else:
            console.print(f"最新バージョン: [green]{latest}[/]")
            console.print(f"\n更新するには: [cyan]textffcut upgrade[/]")
        return

    # brew upgrade 実行
    console.print("\n[bold]Homebrewで更新中...[/]\n")
    try:
        result = subprocess.run(
            ["brew", "upgrade", "textffcut"],
            text=True,
        )
        if result.returncode == 0:
            new_version = _get_current_version()
            if new_version != current:
                console.print(f"\n[green]✓ {current} → {new_version} に更新しました[/]")
            else:
                console.print(f"\n[green]✓ 最新バージョンです ({current})[/]")
            _save_check_result(new_version, new_version)
        else:
            console.print("\n[red]更新に失敗しました[/]")
            console.print("手動で実行してください: [cyan]brew upgrade textffcut[/]")
            sys.exit(1)
    except FileNotFoundError:
        console.print("[red]エラー: Homebrewが見つかりません[/]")
        console.print("Homebrewをインストールしてください: https://brew.sh")
        sys.exit(1)
