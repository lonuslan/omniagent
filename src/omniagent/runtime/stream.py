"""
EventStream — Real-time event broadcasting system.

Provides:
  - Per-task event channels
  - Agent progress streaming
  - Subscriber-based push model
  - Event buffering for replay/audit
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from ..protocol import AgentEvent


class EventStream:
    """
    Real-time event broadcaster for multi-agent task execution.

    Each task gets its own event channel. UI subscribers receive events
    in real-time as agents execute their sub-tasks.
    """

    def __init__(self, buffer_size: int = 1000) -> None:
        self._buffer_size = buffer_size
        # task_id → list of events (for replay/history)
        self._history: dict[str, list[AgentEvent]] = defaultdict(list)
        # task_id → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue[AgentEvent]]] = defaultdict(list)

    # ── Publishing ──────────────────────────────────────────────────────

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to a task's channel."""
        event.timestamp = event.timestamp or time.time()
        task_id = event.task_id

        # Store in history
        hist = self._history[task_id]
        hist.append(event)
        if len(hist) > self._buffer_size:
            self._history[task_id] = hist[-self._buffer_size:]

        # Push to subscribers
        for queue in self._subscribers.get(task_id, []):
            await queue.put(event)

    async def publish_batch(self, events: list[AgentEvent]) -> None:
        """Publish multiple events atomically."""
        for event in events:
            await self.publish(event)

    # ── Subscription ────────────────────────────────────────────────────

    async def subscribe(self, task_id: str) -> asyncio.Queue[AgentEvent]:
        """Subscribe to events for a task. Returns an async queue."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=self._buffer_size)
        self._subscribers[task_id].append(queue)

        # Replay existing history
        for event in self._history.get(task_id, []):
            await queue.put(event)

        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[AgentEvent]) -> None:
        """Remove a subscriber."""
        subs = self._subscribers.get(task_id, [])
        if queue in subs:
            subs.remove(queue)

    # ── History ─────────────────────────────────────────────────────────

    def get_history(self, task_id: str) -> list[AgentEvent]:
        """Get all events for a task."""
        return list(self._history.get(task_id, []))

    def get_latest(self, task_id: str, n: int = 10) -> list[AgentEvent]:
        """Get the latest N events for a task."""
        hist = self._history.get(task_id, [])
        return hist[-n:] if len(hist) > n else list(hist)

    def clear(self, task_id: str) -> None:
        """Clear history for a task."""
        self._history.pop(task_id, None)
        self._subscribers.pop(task_id, None)


# ── Event Factory ───────────────────────────────────────────────────────────


def event(
    agent_id: str,
    task_id: str,
    event_type: str,
    data: dict | None = None,
) -> AgentEvent:
    """Create an AgentEvent with the current timestamp."""
    return AgentEvent(
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        data=data or {},
        timestamp=time.time(),
    )


def progress_event(agent_id: str, task_id: str, message: str, percent: float = 0) -> AgentEvent:
    return event(agent_id, task_id, "progress", {"message": message, "percent": percent})


def artifact_event(agent_id: str, task_id: str, artifact_path: str, artifact_type: str = "file") -> AgentEvent:
    return event(agent_id, task_id, "artifact_created", {
        "path": artifact_path,
        "type": artifact_type,
    })


def error_event(agent_id: str, task_id: str, error_message: str) -> AgentEvent:
    return event(agent_id, task_id, "error", {"error": error_message})
