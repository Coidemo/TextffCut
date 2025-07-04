"""
設定関連のヘルパー関数

既存のconfig直接アクセスを段階的にConfigurationService経由に
移行するためのヘルパー関数を提供。
"""

from config import config
from services import ConfigurationService

# グローバルなConfigurationServiceインスタンス（遅延初期化）
_config_service = None


def get_config_service() -> ConfigurationService:
    """
    ConfigurationServiceのシングルトンインスタンスを取得

    Returns:
        ConfigurationService: 設定サービスのインスタンス
    """
    global _config_service
    if _config_service is None:
        _config_service = ConfigurationService(config)
    return _config_service


def get_ui_page_title() -> str:
    """
    UIのページタイトルを取得

    Returns:
        str: ページタイトル

    Note:
        将来的にはConfigurationService経由での取得に完全移行予定
    """
    # 現在は直接configから取得（段階的移行のため）
    return config.ui.page_title


def get_ui_layout() -> str:
    """
    UIのレイアウト設定を取得

    Returns:
        str: レイアウト設定（"wide"など）
    """
    return config.ui.layout


def get_whisper_models() -> list[str]:
    """
    利用可能なWhisperモデルのリストを取得

    Returns:
        list[str]: モデル名のリスト
    """
    return config.transcription.whisper_models


def get_api_models() -> list[str]:
    """
    利用可能なAPIモデルのリストを取得

    Returns:
        list[str]: APIモデル名のリスト
    """
    return config.transcription.api_models


def is_api_mode() -> bool:
    """
    API使用モードかどうかを確認

    Returns:
        bool: API使用モードの場合True
    """
    return config.transcription.use_api


def get_default_model_size() -> str:
    """
    デフォルトのモデルサイズを取得

    Returns:
        str: デフォルトのモデルサイズ
    """
    return config.transcription.model_size


def get_isolation_mode() -> str:
    """
    文字起こし処理の分離モードを取得

    Returns:
        str: 分離モード（"subprocess"など）
    """
    return config.transcription.isolation_mode


def set_api_mode(use_api: bool, api_key: str | None = None) -> None:
    """
    API使用モードとAPIキーを設定

    Args:
        use_api: API使用フラグ
        api_key: APIキー（use_apiがTrueの場合は必須）
    """
    config.transcription.use_api = use_api
    if use_api and api_key:
        config.transcription.api_key = api_key
    elif not use_api:
        config.transcription.api_key = None
