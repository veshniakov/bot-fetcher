from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from downloader.base import InvalidUrlError, UnsupportedStoryUrlError, UnsupportedUrlError

SUPPORTED_MESSAGE = (
    "Поддерживаются: YouTube, YouTube Shorts, Instagram (Reels, посты, Stories), "
    "TikTok, Twitter (X), Reddit, Pinterest, VK Видео."
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
    # Проверка на приватные/локальные адреса для безопасности
    if _is_private_or_local(domain):
        raise UnsupportedUrlError("Local/private addresses are not supported")

    path = parsed.path.strip("/")
    path_parts = [part for part in path.split("/") if part]
    query = parse_qs(parsed.query)

    # 1. YouTube
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

    # 2. Instagram
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

    # 3. TikTok
    if _is_tiktok_domain(domain):
        return DetectedPlatform(
            url=url,
            platform="TikTok",
            content_type="tiktok_video",
            domain=domain,
        )

    # 4. Twitter / X
    if _is_twitter_domain(domain):
        return DetectedPlatform(
            url=url,
            platform="Twitter",
            content_type="twitter_video",
            domain=domain,
        )

    # 5. Reddit
    if _is_reddit_domain(domain):
        return DetectedPlatform(
            url=url,
            platform="Reddit",
            content_type="reddit_video",
            domain=domain,
        )

    # 6. Pinterest
    if _is_pinterest_domain(domain):
        return DetectedPlatform(
            url=url,
            platform="Pinterest",
            content_type="pinterest_video",
            domain=domain,
        )

    # 7. VK
    if _is_vk_domain(domain):
        return DetectedPlatform(
            url=url,
            platform="VK",
            content_type="vk_video",
            domain=domain,
        )

    # 8. Универсальный web video (Rutube, Vimeo, etc.)
    return DetectedPlatform(
        url=url,
        platform="Web",
        content_type="web_video",
        domain=domain,
    )


def _is_youtube_domain(domain: str) -> bool:
    return domain in {"youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com"}


def _is_instagram_domain(domain: str) -> bool:
    return domain in {"instagram.com", "m.instagram.com"}


def _is_tiktok_domain(domain: str) -> bool:
    return domain in {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"} or domain.endswith(".tiktok.com")


def _is_twitter_domain(domain: str) -> bool:
    return domain in {"twitter.com", "x.com", "mobile.twitter.com"}


def _is_reddit_domain(domain: str) -> bool:
    return domain in {"reddit.com", "redd.it", "v.redd.it", "m.reddit.com"} or domain.endswith(".reddit.com")


def _is_pinterest_domain(domain: str) -> bool:
    return domain in {"pinterest.com", "pin.it"} or domain.endswith(".pinterest.com")


def _is_vk_domain(domain: str) -> bool:
    return domain in {"vk.com", "m.vk.com", "vkvideo.ru"} or domain.endswith(".vk.com") or domain.endswith(".vkvideo.ru")


def _is_private_or_local(domain: str) -> bool:
    # Удаляем порт, если указан
    host = domain.split(":")[0].strip()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False
