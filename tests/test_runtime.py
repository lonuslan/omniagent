"""Tests for Agent Runtime modules."""

import asyncio
import uuid

import pytest

from omniagent.agents.builtin.generators import GeneralAgent, CodeGenAgent
from omniagent.protocol import AgentCapability, SubTask, Task
from omniagent.runtime.executor import ExecutionContext, ToolExecutor
from omniagent.runtime.pool import LLMPool, PoolConfig
from omniagent.runtime.sandbox import AgentRuntime, AgentRuntimePool
from omniagent.runtime.security import (
    ExecutionMode,
    PermissionHandler,
    PermissionLevel,
    PermissionRequest,
    TOOL_PERMISSIONS,
    WorkspacePolicy,
)
from omniagent.runtime.stream import (
    EventStream,
    artifact_event,
    error_event,
    event,
    progress_event,
)
from omniagent.tools.base import BaseTool, ToolDescriptor, ToolParam, ToolRegistry


# ── Security Tests ────────────────────────────────────────────────────────


class TestPermissionHandler:
    def test_plan_mode_read_allowed(self):
        handler = PermissionHandler(ExecutionMode.PLAN)
        result = handler.check("read", {"file_path": "/tmp/x"}, "agent-1")
        assert result is None

    def test_plan_mode_write_denied(self):
        handler = PermissionHandler(ExecutionMode.PLAN)
        result = handler.check("edit", {"file_path": "/tmp/x"}, "agent-1")
        assert result is not None
        assert "only read" in result.reason.lower()

    def test_auto_mode_all_allowed(self):
        handler = PermissionHandler(ExecutionMode.AUTO)
        result = handler.check("bash", {"command": "ls"}, "agent-1")
        assert result is None

    def test_auto_mode_agent_ctrl_blocked(self):
        handler = PermissionHandler(ExecutionMode.AUTO)
        result = handler.check("spawn_agent", {}, "agent-1")
        assert result is not None

    def test_agent_mode_read_allowed(self):
        handler = PermissionHandler(ExecutionMode.AGENT)
        result = handler.check("glob", {"pattern": "*.py"}, "agent-1")
        assert result is None

    def test_agent_mode_write_needs_approval(self):
        handler = PermissionHandler(ExecutionMode.AGENT)
        result = handler.check("write", {"file_path": "/tmp/x", "content": "hi"}, "agent-1")
        assert result is not None
        assert result.tool_name == "write"


class TestWorkspacePolicy:
    def test_path_allowed(self):
        policy = WorkspacePolicy(allowed_paths=["./src"])
        import os
        assert policy.is_path_allowed(os.path.abspath("./src/app.py"))

    def test_path_denied(self):
        policy = WorkspacePolicy(allowed_paths=["./src"], denied_paths=["./src/secrets"])
        import os
        assert not policy.is_path_allowed(os.path.abspath("./src/secrets/key.env"))


# ── EventStream Tests ─────────────────────────────────────────────────────


class TestEventStream:
    async def test_publish_and_subscribe(self):
        stream = EventStream()
        task_id = "task-1"
        evt = event("agent-1", task_id, "started", {"msg": "hello"})

        await stream.publish(evt)

        queue = await stream.subscribe(task_id)
        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received.agent_id == "agent-1"
        assert received.event_type == "started"

    async def test_history_replay(self):
        stream = EventStream()
        evt = event("agent-1", "task-x", "progress")
        await stream.publish(evt)

        history = stream.get_history("task-x")
        assert len(history) == 1


# ── ToolExecutor Tests ───────────────────────────────────────────────────


class EchoTool(BaseTool):
    descriptor = ToolDescriptor(
        name="echo",
        description="Echoes input",
        parameters=[ToolParam(name="text", description="Text to echo")],
        category="general",
    )

    async def execute(self, text: str = "") -> str:
        return f"Echo: {text}"


class TestToolExecutor:
    @pytest.fixture
    def registry(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        return reg

    @pytest.fixture
    def executor(self, registry):
        return ToolExecutor(registry, PermissionHandler(ExecutionMode.AUTO))

    async def test_execute_simple_tool(self, executor, registry):
        from omniagent.llm.types import ToolCall
        tc = ToolCall(id="c1", name="echo", arguments={"text": "hello"})
        ctx = ExecutionContext(agent_id="test", task_id="t1")
        result = await executor.execute(tc, ctx)
        assert result.content == "Echo: hello"
        assert not result.is_error

    async def test_execute_unknown_tool(self, executor):
        from omniagent.llm.types import ToolCall
        tc = ToolCall(id="c1", name="nonexistent", arguments={})
        ctx = ExecutionContext(agent_id="test", task_id="t1")
        result = await executor.execute(tc, ctx)
        assert result.is_error

    async def test_audit_log(self, executor):
        from omniagent.llm.types import ToolCall
        tc = ToolCall(id="c1", name="echo", arguments={"text": "x"})
        ctx = ExecutionContext(agent_id="test", task_id="t1")
        await executor.execute(tc, ctx)
        log = executor.get_audit_log()
        assert len(log) == 1
        assert log[0].tool_name == "echo"


# ── AgentRuntime Tests ──────────────────────────────────────────────────


class TestAgentRuntime:
    async def test_initialize_and_cleanup(self):
        agent = GeneralAgent()
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = ToolExecutor(registry, PermissionHandler(ExecutionMode.AUTO))
        stream = EventStream()
        task_id = "task-runtime-test"

        runtime = AgentRuntime(agent, executor, stream)
        await runtime.initialize(task_id)
        assert runtime._initialized
        assert runtime._sandbox_dir is not None
        assert runtime._sandbox_dir.exists()

        await runtime.cleanup()
        assert not runtime._initialized
