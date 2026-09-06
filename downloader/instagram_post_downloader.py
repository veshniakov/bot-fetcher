from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.config import Settings
from downloader.base import DownloadError, InstagramAuthError, MetadataError, UnsupportedUrlError
from video.metadata import VideoMetadata

logger = logging.getLogger(__name__)

SHORTCODE_RE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", re.IGNORECASE)


class InstagramPostDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if self.settings.proxy_url:
            os.environ["http_proxy"] = self.settings.proxy_url
            os.environ["https_proxy"] = self.settings.proxy_url
            os.environ["HTTP_PROXY"] = self.settings.proxy_url
            os.environ["HTTPS_PROXY"] = self.settings.proxy_url
            os.environ["no_proxy"] = "telegram-bot-api,localhost,127.0.0.1,172.16.0.0/12,192.168.0.0/16"
            os.environ["NO_PROXY"] = "telegram-bot-api,localhost,127.0.0.1,172.16.0.0/12,192.168.0.0/16"

    async def get_metadata(self, url: str) -> VideoMetadata:
        try:
            return await asyncio.to_thread(self._get_metadata_sync, url)
        except (InstagramAuthError, MetadataError, UnsupportedUrlError):
            raise
        except Exception as exc:
            logger.exception("Instagram Post metadata extraction failed")
            raise MetadataError("Failed to extract Instagram Post metadata") from exc

    async def download(self, url: str, work_dir: Path) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            return await asyncio.to_thread(self._download_sync, url, work_dir)
        except (InstagramAuthError, DownloadError):
            raise
        except Exception as exc:
            logger.exception("Instagram Post download failed")
            raise DownloadError("Failed to download Instagram Post") from exc

    def _get_metadata_sync(self, url: str) -> VideoMetadata:
        shortcode = _extract_shortcode(url)
        loader = self._init_loader()

        try:
            import instaloader
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except Exception as exc:
            logger.warning("Instaloader failed to fetch post %s: %s", shortcode, exc)
            raise MetadataError("Failed to fetch Instagram Post") from exc

        is_carousel = (post.typename == "GraphSidecar")
        media_count = post.mediacount if is_carousel else 1

        caption_preview = (post.caption or "").strip().replace("\n", " ")
        if len(caption_preview) > 80:
            caption_preview = caption_preview[:77] + "..."

        if is_carousel:
            title = f"📸 Альбом ({media_count} медиа): {caption_preview}" if caption_preview else f"📸 Альбом ({media_count} медиа)"
        elif post.is_video:
            title = f"🎬 Видео: {caption_preview}" if caption_preview else "🎬 Видео"
        else:
            title = f"🖼️ Фото: {caption_preview}" if caption_preview else "🖼️ Фото"

        return VideoMetadata(
            title=title,
            description=post.caption,
            thumbnail=post.url,
            duration=float(post.video_duration) if getattr(post, "video_duration", None) else None,
            uploader=f"@{post.owner_username}" if post.owner_username else None,
            platform="Instagram",
            content_type="instagram_post",
            webpage_url=f"https://www.instagram.com/p/{shortcode}/",
        )

    def _download_sync(self, url: str, work_dir: Path) -> list[Path]:
        shortcode = _extract_shortcode(url)
        loader = self._init_loader()

        try:
            import instaloader
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except Exception as exc:
            logger.warning("Instaloader failed to fetch post %s: %s", shortcode, exc)
            raise DownloadError("Failed to fetch Instagram Post") from exc

        proxies = None
        if self.settings.proxy_url:
            proxies = {"http": self.settings.proxy_url, "https": self.settings.proxy_url}

        downloaded: list[Path] = []

        if post.typename == "GraphSidecar":
            for idx, node in enumerate(post.get_sidecar_nodes()):
                if idx >= 10:
                    break  # Telegram limit for media group is 10 items
                ext = ".mp4" if node.is_video else ".jpg"
                media_url = node.video_url if node.is_video else node.display_url
                target_file = work_dir / f"{idx:02d}{ext}"
                _download_file(media_url, target_file, proxies)
                downloaded.append(target_file)
        elif post.is_video:
            target_file = work_dir / "00.mp4"
            _download_file(post.video_url, target_file, proxies)
            downloaded.append(target_file)
        else:
            target_file = work_dir / "00.jpg"
            _download_file(post.url, target_file, proxies)
            downloaded.append(target_file)

        if not downloaded:
            raise DownloadError("No media files were downloaded")

        return downloaded

    def _init_loader(self):
        import instaloader

        loader = instaloader.Instaloader(
            quiet=True,
            download_pictures=False,
            download_videos=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )
        if self.settings.proxy_url:
            proxies = {"http": self.settings.proxy_url, "https": self.settings.proxy_url}
            loader.context._session.proxies = proxies

        if self.settings.instagram_session_path.exists():
            username = self.settings.instagram_username or "session"
            try:
                loader.load_session_from_file(username, str(self.settings.instagram_session_path))
            except Exception:
                logger.warning("Could not load Instagram session file")

        return loader


def _extract_shortcode(url: str) -> str:
    parsed = urlparse(url)
    match = SHORTCODE_RE.search(parsed.path)
    if not match:
        raise UnsupportedUrlError("Could not extract shortcode from Instagram URL")
    return match.group(1)


def _download_file(url: str, target: Path, proxies: dict[str, str] | None) -> None:
    resp = requests.get(url, proxies=proxies, timeout=30)
    resp.raise_for_status()
    with open(target, "wb") as f:
        f.write(resp.content)
