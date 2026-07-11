from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    def __init__(self, args: Sequence[str], result: CommandResult) -> None:
        self.args_list = list(args)
        self.result = result
        super().__init__(
            f"Command failed with code {result.returncode}: {' '.join(self.args_list)}"
        )


async def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float | None = None,
) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise

    result = CommandResult(
        returncode=process.returncode,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )
    if result.returncode != 0:
        raise CommandError(args, result)
    return result
