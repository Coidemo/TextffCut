"""
textffcut setup サブコマンド

対話型の初期設定ウィザード。
設定は ~/.textffcut/config.json に保存される。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)

CONFIG_DIR = Path.home() / ".textffcut"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    """既存の設定を読み込む"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(config: dict) -> None:
    """設定を保存する"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _mask_key(key: str) -> str:
    """APIキーをマスクして表示"""
    if len(key) <= 8:
        return "****"
    return key[:4] + "..." + key[-4:]


def _prompt_input(prompt: str, default: str = "") -> str:
    """ユーザー入力を取得"""
    try:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
            return result if result else default
        else:
            return input(f"{prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]キャンセルしました[/]")
        sys.exit(0)


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Yes/No入力を取得"""
    hint = "Y/n" if default else "y/N"
    try:
        result = input(f"{prompt} [{hint}]: ").strip().lower()
        if not result:
            return default
        return result in ("y", "yes", "はい")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]キャンセルしました[/]")
        sys.exit(0)


def _prompt_choice(prompt: str, choices: list[str], default: str = "") -> str:
    """選択肢から入力を取得"""
    console.print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        marker = " ◀ 現在" if choice == default else ""
        console.print(f"  [cyan]{i}[/]. {choice}{marker}")

    try:
        result = input(f"番号を入力 [{choices.index(default) + 1 if default in choices else 1}]: ").strip()
        if not result:
            return default if default else choices[0]
        idx = int(result) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
        console.print("[yellow]無効な番号です。デフォルトを使用します。[/]")
        return default if default else choices[0]
    except (ValueError, EOFError, KeyboardInterrupt):
        if isinstance(sys.exc_info()[1], (EOFError, KeyboardInterrupt)):
            console.print("\n[dim]キャンセルしました[/]")
            sys.exit(0)
        return default if default else choices[0]


def run_setup() -> None:
    """setupサブコマンドを実行する"""
    console.print()
    console.print(Panel.fit(
        "[bold]TextffCut 初期設定[/]\n"
        "設定は ~/.textffcut/config.json に保存されます。\n"
        "何度でも再実行できます。",
        border_style="blue",
    ))

    config = _load_config()
    changed = False

    # --- 1. ライセンスキー ---
    console.print("\n[bold]1. ライセンスキー[/]")
    current_license = config.get("license_key", "")
    if current_license:
        console.print(f"  現在の設定: [green]{_mask_key(current_license)}[/]")
        if _prompt_yes_no("  変更しますか？", default=False):
            new_key = _prompt_input("  ライセンスキー")
            if new_key:
                # ライセンス検証
                from textffcut_cli.license import activate
                if activate(new_key):
                    config["license_key"] = new_key
                    changed = True
                    console.print("  [green]✓ ライセンスキーを更新しました[/]")
                else:
                    console.print("  [red]✗ 無効なキーです。変更しませんでした[/]")
    else:
        console.print("  [dim]未設定（買い切りライセンス）[/]")
        new_key = _prompt_input("  ライセンスキー（スキップ: Enter）")
        if new_key:
            from textffcut_cli.license import activate
            if activate(new_key):
                config["license_key"] = new_key
                changed = True
                console.print("  [green]✓ ライセンスキーを登録しました[/]")
            else:
                console.print("  [red]✗ 無効なキーです[/]")

    # --- 2. OpenAI APIキー ---
    console.print("\n[bold]2. OpenAI APIキー[/]")
    console.print("  [dim]clipコマンド: 約2-5円/回、API文字起こし: 約$0.006/分[/]")
    current_api_key = config.get("openai_api_key", "")
    if current_api_key:
        console.print(f"  現在の設定: [green]{_mask_key(current_api_key)}[/]")
        if _prompt_yes_no("  変更しますか？", default=False):
            new_api_key = _prompt_input("  OpenAI APIキー (sk-...)")
            if new_api_key:
                config["openai_api_key"] = new_api_key
                changed = True
                console.print("  [green]✓ APIキーを更新しました[/]")
    else:
        console.print("  [dim]未設定[/]")
        new_api_key = _prompt_input("  OpenAI APIキー (sk-..., スキップ: Enter)")
        if new_api_key:
            config["openai_api_key"] = new_api_key
            changed = True
            console.print("  [green]✓ APIキーを登録しました[/]")

    # --- 3. デフォルト文字起こしモデル ---
    console.print("\n[bold]3. デフォルト文字起こしモデル[/]")
    models = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
    current_model = config.get("default_model", "medium")
    new_model = _prompt_choice("  モデルを選択:", models, default=current_model)
    if new_model != current_model:
        config["default_model"] = new_model
        changed = True
        console.print(f"  [green]✓ デフォルトモデルを {new_model} に設定しました[/]")
    else:
        console.print(f"  [dim]変更なし: {current_model}[/]")

    # --- 作業ディレクトリの自動作成 ---
    videos_dir = Path.cwd() / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"\n[green]✓ 動画フォルダを作成しました: {videos_dir}[/]")
        console.print("  ↑ ここに処理したい動画ファイルを入れてください")
    else:
        console.print(f"\n動画フォルダ: {videos_dir}")

    # --- 保存 ---
    if changed:
        _save_config(config)
        console.print(f"\n[green]✓ 設定を保存しました: {CONFIG_FILE}[/]")
    else:
        console.print("\n[dim]変更はありませんでした[/]")

    # --- サマリー ---
    console.print()
    console.print(Panel.fit(
        _format_summary(config),
        title="設定サマリー",
        border_style="green",
    ))

    console.print("\n[bold]次のステップ:[/]")
    console.print("  textffcut gui                    GUIで操作")
    console.print("  textffcut ./videos/動画.mp4       文字起こし")
    console.print("  textffcut clip ./videos/動画.mp4   AI自動切り抜き")
    console.print()


def _format_summary(config: dict) -> str:
    """設定サマリーをフォーマット"""
    lines = []

    # ライセンス
    license_key = config.get("license_key", "")
    if license_key:
        lines.append(f"ライセンス: [green]{_mask_key(license_key)}[/]")
    else:
        lines.append("ライセンス: [yellow]未設定[/]")

    # APIキー
    api_key = config.get("openai_api_key", "")
    if api_key:
        lines.append(f"OpenAI API: [green]{_mask_key(api_key)}[/]")
    else:
        lines.append("OpenAI API: [yellow]未設定[/]（clipコマンドには必要）")

    # モデル
    model = config.get("default_model", "medium")
    lines.append(f"モデル:     [cyan]{model}[/]")

    return "\n".join(lines)


def get_config_value(key: str, default: str = "") -> str:
    """設定値を取得する（config.json → .env → 環境変数 の優先順位）"""
    import os

    # 1. config.json
    config = _load_config()
    if key in config and config[key]:
        return config[key]

    # 2. .env（dotenvがあれば）
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # 3. 環境変数（キー名のマッピング）
    env_mapping = {
        "openai_api_key": ["OPENAI_API_KEY", "TEXTFFCUT_API_KEY"],
        "license_key": ["TEXTFFCUT_LICENSE_KEY"],
        "default_model": ["TEXTFFCUT_MODEL_SIZE"],
    }

    for env_name in env_mapping.get(key, []):
        val = os.environ.get(env_name, "")
        if val:
            return val

    return default
