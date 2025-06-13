"""
シンプルなログ管理ユーティリティ（Streamlit非依存）
"""
import logging
import sys
from pathlib import Path
from datetime import datetime


class SimpleLogger:
    """TextffCut CLI用のシンプルなロガー"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.logger = logging.getLogger('textffcut_cli')
        self.logger.setLevel(logging.INFO)
        
        # すでにハンドラーがある場合はスキップ
        if self.logger.handlers:
            return
        
        # コンソールハンドラーのみ（CLI用）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        
        self.logger.addHandler(console_handler)
    
    def info(self, message):
        """情報メッセージ"""
        self.logger.info(message)
    
    def warning(self, message):
        """警告メッセージ"""
        self.logger.warning(message)
    
    def error(self, message):
        """エラーメッセージ"""
        self.logger.error(message)
    
    def debug(self, message):
        """デバッグメッセージ"""
        self.logger.debug(message)