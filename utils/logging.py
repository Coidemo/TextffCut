"""
ログ管理ユーティリティ
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st


class BuzzClipLogger:
    """TextffCut用のロガークラス"""

    _instance: Optional["BuzzClipLogger"] = None
    _initialized: bool

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self.logger = logging.getLogger("textffcut")
        self.logger.setLevel(logging.DEBUG)

        # ログディレクトリの作成
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # ファイルハンドラー（詳細ログ）
        log_file = log_dir / f'textffcut_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # コンソールハンドラー（重要なログのみ）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)

        # ハンドラーを追加
        self.logger.handlers.clear()
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.log_file = log_file

    def debug(self, message: str) -> None:
        """デバッグレベルのログ"""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """情報レベルのログ"""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """警告レベルのログ"""
        self.logger.warning(message)

    def error(self, message: str, exc_info: bool = True) -> None:
        """エラーレベルのログ"""
        self.logger.error(message, exc_info=exc_info)

    def critical(self, message: str, exc_info: bool = True) -> None:
        """クリティカルレベルのログ"""
        self.logger.critical(message, exc_info=exc_info)


# グローバルロガーインスタンス
logger = BuzzClipLogger()


def get_logger(name: str | None = None) -> BuzzClipLogger:
    """
    ロガーインスタンスを取得

    Args:
        name: ロガー名（現在は未使用）

    Returns:
        BuzzClipLoggerインスタンス
    """
    return logger


def log_function_call(func):
    """関数呼び出しをログに記録するデコレータ"""

    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"Calling function: {func_name}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Function {func_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Function {func_name} failed: {str(e)}")
            raise

    return wrapper


def show_log_info() -> None:
    """Streamlit UIでログ情報を表示"""
    with st.expander("📋 デバッグ情報", expanded=False):
        st.info(f"ログファイル: {logger.log_file}")
        if st.button("最新のログを表示"):
            try:
                with open(logger.log_file, encoding="utf-8") as f:
                    lines = f.readlines()
                    # 最新の50行を表示
                    recent_logs = "".join(lines[-50:])
                    st.code(recent_logs, language="log")
            except Exception as e:
                st.error(f"ログの読み込みに失敗しました: {e}")
