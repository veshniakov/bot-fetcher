from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

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

        # YouTube плейлисты не поддерживаем, но карусели/посты Instagram и других платформ разрешаем
        if info.get("entries"):
            if self.platform == "YouTube":
                raise UnsupportedUrlError("Playlists are not supported")
            entries = [e for e in info.get("entries") if isinstance(e, dict)]
            if entries:
                first = entries[0]
                meta = metadata_from_ytdlp(first, self.platform, self.content_type)
                return meta

        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise UnsupportedUrlError("Live streams are not supported")

        return metadata_from_ytdlp(info, self.platform, self.content_type)

    async def download(
        self,
        url: str,
        work_dir: Path,
        *,
        max_height: int | None = None,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            info = await asyncio.to_thread(
                self._extract_info,
                url,
                True,
                work_dir,
                max_height,
                True,
                progress_hook,
            )
            file_path = self._find_downloaded_file(info, work_dir)
        except UnsupportedUrlError:
            raise
        except Exception as exc:
            logger.exception("yt-dlp download failed")
            raise DownloadError("Failed to download video") from exc

        if file_path is None or not file_path.exists():
            raise DownloadError("Downloaded file was not found")
        return file_path

    async def download_audio(
        self,
        url: str,
        work_dir: Path,
        *,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            info = await asyncio.to_thread(
                self._extract_audio_info,
                url,
                work_dir,
                True,
                progress_hook,
            )
            file_path = self._find_downloaded_audio_file(info, work_dir)
        except Exception as exc:
            logger.exception("yt-dlp audio download failed")
            raise DownloadError("Failed to download audio") from exc

        if file_path is None or not file_path.exists():
            raise DownloadError("Downloaded audio file was not found")
        return file_path

    async def download_all(
        self,
        url: str,
        work_dir: Path,
        *,
        max_height: int | None = None,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(
                self._extract_info,
                url,
                True,
                work_dir,
                max_height,
                True,
                progress_hook,
                allow_playlist=True,
            )
            files = self._find_all_downloaded_files(work_dir)
        except Exception as exc:
            logger.exception("yt-dlp download_all failed")
            raise DownloadError("Failed to download media group") from exc

        if not files:
            raise DownloadError("No media files found")
        return files

    def _extract_info(
        self,
        url: str,
        download: bool,
        work_dir: Path | None,
        max_height: int | None = None,
        use_cookies: bool = True,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        allow_playlist: bool = False,
    ) -> dict[str, Any]:
        import yt_dlp

        options = self._options(
            download=download,
            work_dir=work_dir,
            max_height=max_height,
            use_cookies=use_cookies,
            progress_hook=progress_hook,
            allow_playlist=allow_playlist,
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=download)
                if not isinstance(info, dict):
                    raise MetadataError("Unexpected metadata shape")
                return info
        except yt_dlp.utils.DownloadError as exc:
            err_msg = str(exc)
            if use_cookies and self.settings.ytdlp_cookies_path.exists() and any(
                code in err_msg for code in ("403", "Forbidden", "Sign in")
            ):
                logger.warning(
                    "yt-dlp encountered auth/403 error with cookies (%s), retrying without cookies...",
                    exc,
                )
                return self._extract_info(
                    url,
                    download=download,
                    work_dir=work_dir,
                    max_height=max_height,
                    use_cookies=False,
                    progress_hook=progress_hook,
                    allow_playlist=allow_playlist,
                )
            raise

    def _extract_audio_info(
        self,
        url: str,
        work_dir: Path,
        use_cookies: bool = True,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        import yt_dlp

        options = self._audio_options(
            work_dir=work_dir,
            use_cookies=use_cookies,
            progress_hook=progress_hook,
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not isinstance(info, dict):
                    raise MetadataError("Unexpected metadata shape")
                return info
        except yt_dlp.utils.DownloadError as exc:
            err_msg = str(exc)
            if use_cookies and self.settings.ytdlp_cookies_path.exists() and any(
                code in err_msg for code in ("403", "Forbidden", "Sign in")
            ):
                logger.warning("yt-dlp audio 403 error, retrying without cookies...")
                return self._extract_audio_info(
                    url,
                    work_dir=work_dir,
                    use_cookies=False,
                    progress_hook=progress_hook,
                )
            raise

    def _options(
        self,
        *,
        download: bool,
        work_dir: Path | None,
        max_height: int | None = None,
        use_cookies: bool = True,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        allow_playlist: bool = False,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": not allow_playlist,
            "skip_download": not download,
            "cachedir": str(self.settings.cache_dir),
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
            "geo_bypass": True,
        }

        if self.platform == "YouTube":
            options["extractor_args"] = {
                "youtube": {
                    "player_client": ["android", "ios", "mweb"],
                    "player_skip": ["webpage", "configs"],
                }
            }

        if getattr(self.settings, "proxy_url", None):
            options["proxy"] = self.settings.proxy_url

        if use_cookies and self.settings.ytdlp_cookies_path.exists():
            options["cookiefile"] = str(self.settings.ytdlp_cookies_path)

        if progress_hook and download:
            options["progress_hooks"] = [progress_hook]

        if download:
            if work_dir is None:
                raise DownloadError("Work directory is required")
            selected_height = max_height or self.settings.max_video_height
            long_side = _long_side_limit(selected_height)
            options.update(
                {
                    "outtmpl": str(work_dir / "%(id)s_%(autonumber)s.%(ext)s" if allow_playlist else work_dir / "%(id)s.%(ext)s"),
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

    def _audio_options(
        self,
        *,
        work_dir: Path,
        use_cookies: bool = True,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "cachedir": str(self.settings.cache_dir),
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
            "geo_bypass": True,
            "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
            ],
        }

        if self.platform == "YouTube":
            options["extractor_args"] = {
                "youtube": {
                    "player_client": ["android", "ios", "mweb"],
                    "player_skip": ["webpage", "configs"],
                }
            }

        if getattr(self.settings, "proxy_url", None):
            options["proxy"] = self.settings.proxy_url

        if use_cookies and self.settings.ytdlp_cookies_path.exists():
            options["cookiefile"] = str(self.settings.ytdlp_cookies_path)

        if progress_hook:
            options["progress_hooks"] = [progress_hook]

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

    @staticmethod
    def _find_downloaded_audio_file(info: dict[str, Any], work_dir: Path) -> Path | None:
        candidates = [
            path
            for path in work_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.stat().st_mtime)

    @staticmethod
    def _find_all_downloaded_files(work_dir: Path) -> list[Path]:
        valid_exts = {".mp4", ".mkv", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".webp"}
        files = [
            path
            for path in sorted(work_dir.iterdir())
            if path.is_file() and path.suffix.lower() in valid_exts
        ]
        return files


def _long_side_limit(max_height: int) -> int:
    if max_height >= 720:
        return 1920 if max_height >= 1080 else 1280
    return max(320, (max_height * 16 + 8) // 9)
