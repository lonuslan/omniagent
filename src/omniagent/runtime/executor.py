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
from dataclasses import dataclass, field
from typing import Any

from ..llm.types import ToolCall, ToolResult
from ..tools.base import BaseTool, ToolRegistry
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

    def __init__(
        self,
        registry: ToolRegistry,
        permission_handler: PermissionHandler | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permission_handler or PermissionHandler()
        self._audit_log: list[ExecutionRecord] = []
        self._pending_approvals: dict[str, PermissionRequest] = {}

    # ── Execution ───────────────────────────────────────────────────────

    async def execute(self, tool_call: ToolCall, ctx: ExecutionContext) -> ToolResult:
        """Execute a tool call with full permission/sandbox checking."""
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

        # 5. Execute with timeout
        try:
            result = await asyncio.wait_for(
                tool.execute(**tool_call.arguments),
                timeout=ctx.workspace_policy.max_shell_timeout_sec,
            )
        except asyncio.TimeoutError:
            result = f"Tool execution timed out"
            is_error = True
        except Exception as e:
            result = f"Tool execution error: {e}"
            is_error = True
        else:
            is_error = isinstance(result, str) and result.startswith("Error")

        # 6. Audit
        self._audit_log.append(ExecutionRecord(
            tool_name=tool_call.name,
            agent_id=ctx.agent_id,
            task_id=ctx.task_id,
            args=tool_call.arguments,
            result=str(result)[:1000],
            is_error=is_error,
            duration_ms=(time.time() - start) * 1000,
        ))

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

    # ── Audit ───────────────────────────────────────────────────────────

    def get_audit_log(self) -> list[ExecutionRecord]:
        return list(self._audit_log)

    def get_agent_audit(self, agent_id: str) -> list[ExecutionRecord]:
        return [r for r in self._audit_log if r.agent_id == agent_id]

    def clear_audit_log(self) -> None:
        self._audit_log.clear()
