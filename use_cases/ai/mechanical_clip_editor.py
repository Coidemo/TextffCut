"""
フィラー定数の後方互換エイリアス

定数は filler_constants.py に移動済み。
既存コードからのインポート互換のため、re-export する。
"""

from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, FILLER_WORDS  # noqa: F401
