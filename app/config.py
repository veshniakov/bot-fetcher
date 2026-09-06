from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _parse_float(value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    return float(value)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_user_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    normalized = value.replace(";", ",").replace(" ", ",")
    ids: set[int] = set()
    for raw_item in normalized.split(","):
        item = raw_item.strip()
        if not item:
            continue
        ids.add(int(item))
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_user_id: int | None
    telegram_api_base_url: str | None
    telegram_local_mode: bool
    max_telegram_upload_mb: int
    telegram_request_timeout_seconds: int
    max_video_height: int
    target_compressed_size_mb: int
    telegram_cloud_limit_mb: int
    ffmpeg_preset: str
    audio_bitrate_kbps: int
    min_video_bitrate_kbps: int
    document_fallback_enabled: bool
    document_fallback_max_height: int
    document_audio_bitrate_kbps: int
    document_min_video_bitrate_kbps: int
    workdir: Path
    cache_dir: Path
    cookies_dir: Path
    ytdlp_cookies_path: Path
    instagram_session_path: Path
    instagram_username: str | None
    pending_task_ttl_minutes: int
    log_level: str
    compression_time_factor: float | None
    proxy_url: str | None = None

    @property
    def telegram_cloud_limit_bytes(self) -> int:
        return self.telegram_cloud_limit_mb * 1024 * 1024

    @property
    def telegram_upload_limit_bytes(self) -> int:
        return self.max_telegram_upload_mb * 1024 * 1024

    @property
    def target_compressed_size_bytes(self) -> int:
        return self.target_compressed_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv()

    admin_raw = os.getenv("ADMIN_USER_ID")
    compression_factor_raw = os.getenv("COMPRESSION_TIME_FACTOR")
    telegram_api_base_url = (os.getenv("TELEGRAM_API_BASE_URL") or "").strip() or None
    telegram_local_mode = _parse_bool(os.getenv("TELEGRAM_LOCAL_MODE"), False)

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        admin_user_id=int(admin_raw) if admin_raw and admin_raw.strip() else None,
        telegram_api_base_url=telegram_api_base_url,
        telegram_local_mode=telegram_local_mode,
        max_telegram_upload_mb=_parse_int(
            os.getenv("MAX_TELEGRAM_UPLOAD_MB"),
            2000 if telegram_local_mode else 50,
        ),
        telegram_request_timeout_seconds=_parse_int(
            os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS"),
            1800 if telegram_local_mode else 60,
        ),
        max_video_height=_parse_int(os.getenv("MAX_VIDEO_HEIGHT"), 720),
        target_compressed_size_mb=_parse_int(os.getenv("TARGET_COMPRESSED_SIZE_MB"), 47),
        telegram_cloud_limit_mb=_parse_int(os.getenv("TELEGRAM_CLOUD_LIMIT_MB"), 50),
        ffmpeg_preset=os.getenv("FFMPEG_PRESET", "veryfast").strip() or "veryfast",
        audio_bitrate_kbps=_parse_int(os.getenv("AUDIO_BITRATE_KBPS"), 96),
        min_video_bitrate_kbps=_parse_int(os.getenv("MIN_VIDEO_BITRATE_KBPS"), 150),
        document_fallback_enabled=_parse_bool(
            os.getenv("DOCUMENT_FALLBACK_ENABLED"),
            True,
        ),
        document_fallback_max_height=_parse_int(os.getenv("DOCUMENT_FALLBACK_MAX_HEIGHT"), 720),
        document_audio_bitrate_kbps=_parse_int(os.getenv("DOCUMENT_AUDIO_BITRATE_KBPS"), 48),
        document_min_video_bitrate_kbps=_parse_int(
            os.getenv("DOCUMENT_MIN_VIDEO_BITRATE_KBPS"),
            60,
        ),
        workdir=Path(os.getenv("WORKDIR", "/data/work")),
        cache_dir=Path(os.getenv("CACHE_DIR", "/data/cache")),
        cookies_dir=Path(os.getenv("COOKIES_DIR", "/data/cookies")),
        ytdlp_cookies_path=Path(os.getenv("YTDLP_COOKIES_PATH", "/data/cookies/cookies.txt")),
        instagram_session_path=Path(
            os.getenv("INSTAGRAM_SESSION_PATH", "/data/cookies/instagram.session")
        ),
        instagram_username=(os.getenv("INSTAGRAM_USERNAME") or "").strip() or None,
        pending_task_ttl_minutes=_parse_int(os.getenv("PENDING_TASK_TTL_MINUTES"), 30),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        compression_time_factor=(
            _parse_float(compression_factor_raw, 1.0)
            if compression_factor_raw and compression_factor_raw.strip()
            else None
        ),
        proxy_url=(os.getenv("PROXY_URL") or "").strip() or None,
    )
