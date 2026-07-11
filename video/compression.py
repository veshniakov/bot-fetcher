from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings
from utils.shell import CommandError, run_command
from video.estimator import CompressionPlan, build_compression_plan
from video.probe import VideoProbe, probe_video

logger = logging.getLogger(__name__)


class CompressionError(Exception):
    pass


class CompressionTooLossyError(CompressionError):
    pass


async def estimate_compression(
    path: Path,
    settings: Settings,
    *,
    target_size_mb: int | None = None,
    audio_kbps: int | None = None,
    min_video_kbps: int | None = None,
) -> tuple[VideoProbe, CompressionPlan]:
    probe = await probe_video(path)
    plan = build_compression_plan(
        duration_sec=probe.duration,
        target_size_mb=target_size_mb or settings.target_compressed_size_mb,
        audio_kbps=audio_kbps or settings.audio_bitrate_kbps,
        min_video_kbps=min_video_kbps or settings.min_video_bitrate_kbps,
        calibration_factor=settings.compression_time_factor,
    )
    return probe, plan


async def compress_video(
    path: Path,
    output_path: Path,
    settings: Settings,
    *,
    target_size_mb: int | None = None,
    audio_kbps: int | None = None,
    min_video_kbps: int | None = None,
    max_video_height: int | None = None,
) -> Path:
    probe, plan = await estimate_compression(
        path,
        settings,
        target_size_mb=target_size_mb,
        audio_kbps=audio_kbps,
        min_video_kbps=min_video_kbps,
    )
    if not plan.acceptable:
        raise CompressionTooLossyError("Calculated bitrate is too low")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected_audio_kbps = audio_kbps or settings.audio_bitrate_kbps
    selected_max_height = max_video_height or settings.max_video_height
    await _run_ffmpeg(
        path,
        output_path,
        probe,
        plan.video_kbps,
        selected_audio_kbps,
        selected_max_height,
        settings,
    )

    if output_path.stat().st_size <= settings.telegram_cloud_limit_bytes:
        return output_path

    retry_path = output_path.with_name(f"{output_path.stem}.retry{output_path.suffix}")
    lower_bitrate = max(
        int(plan.video_kbps * 0.82),
        min_video_kbps or settings.min_video_bitrate_kbps,
    )
    await _run_ffmpeg(
        path,
        retry_path,
        probe,
        lower_bitrate,
        selected_audio_kbps,
        selected_max_height,
        settings,
    )

    if retry_path.stat().st_size <= settings.telegram_cloud_limit_bytes:
        output_path.unlink(missing_ok=True)
        retry_path.replace(output_path)
        return output_path

    raise CompressionError("Compressed file is still above Telegram limit")


async def _run_ffmpeg(
    input_path: Path,
    output_path: Path,
    probe: VideoProbe,
    video_kbps: int,
    audio_kbps: int,
    max_video_height: int,
    settings: Settings,
) -> None:
    scale_filter = _scale_filter(probe, max_video_height)
    args = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        scale_filter,
        "-c:v",
        "libx264",
        "-preset",
        settings.ffmpeg_preset,
        "-b:v",
        f"{video_kbps}k",
        "-maxrate",
        f"{max(int(video_kbps * 1.25), video_kbps)}k",
        "-bufsize",
        f"{max(video_kbps * 2, video_kbps)}k",
        "-c:a",
        "aac",
        "-b:a",
        f"{audio_kbps}k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        await run_command(args, timeout=None)
    except CommandError:
        logger.exception("ffmpeg compression failed")
        raise CompressionError("ffmpeg compression failed")


def _scale_filter(probe: VideoProbe, max_size: int) -> str:
    width = probe.width or 0
    height = probe.height or 0
    if width and height and height > width:
        return f"scale=trunc(min({max_size}\\,iw)/2)*2:-2"
    return f"scale=-2:trunc(min({max_size}\\,ih)/2)*2"
