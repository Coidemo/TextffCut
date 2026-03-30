#!/usr/bin/env python3
"""ライセンスキー生成ツール（販売者用・非公開）"""

import hashlib
import hmac
import secrets
import sys

_SECRET = b"coidemo-textffcut-2024-mlx"  # license.py と同じ値
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 紛らわしい文字（I, O, 0, 1）を除外


def _to_safe_chars(hex_str: str) -> str:
    """16進数文字列を _CHARS のみを使った文字列に変換する。"""
    result = []
    for c in hex_str.upper():
        if c in _CHARS:
            result.append(c)
        else:
            # 0→A、1→B、O→C（_CHARSに含まれない文字を置換）
            result.append(_CHARS[int(c, 16) % len(_CHARS)])
        if len(result) == 5:
            break
    return "".join(result)


def generate_key() -> str:
    groups = ["".join(secrets.choice(_CHARS) for _ in range(5)) for _ in range(3)]
    payload = "-".join(groups)
    raw_checksum = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    checksum = _to_safe_chars(raw_checksum)
    groups.append(checksum)
    return "-".join(groups)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for _ in range(n):
        print(generate_key())
