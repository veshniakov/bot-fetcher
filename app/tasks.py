from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from video.metadata import VideoMetadata


WAITING_DOWNLOAD_CONFIRMATION = "waiting_download_confirmation"
DOWNLOADING = "downloading"
WAITING_COMPRESSION_CONFIRMATION = "waiting_compression_confirmation"
COMPRESSING = "compressing"
SENDING = "sending"
COMPLETED = "completed"
CANCELLED = "cancelled"
FAILED = "failed"

TERMINAL_STATUSES = {COMPLETED, CANCELLED, FAILED}


@dataclass
class PendingTask:
    task_id: str
    user_id: int
    chat_id: int
    url: str
    platform: str
    content_type: str
    metadata: VideoMetadata | None = None
    downloaded_file_path: Path | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = WAITING_DOWNLOAD_CONFIRMATION
    work_dir: Path | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class PendingTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, PendingTask] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        user_id: int,
        chat_id: int,
        url: str,
        platform: str,
        content_type: str,
        work_dir: Path | None = None,
    ) -> PendingTask:
        async with self._lock:
            task = PendingTask(
                task_id=uuid.uuid4().hex,
                user_id=user_id,
                chat_id=chat_id,
                url=url,
                platform=platform,
                content_type=content_type,
                work_dir=work_dir,
            )
            self._tasks[task.task_id] = task
            return task

    async def get(self, task_id: str) -> PendingTask | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def has_active_task(self, user_id: int) -> bool:
        async with self._lock:
            return any(
                task.user_id == user_id and not task.is_terminal
                for task in self._tasks.values()
            )

    async def set_status(self, task_id: str, status: str) -> PendingTask | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = status
            task.touch()
            return task

    async def update(self, task_id: str, **fields: Any) -> PendingTask | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            for key, value in fields.items():
                setattr(task, key, value)
            task.touch()
            return task

    async def remove(self, task_id: str) -> PendingTask | None:
        async with self._lock:
            return self._tasks.pop(task_id, None)

    async def collect_expired(self, ttl_minutes: int) -> list[PendingTask]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        expired: list[PendingTask] = []
        async with self._lock:
            for task_id, task in list(self._tasks.items()):
                if task.updated_at < cutoff:
                    task.status = CANCELLED
                    expired.append(self._tasks.pop(task_id))
        return expired
