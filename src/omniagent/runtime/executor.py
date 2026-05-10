"""
ToolExecutor — Tool execution engine with permission checking and sandboxing.

Controls:
  1. Permission check before execution
  2. Workspace boundary enforcement
  3. Execution timeout and resource limits
  4. Result capture and error handling
  5. Audit logging of all tool calls
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from ..llm.types import ToolCall, ToolResult
from ..tools.base import BaseTool, ToolRegistry
from .filelock import FileLockManager
from .security import (
    ExecutionMode,
    PermissionHandler,
    PermissionRequest,
    WorkspacePolicy,
)


@dataclass
class ExecutionContext:
    """Context passed to each tool execution."""
    agent_id: str
    task_id: str
    workspace_policy: WorkspacePolicy = field(default_factory=WorkspacePolicy)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """Audit record for a tool execution."""
    tool_name: str
    agent_id: str
    task_id: str
    args: dict[str, Any]
    result: str
    is_error: bool
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


class ToolExecutor:
    """
    Executes tool calls with permission checking, sandboxing, and auditing.

    Usage:
        executor = ToolExecutor(registry, permission_handler)
        result = await executor.execute(tool_call, context)
    """

    # Tools that modify files (need write lock)
    _WRITE_TOOLS = frozenset({"write", "edit", "git_commit", "git_checkout"})
    # Tools that read files (need read lock)
    _READ_TOOLS = frozenset({"read", "glob", "grep"})

    def __init__(
        self,
        registry: ToolRegistry,
        permission_handler: PermissionHandler | None = None,
        file_lock_manager: FileLockManager | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permission_handler or PermissionHandler()
        self._audit_log: list[ExecutionRecord] = []
        self._audit_lock = asyncio.Lock()
        self._pending_approvals: dict[str, PermissionRequest] = {}
        self._file_locks = file_lock_manager or FileLockManager()

    # ── Execution ───────────────────────────────────────────────────────

    async def execute(self, tool_call: ToolCall, ctx: ExecutionContext) -> ToolResult:
        """Execute a tool call with full permission/sandbox checking and file locking."""
        start = time.time()

        # 1. Permission check
        approval = self._permissions.check(tool_call.name, tool_call.arguments, ctx.agent_id)
        if approval:
            self._pending_approvals[tool_call.id] = approval
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Action requires approval: {approval.describe()}",
                is_error=True,
            )

        # 2. Find tool
        tool = self._registry.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Unknown tool: {tool_call.name}",
                is_error=True,
            )

        # 3. Validate args
        if not tool.validate(**tool_call.arguments):
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Invalid arguments for tool: {tool_call.name}",
                is_error=True,
            )

        # 4. Workspace check for file/shell tools
        if tool.descriptor.category in ("file", "shell"):
            if not self._check_workspace(tool_call, ctx):
                return ToolResult(
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    content="Access denied: path outside allowed workspace",
                    is_error=True,
                )

        # 5. Acquire file lock for file tools
        file_path = self._extract_file_path(tool_call)
        lock_ctx = self._acquire_file_lock(tool_call.name, file_path, ctx.agent_id)

        try:
            async with lock_ctx:
                # 6. Execute with timeout
                try:
                    result = await asyncio.wait_for(
                        tool.execute(**tool_call.arguments),
                        timeout=ctx.workspace_policy.max_shell_timeout_sec,
                    )
                except asyncio.TimeoutError:
                    result = "Tool execution timed out"
                    is_error = True
                except Exception as e:
                    result = f"Tool execution error: {e}"
                    is_error = True
                else:
                    is_error = isinstance(result, str) and result.startswith("Error")
        except TimeoutError as e:
            result = str(e)
            is_error = True

        # 7. Audit (thread-safe)
        record = ExecutionRecord(
            tool_name=tool_call.name,
            agent_id=ctx.agent_id,
            task_id=ctx.task_id,
            args=tool_call.arguments,
            result=str(result)[:1000],
            is_error=is_error,
            duration_ms=(time.time() - start) * 1000,
        )
        async with self._audit_lock:
            self._audit_log.append(record)

        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=str(result),
            is_error=is_error,
        )

    async def execute_batch(
        self, tool_calls: list[ToolCall], ctx: ExecutionContext
    ) -> list[ToolResult]:
        """Execute multiple independent tool calls in parallel."""
        tasks = [self.execute(tc, ctx) for tc in tool_calls]
        return list(await asyncio.gather(*tasks))

    # ── Approval flow ──────────────────────────────────────────────────

    def get_pending_approvals(self) -> list[PermissionRequest]:
        return list(self._pending_approvals.values())

    def approve(self, tool_call_id: str) -> bool:
        req = self._pending_approvals.pop(tool_call_id, None)
        if req:
            self._permissions.approve(req)
            return True
        return False

    def deny(self, tool_call_id: str) -> bool:
        req = self._pending_approvals.pop(tool_call_id, None)
        if req:
            self._permissions.deny(req)
            return True
        return False

    # ── Workspace ───────────────────────────────────────────────────────

    def _check_workspace(self, tool_call: ToolCall, ctx: ExecutionContext) -> bool:
        """Check if file operations are within allowed workspace."""
        policy = ctx.workspace_policy
        path = tool_call.arguments.get("file_path") or tool_call.arguments.get("path") or ""
        if not path:
            return True  # No path to check
        return policy.is_path_allowed(path)

    def _extract_file_path(self, tool_call: ToolCall) -> str:
        """Extract the file path from tool arguments."""
        return tool_call.arguments.get("file_path") or tool_call.arguments.get("path") or ""

    @asynccontextmanager
    async def _acquire_file_lock(self, tool_name: str, file_path: str, agent_id: str):
        """Acquire the appropriate file lock (read or write) based on tool type."""
        if not file_path or tool_name not in (self._WRITE_TOOLS | self._READ_TOOLS):
            yield  # No lock needed
            return

        if tool_name in self._WRITE_TOOLS:
            async with self._file_locks.write_lock(file_path, agent_id):
                yield
        else:
            async with self._file_locks.read_lock(file_path, agent_id):
                yield

    # ── Audit ───────────────────────────────────────────────────────────

    def get_audit_log(self) -> list[ExecutionRecord]:
        return list(self._audit_log)

    def get_agent_audit(self, agent_id: str) -> list[ExecutionRecord]:
        return [r for r in self._audit_log if r.agent_id == agent_id]

    def clear_audit_log(self) -> None:
        self._audit_log.clear()
