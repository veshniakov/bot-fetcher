from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from downloader.base import DownloadError, MetadataError, UnsupportedUrlError
from video.metadata import VideoMetadata, metadata_from_ytdlp

logger = logging.getLogger(__name__)


class YtDlpDownloader:
    def __init__(self, settings: Settings, platform: str, content_type: str) -> None:
        self.settings = settings
        self.platform = platform
        self.content_type = content_type

    async def get_metadata(self, url: str) -> VideoMetadata:
        try:
            info = await asyncio.to_thread(self._extract_info, url, False, None)
        except UnsupportedUrlError:
            raise
        except Exception as exc:
            logger.exception("yt-dlp metadata extraction failed")
            raise MetadataError("Failed to extract metadata") from exc

        if info.get("entries"):
            raise UnsupportedUrlError("Playlists are not supported")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise UnsupportedUrlError("Live streams are not supported")

        return metadata_from_ytdlp(info, self.platform, self.content_type)

    async def download(self, url: str, work_dir: Path, *, max_height: int | None = None) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            info = await asyncio.to_thread(self._extract_info, url, True, work_dir, max_height)
            file_path = self._find_downloaded_file(info, work_dir)
        except UnsupportedUrlError:
            raise
        except Exception as exc:
            logger.exception("yt-dlp download failed")
            raise DownloadError("Failed to download video") from exc

        if file_path is None or not file_path.exists():
            raise DownloadError("Downloaded file was not found")
        return file_path

    def _extract_info(
        self,
        url: str,
        download: bool,
        work_dir: Path | None,
        max_height: int | None = None,
    ) -> dict[str, Any]:
        import yt_dlp

        options = self._options(download=download, work_dir=work_dir, max_height=max_height)
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=download)
            if not isinstance(info, dict):
                raise MetadataError("Unexpected metadata shape")
            return info

    def _options(
        self,
        *,
        download: bool,
        work_dir: Path | None,
        max_height: int | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "skip_download": not download,
            "cachedir": str(self.settings.cache_dir),
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
        }

        if self.settings.ytdlp_cookies_path.exists():
            options["cookiefile"] = str(self.settings.ytdlp_cookies_path)

        if download:
            if work_dir is None:
                raise DownloadError("Work directory is required")
            selected_height = max_height or self.settings.max_video_height
            long_side = _long_side_limit(selected_height)
            options.update(
                {
                    "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
                    "merge_output_format": "mp4",
                    "format": (
                        f"bestvideo[ext=mp4][vcodec^=avc1][height<={long_side}][width<={long_side}]"
                        f"+bestaudio[ext=m4a][acodec^=mp4a]/"
                        f"bestvideo[ext=mp4][vcodec^=avc1][height<={long_side}][width<={long_side}]"
                        f"+bestaudio[ext=m4a]/"
                        f"best[ext=mp4][vcodec^=avc1][acodec^=mp4a][height<={long_side}][width<={long_side}]/"
                        f"best[ext=mp4][height<={long_side}][width<={long_side}]/"
                        f"bestvideo[height<={long_side}][width<={long_side}]+bestaudio/"
                        f"best[height<={long_side}][width<={long_side}]"
                    ),
                    "format_sort": [f"res:{selected_height}", "vcodec:h264", "acodec:aac", "ext:mp4:m4a"],
                    "postprocessors": [
                        {
                            "key": "FFmpegVideoRemuxer",
                            "preferedformat": "mp4",
                        }
                    ],
                }
            )

        return options

    @staticmethod
    def _find_downloaded_file(info: dict[str, Any], work_dir: Path) -> Path | None:
        requested_downloads = info.get("requested_downloads") or []
        for item in requested_downloads:
            candidate = item.get("filepath") or item.get("filename")
            if candidate and Path(candidate).exists():
                return Path(candidate)

        candidates = [
            path
            for path in work_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.stat().st_mtime)


def _long_side_limit(max_height: int) -> int:
    if max_height >= 720:
        return 1280
    return max(320, (max_height * 16 + 8) // 9)
