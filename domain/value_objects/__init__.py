"""
値オブジェクト

不変で同一性を持たない値を表すオブジェクト。
等価性は属性の値によって判断されます。
"""

from .duration import Duration
from .file_path import FilePath
from .time_range import TimeRange

__all__ = [
    "TimeRange",
    "FilePath",
    "Duration",
]
