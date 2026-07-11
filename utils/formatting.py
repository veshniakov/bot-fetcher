from __future__ import annotations

from math import ceil
from urllib.parse import urlparse


def format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(bytes_count: int | None) -> str | None:
    if bytes_count is None:
        return None
    mb = bytes_count / 1024 / 1024
    if mb >= 1:
        return f"{mb:.1f} MB"
    kb = bytes_count / 1024
    return f"{kb:.0f} KB"


def format_time_estimate(seconds: float | int | None) -> str:
    if seconds is None:
        return "несколько минут"
    value = max(1, int(ceil(float(seconds))))
    if value < 60:
        return f"{value} сек."
    minutes = ceil(value / 60)
    if minutes < 60:
        return f"{minutes} мин."
    hours = minutes // 60
    rest = minutes % 60
    if rest:
        return f"{hours} ч. {rest} мин."
    return f"{hours} ч."


def url_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")
