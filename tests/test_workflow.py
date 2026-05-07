"""Tests for Workflow Engine."""

import uuid

from omniagent.core.workflow import SoftwareLifecycleWorkflow, WorkflowRegistry
from omniagent.protocol import Task


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
        # Each sub-task should depend on the previous one
        for i in range(1, len(sub_tasks)):
            assert sub_tasks[i].dependencies == [sub_tasks[i - 1].id]

    def test_validate_transition(self):
        wf = SoftwareLifecycleWorkflow()
        assert wf.validate_transition("需求确认", "需求分析")
        assert not wf.validate_transition("需求确认", "前端开发")  # skip stage
        assert not wf.validate_transition("部署上线", "需求确认")  # backwards


class TestWorkflowRegistry:
    def test_builtins_registered(self):
        reg = WorkflowRegistry()
        assert "software_lifecycle" in reg.list_all()
        assert "video_production" in reg.list_all()
        assert "document_writing" in reg.list_all()
