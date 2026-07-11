from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from utils.shell import run_command


@dataclass
class VideoProbe:
    duration: float
    width: int | None
    height: int | None
    size_bytes: int
    video_codec: str | None
    audio_codec: str | None


async def probe_video(path: Path) -> VideoProbe:
    result = await run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    format_info = data.get("format") or {}
    streams = data.get("streams") or []
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})

    duration = _as_float(format_info.get("duration")) or _as_float(video_stream.get("duration"))
    if duration is None or duration <= 0:
        raise ValueError("Video duration is unavailable")

    return VideoProbe(
        duration=duration,
        width=_as_int(video_stream.get("width")),
        height=_as_int(video_stream.get("height")),
        size_bytes=path.stat().st_size,
        video_codec=video_stream.get("codec_name"),
        audio_codec=audio_stream.get("codec_name"),
    )


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
