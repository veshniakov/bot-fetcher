from __future__ import annotations

import shutil
from pathlib import Path

from app.config import Settings


def ensure_data_dirs(settings: Settings) -> None:
    settings.workdir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.cookies_dir.mkdir(parents=True, exist_ok=True)


def create_task_work_dir(settings: Settings, task_id: str) -> Path:
    path = settings.workdir / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_task_work_dir(path: Path | None, settings: Settings) -> None:
    if path is None:
        return
    root = settings.workdir.resolve()
    target = path.resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Refusing to remove path outside workdir: {target}")
    if target.exists():
        shutil.rmtree(target)


def file_size(path: Path) -> int:
    return path.stat().st_size
