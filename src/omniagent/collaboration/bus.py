"""
Collaboration Bus - The communication backbone for multi-agent collaboration.

Provides:
  - Message routing (point-to-point and broadcast)
  - Event streaming per task
  - Artifact sharing between agents
  - Agent handoff protocol
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ..protocol import AgentEvent, CollaborationMessage


class CollaborationBus:
    """
    Asynchronous message bus for agent-to-agent communication.

    Each task gets its own message namespace so agents working on different
    tasks don't interfere with each other.
    """

    def __init__(self) -> None:
        # task_id → list of (message, event) for replay/audit
        self._task_streams: dict[str, list[CollaborationMessage]] = defaultdict(list)
        # task_id → list of async queues for live subscribers
        self._task_subscribers: dict[str, list[asyncio.Queue[CollaborationMessage]]] = (
            defaultdict(list)
        )
        # agent_id → queue for direct messages
        self._agent_inboxes: dict[str, asyncio.Queue[CollaborationMessage]] = defaultdict(
            asyncio.Queue
        )

    # ── Publishing ────────────────────────────────────────────────────────

    async def publish(self, message: CollaborationMessage) -> None:
        """Publish a message to the task's stream and all subscribers."""
        message.timestamp = message.timestamp or time.time()
        task_id = message.payload.get("task_id", "")

        # Archive
        self._task_streams[task_id].append(message)

        # Notify task subscribers
        for queue in self._task_subscribers[task_id]:
            await queue.put(message)

        # Direct delivery
        if message.receiver_id:
            await self._agent_inboxes[message.receiver_id].put(message)
        else:
            # Broadcast to all agent inboxes in the task
            # (filtered by agents that care about this task)
            for agent_id, inbox in self._agent_inboxes.items():
                if agent_id != message.sender_id:
                    await inbox.put(message)

    # ── Subscription ──────────────────────────────────────────────────────

    async def subscribe(
        self, task_id: str, agent_id: str | None = None
    ) -> AsyncIterator[CollaborationMessage]:
        """
        Subscribe to messages for a specific task. Yields messages as they arrive.
        """
        queue: asyncio.Queue[CollaborationMessage] = asyncio.Queue()
        self._task_subscribers[task_id].append(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            self._task_subscribers[task_id].remove(queue)

    @asynccontextmanager
    async def agent_session(self, agent_id: str):
        """Context manager that sets up an agent's inbox for the session."""
        inbox = self._agent_inboxes[agent_id]
        try:
            yield inbox
        finally:
            pass  # Inbox persists across sessions

    # ── Agent Handoff ─────────────────────────────────────────────────────

    async def handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        context: dict,
    ) -> None:
        """
        Formal handoff from one agent to another, passing full context.
        Used when one agent completes its stage and the next agent picks up.
        """
        message = CollaborationMessage(
            id=str(uuid.uuid4()),
            sender_id=from_agent,
            receiver_id=to_agent,
            message_type="handoff",
            payload={
                "task_id": task_id,
                "context": context,
                "handoff_from": from_agent,
            },
            timestamp=time.time(),
        )
        await self.publish(message)

    # ── History ───────────────────────────────────────────────────────────

    def get_task_history(self, task_id: str) -> list[CollaborationMessage]:
        """Get the full message history for a task (for replay/audit)."""
        return list(self._task_streams.get(task_id, []))


# ── Agent Conversation Protocol ──────────────────────────────────────────────


class ConversationManager:
    """
    Manages structured conversations between agents.

    Supports patterns like:
      - Request/Response: Agent A requests info from Agent B
      - Review/Feedback: Reviewer agent gives feedback to executor
      - Negotiation: Agents discuss and agree on approach
    """

    def __init__(self, bus: CollaborationBus) -> None:
        self.bus = bus
        self._pending_requests: dict[str, asyncio.Future] = {}

    async def request(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        request_type: str,
        payload: dict,
        timeout: float = 30.0,
    ) -> dict:
        """Send a request and await response."""
        msg_id = str(uuid.uuid4())
        message = CollaborationMessage(
            id=msg_id,
            sender_id=from_agent,
            receiver_id=to_agent,
            message_type="request",
            payload={"task_id": task_id, "request_type": request_type, **payload},
            timestamp=time.time(),
        )
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[msg_id] = future
        await self.bus.publish(message)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            return {"error": "timeout", "message": f"No response from {to_agent}"}

    async def respond(
        self,
        from_agent: str,
        request_msg: CollaborationMessage,
        payload: dict,
    ) -> None:
        """Respond to a previous request."""
        response = CollaborationMessage(
            id=str(uuid.uuid4()),
            sender_id=from_agent,
            receiver_id=request_msg.sender_id,
            message_type="response",
            payload=payload,
            reply_to=request_msg.id,
            timestamp=time.time(),
        )
        await self.bus.publish(response)

        # Resolve the pending future
        if request_msg.id in self._pending_requests:
            self._pending_requests[request_msg.id].set_result(payload)
