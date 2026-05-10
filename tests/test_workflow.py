"""Tests for Workflow Engine."""

import uuid

from omniagent.core.analyzer import TaskAnalysis
from omniagent.core.orchestrator import Orchestrator, OrchestratorConfig
from omniagent.core.registry import AgentRegistry
from omniagent.core.workflow import (
    DocumentWritingWorkflow,
    SoftwareLifecycleWorkflow,
    WorkflowRegistry,
)
from omniagent.protocol import AgentCapability, Task


class TestSoftwareLifecycleWorkflow:
    def test_generates_seven_stages(self):
        wf = SoftwareLifecycleWorkflow()
        assert len(wf.stages) == 7

    def test_stage_names(self):
        wf = SoftwareLifecycleWorkflow()
        names = [s.name for s in wf.stages]
        assert "需求确认" in names
        assert "部署上线" in names

    def test_generate_sub_tasks(self):
        wf = SoftwareLifecycleWorkflow()
        task = Task(
            id=str(uuid.uuid4()),
            title="Test Project",
            description="A test project",
        )
        sub_tasks = wf.generate_sub_tasks(task)
        assert len(sub_tasks) == 7
        for i in range(1, len(sub_tasks)):
            assert sub_tasks[i].dependencies == [sub_tasks[i - 1].id]

    def test_validate_transition(self):
        wf = SoftwareLifecycleWorkflow()
        assert wf.validate_transition("需求确认", "需求分析")
        assert not wf.validate_transition("需求确认", "前端开发")
        assert not wf.validate_transition("部署上线", "需求确认")


class TestWorkflowRegistry:
    def test_builtins_registered(self):
        reg = WorkflowRegistry()
        assert "software_lifecycle" in reg.list_all()
        assert "video_production" in reg.list_all()
        assert "document_writing" in reg.list_all()

    def test_get_returns_template(self):
        reg = WorkflowRegistry()
        wf = reg.get("software_lifecycle")
        assert wf is not None
        assert isinstance(wf, SoftwareLifecycleWorkflow)

    def test_get_unknown_returns_none(self):
        reg = WorkflowRegistry()
        assert reg.get("nonexistent") is None

    def test_register_custom(self):
        reg = WorkflowRegistry()
        custom = DocumentWritingWorkflow()
        custom.name = "custom_test"
        custom.description = "Test custom"
        reg.register(custom)
        assert "custom_test" in reg.list_all()
        assert reg.get("custom_test") is custom


class TestOrchestratorWorkflowFallback:
    """Test that Orchestrator falls back to WorkflowRegistry when analyzer produces no stages."""

    def _make_orchestrator(self) -> Orchestrator:
        registry = AgentRegistry()
        return Orchestrator(registry, config=OrchestratorConfig())

    def test_software_domain_uses_workflow_template(self):
        orch = self._make_orchestrator()
        task = Task(id="t1", title="Build app", description="Build an app")
        analysis = TaskAnalysis(domain="software", summary="Build app", suggested_stages=[])
        sub_tasks = orch._generate_sub_tasks(task, analysis)
        assert len(sub_tasks) == 7
        assert sub_tasks[0].title == "[需求确认] Build app"

    def test_video_domain_uses_workflow_template(self):
        orch = self._make_orchestrator()
        task = Task(id="t2", title="Make video", description="Make a video")
        analysis = TaskAnalysis(domain="video", summary="Make video", suggested_stages=[])
        sub_tasks = orch._generate_sub_tasks(task, analysis)
        assert len(sub_tasks) == 7
        assert sub_tasks[0].title == "[文案脚本] Make video"

    def test_document_domain_uses_workflow_template(self):
        orch = self._make_orchestrator()
        task = Task(id="t3", title="Write doc", description="Write a doc")
        analysis = TaskAnalysis(domain="document", summary="Write doc", suggested_stages=[])
        sub_tasks = orch._generate_sub_tasks(task, analysis)
        assert len(sub_tasks) == 4

    def test_unknown_domain_single_stage_fallback(self):
        orch = self._make_orchestrator()
        task = Task(id="t4", title="Do stuff", description="Do stuff")
        analysis = TaskAnalysis(
            domain="quantum_computing", summary="Do stuff",
            suggested_stages=[],
            required_capabilities=[AgentCapability.GENERAL_PURPOSE],
        )
        sub_tasks = orch._generate_sub_tasks(task, analysis)
        assert len(sub_tasks) == 1
        assert sub_tasks[0].title == "Do stuff"

    def test_stages_from_analyzer_used_over_template(self):
        orch = self._make_orchestrator()
        task = Task(id="t5", title="Build app", description="Build app")
        analysis = TaskAnalysis(
            domain="software", summary="Build app",
            suggested_stages=[
                {"name": "Custom Stage 1", "description": "First", "capabilities": ["code_generation"]},
                {"name": "Custom Stage 2", "description": "Second", "capabilities": ["testing"]},
            ],
        )
        sub_tasks = orch._generate_sub_tasks(task, analysis)
        assert len(sub_tasks) == 2
        assert sub_tasks[0].title == "Custom Stage 1"

    def test_list_workflows(self):
        orch = self._make_orchestrator()
        workflows = orch.list_workflows()
        assert len(workflows) >= 3
        names = [w["name"] for w in workflows]
        assert "software_lifecycle" in names
        assert all("stages" in w for w in workflows)
