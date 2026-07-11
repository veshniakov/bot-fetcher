from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.tasks import PendingTaskStore
from storage.paths import remove_task_work_dir

logger = logging.getLogger(__name__)


def cleanup_old_work_files(settings: Settings, older_than_hours: int = 24) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    if not settings.workdir.exists():
        return

    for path in settings.workdir.iterdir():
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified >= cutoff:
                continue
            if path.is_dir():
                remove_task_work_dir(path, settings)
            else:
                path.unlink(missing_ok=True)
            logger.info("Removed old work file: %s", path.name)
        except Exception:
            logger.exception("Failed to cleanup old work path: %s", path)


async def cleanup_pending_tasks_loop(settings: Settings, store: PendingTaskStore) -> None:
    while True:
        await asyncio.sleep(300)
        expired = await store.collect_expired(settings.pending_task_ttl_minutes)
        for task in expired:
            try:
                remove_task_work_dir(task.work_dir, settings)
                logger.info(
                    "Expired pending task cleaned: user_id=%s platform=%s status=%s",
                    task.user_id,
                    task.platform,
                    task.status,
                )
            except Exception:
                logger.exception("Failed to cleanup expired task: task_id=%s", task.task_id)
