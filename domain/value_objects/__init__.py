"""
値オブジェクト

不変で同一性を持たない値を表すオブジェクト。
等価性は属性の値によって判断されます。
"""

from .time_range import TimeRange
from .file_path import FilePath
from .duration import Duration

__all__ = [
    "TimeRange",
    "FilePath",
    "Duration",
]
