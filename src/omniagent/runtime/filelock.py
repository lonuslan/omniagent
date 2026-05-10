"""
File Lock Manager — Readers-writer locking for concurrent agent file access.

Implements the readers-writer pattern:
  - Multiple agents can READ the same file simultaneously
  - Only one agent can WRITE to a file at a time (exclusive)
  - No reads while a write is in progress

Usage:
    manager = FileLockManager()
    async with manager.read_lock("/path/to/file", agent_id="agent-1"):
        content = read_file(path)
    async with manager.write_lock("/path/to/file", agent_id="agent-2"):
        write_file(path, new_content)
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileLockInfo:
    """State of a single file's lock."""
    path: str
    readers: set[str] = field(default_factory=set)      # agent IDs holding read locks
    writer: str | None = None                            # agent ID holding write lock
    write_waiters: int = 0                               # number of agents waiting to write
    last_modified_by: str | None = None
    last_modified_at: float = 0.0


class FileLockManager:
    """
    Manages file-level read/write locks for concurrent agent access.

    Thread-safe via asyncio primitives. Supports timeout on lock acquisition.
    """

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._locks: dict[str, FileLockInfo] = {}
        self._cond: dict[str, asyncio.Condition] = {}
        self._global_lock = asyncio.Lock()
        self._default_timeout = default_timeout

    def _get_or_create(self, path: str) -> tuple[FileLockInfo, asyncio.Condition]:
        if path not in self._locks:
            self._locks[path] = FileLockInfo(path=path)
            self._cond[path] = asyncio.Condition()
        return self._locks[path], self._cond[path]

    @asynccontextmanager
    async def read_lock(self, path: str, agent_id: str, timeout: float | None = None):
        """
        Acquire a shared read lock. Blocks if a writer is active or waiting.

        Usage:
            async with manager.read_lock("/file", "agent-1"):
                data = open("/file").read()
        """
        timeout = timeout or self._default_timeout
        normalized = str(Path(path).resolve())

        async with self._global_lock:
            info, cond = self._get_or_create(normalized)

        acquired = False
        try:
            async with cond:
                # Wait until no writer and no write waiters (writers have priority)
                deadline = time.monotonic() + timeout
                while info.writer is not None or info.write_waiters > 0:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Read lock timeout ({timeout}s) on {path} — "
                            f"writer: {info.writer}, waiters: {info.write_waiters}"
                        )
                    await asyncio.wait_for(cond.wait(), timeout=remaining)

                info.readers.add(agent_id)
                acquired = True

            yield
        finally:
            if acquired:
                async with cond:
                    info.readers.discard(agent_id)
                    cond.notify_all()

    @asynccontextmanager
    async def write_lock(self, path: str, agent_id: str, timeout: float | None = None):
        """
        Acquire an exclusive write lock. Blocks until no readers and no other writer.

        Usage:
            async with manager.write_lock("/file", "agent-2"):
                open("/file", "w").write(new_content)
        """
        timeout = timeout or self._default_timeout
        normalized = str(Path(path).resolve())

        async with self._global_lock:
            info, cond = self._get_or_create(normalized)

        acquired = False
        try:
            async with cond:
                info.write_waiters += 1
                try:
                    deadline = time.monotonic() + timeout
                    while info.writer is not None or len(info.readers) > 0:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"Write lock timeout ({timeout}s) on {path} — "
                                f"writer: {info.writer}, readers: {len(info.readers)}"
                            )
                        await asyncio.wait_for(cond.wait(), timeout=remaining)

                    info.writer = agent_id
                    acquired = True
                finally:
                    info.write_waiters -= 1

            yield
        finally:
            if acquired:
                async with cond:
                    info.writer = None
                    info.last_modified_by = agent_id
                    info.last_modified_at = time.time()
                    cond.notify_all()

    def get_lock_info(self, path: str) -> FileLockInfo | None:
        """Get current lock state for a path (for diagnostics)."""
        normalized = str(Path(path).resolve())
        return self._locks.get(normalized)

    def get_all_locked_files(self) -> list[FileLockInfo]:
        """Return all files currently locked (for monitoring)."""
        return [
            info for info in self._locks.values()
            if info.writer is not None or len(info.readers) > 0
        ]
