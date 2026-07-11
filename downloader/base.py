from __future__ import annotations

from pathlib import Path
from typing import Protocol

from video.metadata import VideoMetadata


class DownloaderError(Exception):
    pass


class InvalidUrlError(DownloaderError):
    pass


class UnsupportedUrlError(DownloaderError):
    pass


class UnsupportedStoryUrlError(UnsupportedUrlError):
    pass


class MetadataError(DownloaderError):
    pass


class DownloadError(DownloaderError):
    pass


class InstagramAuthError(DownloaderError):
    pass


class VideoDownloader(Protocol):
    async def get_metadata(self, url: str) -> VideoMetadata:
        ...

    async def download(self, url: str, work_dir: Path) -> Path:
        ...
