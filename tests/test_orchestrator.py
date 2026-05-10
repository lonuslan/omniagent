"""Tests for Orchestrator."""

import pytest

from omniagent.core.orchestrator import Orchestrator, OrchestratorConfig
from omniagent.core.registry import AgentRegistry
from omniagent.protocol import (
    AgentCapability,
    AgentDescriptor,
    AgentEvent,
    Task,
    TaskStatus,
)
from omniagent.agents.builtin.generators import GeneralAgent, CodeGenAgent


def _make_task(description: str) -> Task:
    return Task(id="test-1", title="Test Task", description=description)


@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register(GeneralAgent().descriptor, GeneralAgent)
    r.register(CodeGenAgent().descriptor, CodeGenAgent)
    return r


@pytest.fixture
def orchestrator(registry):
    return Orchestrator(registry, config=OrchestratorConfig(max_retries_per_stage=1))


class TestOrchestratorSubmit:
    async def test_submit_returns_tuple(self, orchestrator):
        task = _make_task("Build a todo app with React")
        result = await orchestrator.submit(task)
        assert isinstance(result, tuple)
        assert len(result) == 2

    async def test_submit_returns_task_and_analysis(self, orchestrator):
        task = _make_task("Build a todo app with React")
        returned_task, analysis = await orchestrator.submit(task)
        assert returned_task is task
        assert hasattr(analysis, "domain")
        assert hasattr(analysis, "suggested_stages")

    async def test_submit_sets_task_status(self, orchestrator):
        task = _make_task("Build a web application")
        await orchestrator.submit(task)
        assert task.status == TaskStatus.DELEGATED

    async def test_submit_generates_sub_tasks(self, orchestrator):
        task = _make_task("Build a REST API with Python FastAPI")
        returned_task, analysis = await orchestrator.submit(task)
        assert len(returned_task.sub_tasks) > 0

    async def test_submit_assigns_agents(self, orchestrator):
        task = _make_task("Write code for a calculator app")
        returned_task, analysis = await orchestrator.submit(task)
        for st in returned_task.sub_tasks:
            assert st.assigned_agent is not None


class TestOrchestratorExecute:
    async def test_execute_returns_events(self, orchestrator):
        task = _make_task("Build a simple calculator")
        task, analysis = await orchestrator.submit(task)
        events = await orchestrator.execute(task)
        assert isinstance(events, list)
        assert all(isinstance(e, AgentEvent) for e in events)

    async def test_execute_completes_task(self, orchestrator):
        task = _make_task("Create a hello world script")
        task, analysis = await orchestrator.submit(task)
        await orchestrator.execute(task)
        assert task.status == TaskStatus.COMPLETED

    async def test_execute_with_empty_sub_tasks(self, orchestrator):
        task = _make_task("Simple task")
        task, _ = await orchestrator.submit(task)
        # Even with sub_tasks, execute should handle gracefully
        events = await orchestrator.execute(task)
        assert isinstance(events, list)


class TestOrchestratorConfig:
    def test_default_config(self):
        config = OrchestratorConfig()
        assert config.max_retries_per_stage == 2
        assert config.parallel_stages is True

    def test_custom_config(self, registry):
        config = OrchestratorConfig(max_retries_per_stage=5, parallel_stages=False)
        orch = Orchestrator(registry, config=config)
        assert orch.config.max_retries_per_stage == 5
        assert orch.config.parallel_stages is False


class TestOrchestratorInstantiateAgent:
    def test_instantiate_registered_agent(self, orchestrator, registry):
        desc = GeneralAgent().descriptor
        agent = orchestrator._instantiate_agent(desc)
        assert agent is not None

    def test_instantiate_unknown_agent(self, orchestrator):
        desc = AgentDescriptor(
            id="nonexistent", name="Ghost", version="1.0",
            capabilities=[AgentCapability.CODE_GENERATION],
        )
        agent = orchestrator._instantiate_agent(desc)
        assert agent is None
