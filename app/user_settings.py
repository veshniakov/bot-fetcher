from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class UserSettingsManager:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = asyncio.Lock()
        self._settings: dict[str, dict[str, Any]] = {}
        self._load_sync()

    def _load_sync(self) -> None:
        if not self._file_path.exists():
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                self._settings = json.load(f)
        except Exception:
            logger.exception("Failed to load user settings from %s", self._file_path)

    async def _save(self) -> None:
        try:
            temp_path = self._file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            temp_path.replace(self._file_path)
        except Exception:
            logger.exception("Failed to save user settings to %s", self._file_path)

    async def get_user_settings(self, user_id: int) -> dict[str, Any]:
        async with self._lock:
            return dict(self._settings.get(str(user_id), {}))

    async def is_quick_mode(self, user_id: int) -> bool:
        async with self._lock:
            user_data = self._settings.get(str(user_id), {})
            return bool(user_data.get("quick_mode", False))

    async def toggle_quick_mode(self, user_id: int) -> bool:
        async with self._lock:
            uid = str(user_id)
            if uid not in self._settings:
                self._settings[uid] = {}
            new_value = not bool(self._settings[uid].get("quick_mode", False))
            self._settings[uid]["quick_mode"] = new_value
            await self._save()
            return new_value
