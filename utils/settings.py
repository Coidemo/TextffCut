"""
設定管理ユーティリティ
ユーザーの設定を保存・読み込みする機能を提供
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

class SettingsManager:
    """設定管理クラス"""
    
    def __init__(self, settings_file: str = "user_settings.json"):
        """
        初期化
        
        Args:
            settings_file: 設定ファイル名
        """
        self.settings_file = Path.home() / ".buzz-clip" / settings_file
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings = self._load_settings()
    
    def _load_settings(self) -> Dict[str, Any]:
        """設定ファイルから読み込み"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_settings(self):
        """設定をファイルに保存"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定の保存に失敗しました: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値を取得
        
        Args:
            key: 設定キー
            default: デフォルト値
            
        Returns:
            設定値
        """
        return self._settings.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        設定値を保存
        
        Args:
            key: 設定キー
            value: 設定値
        """
        self._settings[key] = value
        self._save_settings()
    
    def update(self, settings: Dict[str, Any]):
        """
        複数の設定を一括更新
        
        Args:
            settings: 設定の辞書
        """
        self._settings.update(settings)
        self._save_settings()
    
    def get_all(self) -> Dict[str, Any]:
        """全ての設定を取得"""
        return self._settings.copy()
    
    def clear(self):
        """全ての設定をクリア"""
        self._settings = {}
        self._save_settings()


# グローバルインスタンス
settings_manager = SettingsManager()