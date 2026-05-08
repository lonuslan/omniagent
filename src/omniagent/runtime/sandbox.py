"""
AgentRuntime — Sandboxed execution environment for individual agents.

Each agent gets its own runtime with:
  - Isolated event stream channel
  - Tool executor with permissions
  - LLM connection from the shared pool
  - Workspace policy enforcement
  - Lifecycle management (init → execute → review → cleanup)
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from .pool import LLMPool
from ..protocol import AgentDescriptor, AgentEvent, IAgent, SubTask, TaskStatus
from .executor import ExecutionContext, ToolExecutor
from .security import ExecutionMode, PermissionHandler, WorkspacePolicy
from .stream import EventStream, progress_event


class AgentRuntime:
    """
    Sandboxed runtime for a single agent instance.

    Provides everything an agent needs to execute:
      - ToolExecutor with permission checking
      - EventStream for progress reporting
      - LLMPool access for model calls
      - Filesystem sandbox (temp workspace)
      - Resource limits and timeouts
    """

    def __init__(
        self,
        agent: IAgent,
        tool_executor: ToolExecutor,
        event_stream: EventStream,
        llm_pool: LLMPool | None = None,
        workspace_policy: WorkspacePolicy | None = None,
    ) -> None:
        self.agent = agent
        self.descriptor = agent.descriptor
        self.tools = tool_executor
        self.events = event_stream
        self.llm = llm_pool
        self.workspace_policy = workspace_policy or WorkspacePolicy()

        self._sandbox_dir: Path | None = None
        self._ctx: ExecutionContext | None = None
        self._initialized = False

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def initialize(self, task_id: str) -> None:
        """Set up the sandbox for this agent."""
        self._sandbox_dir = Path(tempfile.mkdtemp(prefix=f"omniagent_{self.descriptor.id}_"))
        self._ctx = ExecutionContext(
            agent_id=self.descriptor.id,
            task_id=task_id,
            workspace_policy=self.workspace_policy,
        )
        await self.agent.initialize()
        self._initialized = True

        await self.events.publish(
            progress_event(self.descriptor.id, task_id, f"Agent initialized in {self._sandbox_dir}")
        )

    async def execute(self, sub_task: SubTask) -> list[AgentEvent]:
        """Execute a sub-task within the sandbox."""
        if not self._initialized:
            raise RuntimeError(f"Agent {self.descriptor.id} not initialized")

        sub_task.status = TaskStatus.IN_PROGRESS

        await self.events.publish(
            progress_event(self.descriptor.id, sub_task.parent_task_id,
                           f"Starting: {sub_task.title}")
        )

        try:
            events = await self.agent.execute(sub_task)
            sub_task.status = TaskStatus.COMPLETED
            return events
        except Exception as e:
            sub_task.status = TaskStatus.FAILED
            await self.events.publish(
                progress_event(self.descriptor.id, sub_task.parent_task_id,
                               f"Error: {e}")
            )
            raise

    async def review(self, artifact: Any) -> dict[str, Any]:
        """Review another agent's output."""
        if not self._initialized:
            raise RuntimeError(f"Agent {self.descriptor.id} not initialized")
        return await self.agent.review(artifact)

    async def cleanup(self) -> None:
        """Tear down the sandbox and clean up resources."""
        await self.agent.cleanup()
        self._initialized = False

        # Clean up sandbox directory
        if self._sandbox_dir and self._sandbox_dir.exists():
            import shutil
            shutil.rmtree(self._sandbox_dir, ignore_errors=True)
            self._sandbox_dir = None

    @property
    def context(self) -> ExecutionContext | None:
        return self._ctx


# ── Runtime Pool ────────────────────────────────────────────────────────────


class AgentRuntimePool:
    """
    Manages a pool of AgentRuntime instances.

    Multiple agents can run concurrently in their own sandboxes.
    The pool handles resource allocation and lifecycle.
    """

    def __init__(
        self,
        tool_executor: ToolExecutor,
        event_stream: EventStream,
        llm_pool: LLMPool | None = None,
        max_concurrent: int = 5,
    ) -> None:
        self._tool_executor = tool_executor
        self._event_stream = event_stream
        self._llm_pool = llm_pool
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._runtimes: dict[str, AgentRuntime] = {}

    async def acquire(self, agent: IAgent, task_id: str) -> AgentRuntime:
        """Acquire a runtime for an agent. Blocks if pool is full."""
        await self._semaphore.acquire()
        runtime = AgentRuntime(
            agent=agent,
            tool_executor=self._tool_executor,
            event_stream=self._event_stream,
            llm_pool=self._llm_pool,
        )
        await runtime.initialize(task_id)
        self._runtimes[agent.descriptor.id] = runtime
        return runtime

    async def release(self, agent_id: str) -> None:
        """Release an agent's runtime back to the pool."""
        runtime = self._runtimes.pop(agent_id, None)
        if runtime:
            await runtime.cleanup()
            self._semaphore.release()

    @asynccontextmanager
    async def session(self, agent: IAgent, task_id: str):
        """Context manager for agent runtime sessions."""
        runtime = await self.acquire(agent, task_id)
        try:
            yield runtime
        finally:
            await self.release(agent.descriptor.id)

    async def shutdown(self) -> None:
        """Clean up all runtimes."""
        for runtime in list(self._runtimes.values()):
            await runtime.cleanup()
        self._runtimes.clear()
