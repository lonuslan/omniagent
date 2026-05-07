"""
Base Agent implementation and agent factory.

Every agent in OmniAgent extends BaseAgent. This provides the common lifecycle,
event emission, and tool access that all agents share.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..protocol import AgentDescriptor, AgentEvent, IAgent, SubTask


class BaseAgent(IAgent):
    """
    Base class for all agents in OmniAgent.

    Provides common lifecycle management and tool integration.
    Subclasses override execute() to implement specific agent behavior.
    """

    descriptor: AgentDescriptor
    _event_queue: list[AgentEvent]

    def __init__(self) -> None:
        self._event_queue = []
        self._initialized = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Called when the agent is loaded into the runtime."""
        self._initialized = True

    async def execute(self, task: SubTask) -> list[AgentEvent]:
        """Execute an assigned sub-task. Override in subclasses."""
        self._emit("started", task.id, {"agent": self.descriptor.name})
        try:
            result = await self._do_execute(task)
            self._emit("completed", task.id, {"result": result})
        except Exception as e:
            self._emit("error", task.id, {"error": str(e)})
        return self._drain_events()

    async def review(self, artifact: Any) -> dict[str, Any]:
        """Review another agent's output."""
        return {"approved": True, "feedback": ""}

    async def cleanup(self) -> None:
        """Called when the agent is being unloaded."""
        self._initialized = False

    # ── Subclass Hook ────────────────────────────────────────────────────

    async def _do_execute(self, task: SubTask) -> Any:
        """Override this in subclasses to implement agent-specific logic."""
        raise NotImplementedError(
            f"Agent '{self.descriptor.name}' must implement _do_execute()"
        )

    # ── Event Helpers ─────────────────────────────────────────────────────

    def _emit(self, event_type: str, task_id: str, data: dict | None = None) -> None:
        self._event_queue.append(
            AgentEvent(
                agent_id=self.descriptor.id,
                task_id=task_id,
                event_type=event_type,
                data=data or {},
                timestamp=time.time(),
            )
        )

    def _drain_events(self) -> list[AgentEvent]:
        events = self._event_queue
        self._event_queue = []
        return events

    def _make_subtask(self, parent_id: str, title: str, description: str, **kw: Any) -> SubTask:
        """Create a new sub-task (for agents that need to delegate further)."""
        return SubTask(
            id=str(uuid.uuid4()),
            parent_task_id=parent_id,
            title=title,
            description=description,
            **kw,
        )


# ── Agent Factory ────────────────────────────────────────────────────────────


class AgentFactory:
    """Factory for instantiating agents from their descriptors."""

    _agent_classes: dict[str, type[BaseAgent]] = {}

    @classmethod
    def register(cls, agent_cls: type[BaseAgent]) -> None:
        """Register an agent class so it can be instantiated by ID."""
        # Use a temporary instance to get the descriptor
        temp = agent_cls()
        cls._agent_classes[temp.descriptor.id] = agent_cls

    @classmethod
    def create(cls, descriptor: AgentDescriptor) -> BaseAgent:
        """Create an agent instance from its descriptor."""
        agent_cls = cls._agent_classes.get(descriptor.id)
        if agent_cls:
            agent = agent_cls()
            agent.descriptor = descriptor
            return agent
        raise ValueError(f"No registered agent class for: {descriptor.id}")
