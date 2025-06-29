"""
キーボードショートカットハンドラー
タイムライン編集でのキーボード操作を管理
"""

from collections.abc import Callable
from typing import Any

import streamlit as st

from utils.logging import get_logger

logger = get_logger(__name__)


class KeyboardShortcuts:
    """キーボードショートカット管理クラス"""

    def __init__(self) -> None:
        self.shortcuts: dict[str, dict[str, Any]] = {
            # 再生制御
            "space": {"description": "再生/停止", "action": "toggle_playback", "modifier": None},
            # セグメント移動
            "arrowleft": {"description": "前のセグメントへ", "action": "previous_segment", "modifier": None},
            "arrowright": {"description": "次のセグメントへ", "action": "next_segment", "modifier": None},
            # 時間調整（粗調整）
            "arrowup": {
                "description": "開始時間を0.5秒前へ",
                "action": "adjust_start_time",
                "modifier": None,
                "value": -0.5,
            },
            "arrowdown": {
                "description": "開始時間を0.5秒後へ",
                "action": "adjust_start_time",
                "modifier": None,
                "value": 0.5,
            },
            # 時間調整（微調整）
            "shift+arrowleft": {
                "description": "開始時間を0.1秒前へ",
                "action": "adjust_start_time",
                "modifier": "shift",
                "value": -0.1,
            },
            "shift+arrowright": {
                "description": "開始時間を0.1秒後へ",
                "action": "adjust_start_time",
                "modifier": "shift",
                "value": 0.1,
            },
            "shift+arrowup": {
                "description": "終了時間を0.1秒前へ",
                "action": "adjust_end_time",
                "modifier": "shift",
                "value": -0.1,
            },
            "shift+arrowdown": {
                "description": "終了時間を0.1秒後へ",
                "action": "adjust_end_time",
                "modifier": "shift",
                "value": 0.1,
            },
            # 元に戻す/やり直し
            "ctrl+z": {"description": "元に戻す", "action": "undo", "modifier": "ctrl"},
            "ctrl+y": {"description": "やり直し", "action": "redo", "modifier": "ctrl"},
            "cmd+z": {"description": "元に戻す（Mac）", "action": "undo", "modifier": "cmd"},
            "cmd+shift+z": {"description": "やり直し（Mac）", "action": "redo", "modifier": "cmd+shift"},
        }

        self.action_handlers: dict[str, Callable | None] = {}
        self.enabled = True

    def register_handler(self, action: str, handler: Callable) -> None:
        """アクションハンドラーを登録"""
        self.action_handlers[action] = handler
        logger.debug(f"Registered handler for action: {action}")

    def handle_key_event(self, key_event: dict[str, Any]) -> bool:
        """
        キーイベントを処理

        Args:
            key_event: キーイベント情報

        Returns:
            処理されたかどうか
        """
        if not self.enabled:
            return False

        # キーコードとモディファイアを取得
        key = key_event.get("key", "").lower()
        ctrl_key = key_event.get("ctrlKey", False)
        shift_key = key_event.get("shiftKey", False)
        alt_key = key_event.get("altKey", False)
        meta_key = key_event.get("metaKey", False)  # Cmd key on Mac

        # ショートカットキーを構築
        shortcut_key = ""
        if ctrl_key:
            shortcut_key += "ctrl+"
        if meta_key:
            shortcut_key += "cmd+"
        if shift_key:
            shortcut_key += "shift+"
        if alt_key:
            shortcut_key += "alt+"
        shortcut_key += key

        # ショートカットを検索
        shortcut = self.shortcuts.get(shortcut_key)
        if not shortcut:
            # モディファイアなしでも検索
            shortcut = self.shortcuts.get(key)

        if shortcut:
            action = shortcut["action"]
            handler = self.action_handlers.get(action)

            if handler:
                # ハンドラーを実行
                try:
                    value = shortcut.get("value")
                    if value is not None:
                        handler(value)
                    else:
                        handler()
                    logger.debug(f"Executed action: {action}")
                    return True
                except Exception as e:
                    logger.error(f"Error executing action {action}: {e}")
                    return False
            else:
                logger.warning(f"No handler registered for action: {action}")

        return False

    def get_help_text(self) -> str:
        """ショートカットヘルプテキストを生成"""
        help_lines = ["### キーボードショートカット\n"]

        categories = {
            "再生制御": ["space"],
            "セグメント移動": ["arrowleft", "arrowright"],
            "時間調整": [
                "arrowup",
                "arrowdown",
                "shift+arrowleft",
                "shift+arrowright",
                "shift+arrowup",
                "shift+arrowdown",
            ],
            "編集操作": ["ctrl+z", "ctrl+y", "cmd+z", "cmd+shift+z"],
        }

        for category, keys in categories.items():
            help_lines.append(f"\n**{category}**")
            for key in keys:
                if key in self.shortcuts:
                    shortcut = self.shortcuts[key]
                    key_display = key.replace("+", " + ").upper()
                    help_lines.append(f"- `{key_display}`: {shortcut['description']}")

        return "\n".join(help_lines)

    def enable(self) -> None:
        """ショートカットを有効化"""
        self.enabled = True

    def disable(self) -> None:
        """ショートカットを無効化"""
        self.enabled = False


def inject_keyboard_handler_script() -> None:
    """
    キーボードイベントハンドラーのJavaScriptを注入
    Streamlitページに追加して使用
    """
    script = """
    <script>
    // キーボードイベントハンドラー
    document.addEventListener('keydown', function(e) {
        // テキスト入力中は無視
        if (e.target.tagName === 'INPUT' || 
            e.target.tagName === 'TEXTAREA' || 
            e.target.isContentEditable) {
            return;
        }

        // Streamlitのイベント送信
        const keyEvent = {
            key: e.key,
            keyCode: e.keyCode,
            ctrlKey: e.ctrlKey,
            shiftKey: e.shiftKey,
            altKey: e.altKey,
            metaKey: e.metaKey
        };

        // カスタムイベントを発火
        window.parent.postMessage({
            type: 'keyboard_event',
            data: keyEvent
        }, '*');

        // デフォルト動作を抑制（Space, Arrow keys）
        if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
            e.preventDefault();
        }
    });
    </script>
    """

    st.components.v1.html(script, height=0)
