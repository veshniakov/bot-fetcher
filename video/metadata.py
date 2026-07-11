from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VideoMetadata:
    title: str | None = None
    description: str | None = None
    thumbnail: str | None = None
    duration: float | None = None
    uploader: str | None = None
    platform: str | None = None
    content_type: str | None = None
    estimated_filesize: int | None = None
    webpage_url: str | None = None
    width: int | None = None
    height: int | None = None


def metadata_from_ytdlp(info: dict[str, Any], platform: str, content_type: str) -> VideoMetadata:
    return VideoMetadata(
        title=_clean_text(info.get("title")),
        description=_clean_text(info.get("description") or info.get("caption")),
        thumbnail=_best_thumbnail(info),
        duration=_to_float(info.get("duration")),
        uploader=_clean_text(
            info.get("uploader")
            or info.get("channel")
            or info.get("creator")
            or info.get("artist")
        ),
        platform=platform,
        content_type=content_type,
        estimated_filesize=_estimate_filesize(info),
        webpage_url=info.get("webpage_url"),
        width=_to_int(info.get("width")),
        height=_to_int(info.get("height")),
    )


def _best_thumbnail(info: dict[str, Any]) -> str | None:
    thumbnail = info.get("thumbnail")
    if thumbnail:
        return str(thumbnail)

    thumbnails = info.get("thumbnails") or []
    if not thumbnails:
        return None

    def sort_key(item: dict[str, Any]) -> int:
        return int(item.get("width") or 0) * int(item.get("height") or 0)

    best = max(thumbnails, key=sort_key)
    return best.get("url")


def _estimate_filesize(info: dict[str, Any]) -> int | None:
    direct = info.get("filesize") or info.get("filesize_approx")
    if direct:
        return _to_int(direct)

    formats = info.get("formats") or []
    candidates = [
        _to_int(item.get("filesize") or item.get("filesize_approx"))
        for item in formats
        if item.get("filesize") or item.get("filesize_approx")
    ]
    candidates = [item for item in candidates if item]
    if not candidates:
        return None
    return min(candidates)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
