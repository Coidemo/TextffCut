"""ライセンスキー検証（coidemo / textffcut）"""

import hashlib
import hmac
from pathlib import Path

_SECRET = b"coidemo-textffcut-2024-mlx"
_LICENSE_FILE = Path.home() / ".textffcut" / "license"
_PURCHASE_URL = "https://note.com/coidemo"
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 紛らわしい文字（I, O, 0, 1）を除外


def _to_safe_chars(hex_str: str) -> str:
    """16進数文字列を _CHARS のみを使った5文字に変換する。"""
    result = []
    for c in hex_str.upper():
        if c in _CHARS:
            result.append(c)
        else:
            result.append(_CHARS[int(c, 16) % len(_CHARS)])
        if len(result) == 5:
            break
    return "".join(result)


def validate_key(key: str) -> bool:
    """キーの形式と署名を検証する（XXXXX-XXXXX-XXXXX-XXXXX）。"""
    parts = key.strip().upper().split("-")
    if len(parts) != 4 or any(len(p) != 5 for p in parts):
        return False
    payload = "-".join(parts[:3])
    raw_checksum = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    expected = _to_safe_chars(raw_checksum)
    return hmac.compare_digest(parts[3], expected)


def activate(key: str) -> bool:
    """キーを検証してライセンスファイルに保存する。有効なら True を返す。"""
    if not validate_key(key):
        return False
    _LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LICENSE_FILE.write_text(key.strip().upper(), encoding="utf-8")
    return True


def is_licensed() -> bool:
    """ライセンス済みかどうかを確認する。"""
    if not _LICENSE_FILE.exists():
        return False
    return validate_key(_LICENSE_FILE.read_text(encoding="utf-8").strip())


def require_license() -> None:
    """ライセンスがなければエラーメッセージを表示して終了する。"""
    if not is_licensed():
        print(
            "エラー: ライセンスキーが必要です。\n"
            f"  購入: {_PURCHASE_URL}\n"
            "  認証: textffcut activate XXXXX-XXXXX-XXXXX-XXXXX"
        )
        raise SystemExit(1)
