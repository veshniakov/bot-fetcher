from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from downloader.base import InvalidUrlError, UnsupportedStoryUrlError, UnsupportedUrlError

SUPPORTED_MESSAGE = (
    "Пока поддерживаются YouTube, YouTube Shorts, Instagram Reels, "
    "Instagram posts и Instagram Stories."
)


@dataclass(frozen=True)
class DetectedPlatform:
    url: str
    platform: str
    content_type: str
    domain: str
    story_username: str | None = None
    story_id: str | None = None


def detect_platform(url: str) -> DetectedPlatform:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidUrlError("Invalid URL")

    domain = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    path_parts = [part for part in path.split("/") if part]
    query = parse_qs(parsed.query)

    if _is_youtube_domain(domain):
        if path_parts and path_parts[0] in {"playlist", "live"}:
            raise UnsupportedUrlError("YouTube playlists and live streams are not supported")
        if "list" in query and "v" not in query and domain != "youtu.be":
            raise UnsupportedUrlError("YouTube playlists are not supported")
        content_type = "youtube_shorts" if path_parts[:1] == ["shorts"] else "youtube_video"
        return DetectedPlatform(
            url=url,
            platform="YouTube",
            content_type=content_type,
            domain=domain,
        )

    if _is_instagram_domain(domain):
        if not path_parts:
            raise UnsupportedUrlError("Instagram root URL is not supported")

        first_part = path_parts[0].lower()
        if first_part in {"reel", "reels"} and len(path_parts) >= 2:
            return DetectedPlatform(url, "Instagram", "instagram_reel", domain)
        if first_part in {"p", "tv"} and len(path_parts) >= 2:
            return DetectedPlatform(url, "Instagram", "instagram_post", domain)
        if first_part == "stories":
            if len(path_parts) >= 3 and path_parts[2].isdigit():
                return DetectedPlatform(
                    url=url,
                    platform="Instagram",
                    content_type="instagram_story",
                    domain=domain,
                    story_username=path_parts[1],
                    story_id=path_parts[2],
                )
            raise UnsupportedStoryUrlError("A direct Instagram Story link is required")

        raise UnsupportedUrlError("Unsupported Instagram URL")

    raise UnsupportedUrlError("Unsupported domain")


def _is_youtube_domain(domain: str) -> bool:
    return domain in {"youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com"}


def _is_instagram_domain(domain: str) -> bool:
    return domain in {"instagram.com", "m.instagram.com"}
