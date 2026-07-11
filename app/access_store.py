from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import Settings


class AccessStore:
    def __init__(self, settings: Settings) -> None:
        self._path = settings.allowed_users_path
        self._seed_user_ids = set(settings.allowed_user_ids)
        if settings.admin_user_id is not None:
            self._seed_user_ids.add(settings.admin_user_id)
        self._allowed_user_ids: set[int] = set()
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                raw_ids = data.get("allowed_user_ids", [])
                self._allowed_user_ids = {int(item) for item in raw_ids}
            else:
                self._allowed_user_ids = set()

            before = set(self._allowed_user_ids)
            self._allowed_user_ids.update(self._seed_user_ids)
            if self._allowed_user_ids != before or not self._path.exists():
                self._save_locked()

    async def is_allowed(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._allowed_user_ids

    async def add_user(self, user_id: int) -> bool:
        async with self._lock:
            before = len(self._allowed_user_ids)
            self._allowed_user_ids.add(user_id)
            changed = len(self._allowed_user_ids) != before
            if changed:
                self._save_locked()
            return changed

    async def remove_user(self, user_id: int) -> bool:
        async with self._lock:
            if user_id not in self._allowed_user_ids:
                return False
            self._allowed_user_ids.remove(user_id)
            self._save_locked()
            return True

    async def list_users(self) -> list[int]:
        async with self._lock:
            return sorted(self._allowed_user_ids)

    def _save_locked(self) -> None:
        data = {"allowed_user_ids": sorted(self._allowed_user_ids)}
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self._path)
