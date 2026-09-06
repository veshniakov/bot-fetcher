from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from utils.formatting import format_duration, format_size

logger = logging.getLogger(__name__)


def render_progress_bar(percent: float, length: int = 10) -> str:
    clamped = max(0.0, min(100.0, percent))
    filled_len = int(round(length * clamped / 100.0))
    bar = "▰" * filled_len + "▱" * (length - filled_len)
    return f"{bar} {clamped:.1f}%"


class DownloadProgressReporter:
    def __init__(self, message: Message, update_interval: float = 2.5) -> None:
        self.message = message
        self.update_interval = update_interval
        self._latest_data: dict[str, Any] | None = None
        self._last_rendered_text: str = ""
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def ytdlp_hook(self, d: dict[str, Any]) -> None:
        """Синхронный хук для передачи в yt-dlp progress_hooks."""
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed")
            eta = d.get("eta")

            percent = 0.0
            if total > 0:
                percent = (downloaded / total) * 100.0

            self._latest_data = {
                "downloaded": downloaded,
                "total": total,
                "percent": percent,
                "speed": speed,
                "eta": eta,
            }
        elif status == "finished":
            self._latest_data = {
                "status": "finished",
            }

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._update_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def set_sending_status(self) -> None:
        """Обновляет статус перед отправкой файла в чат."""
        try:
            await self.message.edit_text("📤 <b>Отправка видео в Telegram...</b>")
        except Exception:
            pass

    async def _update_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.update_interval)
            if not self._running:
                break
            if not self._latest_data:
                continue

            text = self._build_status_text(self._latest_data)
            if not text or text == self._last_rendered_text:
                continue

            try:
                await self.message.edit_text(text)
                self._last_rendered_text = text
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except TelegramBadRequest as exc:
                # Текст не изменился или сообщение удалено
                if "message is not modified" in str(exc).lower():
                    continue
                logger.debug("Failed to update progress: %s", exc)
            except Exception:
                logger.debug("Error updating progress message", exc_info=True)

    def _build_status_text(self, data: dict[str, Any]) -> str | None:
        if data.get("status") == "finished":
            return "⏳ <b>Обработка видео...</b>"

        downloaded = data.get("downloaded") or 0
        total = data.get("total") or 0
        percent = data.get("percent") or 0.0
        speed = data.get("speed")
        eta = data.get("eta")

        bar = render_progress_bar(percent)
        lines = [
            "⏳ <b>Скачивание...</b>",
            f"<code>{bar}</code>",
        ]

        size_info = []
        if downloaded:
            size_info.append(format_size(downloaded))
        if total:
            size_info.append(format_size(total))

        if size_info:
            lines.append(f"💾 {' / '.join(size_info)}")

        extra_info = []
        if speed:
            extra_info.append(f"⚡ {format_size(speed)}/s")
        if eta is not None:
            extra_info.append(f"Осталось: {format_duration(eta)}")

        if extra_info:
            lines.append(" • ".join(extra_info))

        return "\n".join(lines)
