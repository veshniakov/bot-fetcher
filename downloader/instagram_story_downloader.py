from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

from app.config import Settings
from downloader.base import DownloadError, InstagramAuthError, MetadataError, UnsupportedStoryUrlError
from video.metadata import VideoMetadata

logger = logging.getLogger(__name__)


class InstagramStoryDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_metadata(self, url: str) -> VideoMetadata:
        try:
            return await asyncio.to_thread(self._get_metadata_sync, url)
        except (InstagramAuthError, UnsupportedStoryUrlError, MetadataError):
            raise
        except Exception as exc:
            logger.exception("Instagram Story metadata extraction failed")
            raise MetadataError("Failed to extract Instagram Story metadata") from exc

    async def download(self, url: str, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            return await asyncio.to_thread(self._download_sync, url, work_dir)
        except (InstagramAuthError, UnsupportedStoryUrlError, DownloadError):
            raise
        except Exception as exc:
            logger.exception("Instagram Story download failed")
            raise DownloadError("Failed to download Instagram Story") from exc

    def _get_metadata_sync(self, url: str) -> VideoMetadata:
        username, story_id = _parse_story_url(url)
        item = self._get_story_item(username, story_id)
        if not getattr(item, "is_video", False):
            raise MetadataError("Instagram Story is not a video")

        return VideoMetadata(
            title=f"Instagram Story @{username}",
            description=None,
            thumbnail=getattr(item, "url", None),
            duration=_as_float(getattr(item, "video_duration", None)),
            uploader=f"@{username}",
            platform="Instagram",
            content_type="instagram_story",
            estimated_filesize=None,
            webpage_url=url,
            width=_as_int(getattr(item, "dimensions", {}).get("width"))
            if isinstance(getattr(item, "dimensions", None), dict)
            else None,
            height=_as_int(getattr(item, "dimensions", {}).get("height"))
            if isinstance(getattr(item, "dimensions", None), dict)
            else None,
        )

    def _download_sync(self, url: str, work_dir: Path) -> Path:
        username, story_id = _parse_story_url(url)
        loader, item = self._get_loader_and_story_item(username, story_id, use_session=True)
        if not getattr(item, "is_video", False):
            raise DownloadError("Instagram Story is not a video")

        before = {path.resolve() for path in work_dir.rglob("*") if path.is_file()}
        loader.download_storyitem(item, target=str(work_dir))
        candidates = [
            path
            for path in work_dir.rglob("*")
            if path.is_file()
            and path.resolve() not in before
            and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
        ]
        if not candidates:
            candidates = [
                path
                for path in work_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
            ]
        if not candidates:
            raise DownloadError("Downloaded Instagram Story video was not found")
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _get_story_item(self, username: str, story_id: str):
        try:
            _, item = self._get_loader_and_story_item(username, story_id, use_session=False)
            return item
        except InstagramAuthError:
            _, item = self._get_loader_and_story_item(username, story_id, use_session=True)
            return item

    def _get_loader_and_story_item(self, username: str, story_id: str, *, use_session: bool):
        import instaloader

        loader = instaloader.Instaloader(
            quiet=True,
            dirname_pattern=str(Path("{target}")),
            filename_pattern="{mediaid}",
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

        if use_session:
            self._load_session(loader)

        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            for story in loader.get_stories(userids=[profile.userid]):
                for item in story.get_items():
                    if _story_item_matches(item, story_id):
                        return loader, item
        except Exception as exc:
            if _looks_like_auth_error(exc):
                raise InstagramAuthError("Instagram session is missing or invalid") from exc
            raise MetadataError("Failed to find Instagram Story") from exc

        raise MetadataError("Instagram Story was not found or has expired")

    def _load_session(self, loader) -> None:
        if not self.settings.instagram_session_path.exists():
            raise InstagramAuthError("Instagram session file is missing")

        username = self.settings.instagram_username or "session"
        try:
            loader.load_session_from_file(username, str(self.settings.instagram_session_path))
            logged_in_user = loader.test_login()
        except Exception as exc:
            raise InstagramAuthError("Instagram session is invalid") from exc

        if not logged_in_user:
            raise InstagramAuthError("Instagram session is invalid")


def _parse_story_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 3 or parts[0].lower() != "stories" or not parts[2].isdigit():
        raise UnsupportedStoryUrlError("A direct Instagram Story link is required")
    return parts[1], parts[2]


def _story_item_matches(item, story_id: str) -> bool:
    values = {
        getattr(item, "mediaid", None),
        getattr(item, "pk", None),
        getattr(item, "id", None),
        getattr(item, "shortcode", None),
    }
    return story_id in {str(value) for value in values if value is not None}


def _looks_like_auth_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    return any(
        marker in name or marker in text
        for marker in ("login", "401", "403", "forbidden", "unauthorized")
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
