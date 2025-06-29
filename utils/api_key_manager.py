"""
APIキー管理モジュール（セキュア保存）
"""

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .logging import get_logger

logger = get_logger(__name__)


class APIKeyManager:
    """APIキーの暗号化保存・読み込み管理"""

    def __init__(self) -> None:
        # ユーザーホームディレクトリに設定フォルダを作成
        self.config_dir = Path.home() / ".textffcut"
        self.config_dir.mkdir(exist_ok=True)
        self.key_file = self.config_dir / "api_key.enc"

        # 暗号化キーを生成（マシン固有の情報から）
        self._cipher = self._create_cipher()

    def _create_cipher(self) -> Fernet:
        """マシン固有の暗号化キーを生成"""
        # マシン固有の情報を組み合わせて暗号化キーを作成
        machine_info = f"{os.environ.get('USER', 'default')}-{Path.home()}"

        # PBKDF2で安全なキーを生成
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"textffcut_salt_2024",  # 固定ソルト（本格運用では動的にすべき）
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_info.encode()))
        return Fernet(key)

    def save_api_key(self, api_key: str) -> bool:
        """APIキーを暗号化して保存"""
        try:
            if not api_key or not api_key.startswith("sk-") or len(api_key) < 20:
                raise ValueError("無効なAPIキー形式")

            # 暗号化
            encrypted_key = self._cipher.encrypt(api_key.encode())

            # ファイルに保存
            with open(self.key_file, "wb") as f:
                f.write(encrypted_key)

            # ファイル権限を制限（読み取り専用、所有者のみ）
            os.chmod(self.key_file, 0o600)

            logger.info("APIキーを暗号化保存しました")
            return True

        except Exception as e:
            logger.error(f"APIキー保存エラー: {e}")
            return False

    def load_api_key(self) -> str | None:
        """保存されたAPIキーを復号化して読み込み"""
        try:
            if not self.key_file.exists():
                return None

            # ファイルから読み込み
            with open(self.key_file, "rb") as f:
                encrypted_key = f.read()

            # 復号化
            decrypted_key = self._cipher.decrypt(encrypted_key).decode()

            # 有効性チェック
            if not decrypted_key.startswith("sk-"):
                logger.warning("保存されたAPIキーが無効です")
                return None

            logger.info("保存されたAPIキーを読み込みました")
            return decrypted_key

        except Exception as e:
            logger.error(f"APIキー読み込みエラー: {e}")
            return None

    def delete_api_key(self) -> bool:
        """保存されたAPIキーを削除"""
        try:
            if self.key_file.exists():
                os.unlink(self.key_file)
                logger.info("保存されたAPIキーを削除しました")
                return True
            return False

        except Exception as e:
            logger.error(f"APIキー削除エラー: {e}")
            return False

    def has_saved_key(self) -> bool:
        """保存されたAPIキーが存在するか"""
        return self.key_file.exists()

    def mask_api_key(self, api_key: str) -> str:
        """APIキーをマスク表示用に変換"""
        if not api_key or len(api_key) < 10:
            return "***"

        # sk-***...***abc 形式
        prefix = api_key[:3]  # "sk-"
        suffix = api_key[-3:]  # 最後の3文字
        return f"{prefix}***...***{suffix}"


# グローバルインスタンス
api_key_manager = APIKeyManager()
