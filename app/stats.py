from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class StatsManager:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = asyncio.Lock()
        self._unique_users: set[int] = set()
        self._total_downloads: int = 0
        
        # Загружаем при инициализации, если файл существует
        self._load_sync()

    def _load_sync(self) -> None:
        if not self._file_path.exists():
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._unique_users = set(data.get("unique_users", []))
                self._total_downloads = data.get("total_downloads", 0)
        except Exception:
            logger.exception("Failed to load stats from %s", self._file_path)

    async def _save(self) -> None:
        try:
            data = {
                "unique_users": list(self._unique_users),
                "total_downloads": self._total_downloads,
            }
            # Используем временный файл для атомарного сохранения
            temp_path = self._file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self._file_path)
        except Exception:
            logger.exception("Failed to save stats to %s", self._file_path)

    async def add_user(self, user_id: int) -> None:
        async with self._lock:
            if user_id not in self._unique_users:
                self._unique_users.add(user_id)
                await self._save()

    async def increment_downloads(self) -> None:
        async with self._lock:
            self._total_downloads += 1
            await self._save()

    def get_audience_stats(self) -> tuple[int, int]:
        """Возвращает (кол-во пользователей, кол-во загрузок)"""
        return len(self._unique_users), self._total_downloads

    @staticmethod
    def get_system_stats(workdir: Path) -> tuple[int, int]:
        """Возвращает (свободно байт, всего байт) на диске, где находится workdir"""
        try:
            usage = shutil.disk_usage(workdir)
            return usage.free, usage.total
        except Exception:
            logger.exception("Failed to get disk usage for %s", workdir)
            return 0, 0
