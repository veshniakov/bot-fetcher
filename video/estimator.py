from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompressionPlan:
    target_size_mb: int
    audio_kbps: int
    video_kbps: int
    total_kbps: float
    estimated_time_sec: float
    acceptable: bool
    reason: str | None = None


def build_compression_plan(
    *,
    duration_sec: float,
    target_size_mb: int,
    audio_kbps: int,
    min_video_kbps: int = 150,
    calibration_factor: float | None = None,
) -> CompressionPlan:
    if duration_sec <= 0:
        return CompressionPlan(
            target_size_mb=target_size_mb,
            audio_kbps=audio_kbps,
            video_kbps=0,
            total_kbps=0,
            estimated_time_sec=0,
            acceptable=False,
            reason="duration_unavailable",
        )

    total_kbps = target_size_mb * 8192 / duration_sec
    raw_video_kbps = total_kbps - audio_kbps
    video_kbps = max(int(raw_video_kbps), min_video_kbps)
    acceptable = raw_video_kbps >= min_video_kbps
    estimate_factor = calibration_factor if calibration_factor and calibration_factor > 0 else 0.8
    estimated_time_sec = max(20.0, duration_sec * estimate_factor)

    return CompressionPlan(
        target_size_mb=target_size_mb,
        audio_kbps=audio_kbps,
        video_kbps=video_kbps,
        total_kbps=total_kbps,
        estimated_time_sec=estimated_time_sec,
        acceptable=acceptable,
        reason=None if acceptable else "bitrate_too_low",
    )
