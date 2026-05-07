"""
Workflow Engine - Defines multi-stage workflow templates for different domains.

Each workflow template knows how to decompose a high-level task into a sequence
of sub-tasks with proper dependencies. This is the "development methodology"
layer of OmniAgent.

Example flows:
  software_lifecycle:  Requirements → Analysis → Prototype → UI → Code → Test → Deploy
  video_production:    Script → Footage → Edit → Audio → Review → Export
  document_writing:    Outline → Draft → Review → Finalize
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from ..protocol import AgentCapability, SubTask, Task


class IWorkflowTemplate(ABC):
    """Abstract workflow template."""

    name: str
    description: str
    stages: list[WorkflowStage]

    def generate_sub_tasks(self, task: Task) -> list[SubTask]:
        """Decompose a task into ordered sub-tasks based on workflow stages."""
        sub_tasks: list[SubTask] = []
        previous_id: str | None = None

        for stage in self.stages:
            st = SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                title=f"[{stage.name}] {task.title}",
                description=f"Stage: {stage.name}\n{stage.description}\n\n{task.description}",
                required_capabilities=stage.required_capabilities,
                dependencies=[previous_id] if previous_id else [],
            )
            sub_tasks.append(st)
            previous_id = st.id

        return sub_tasks

    def validate_transition(self, current_stage: str, next_stage: str) -> bool:
        """Validate that a stage transition is valid in this workflow."""
        stage_names = [s.name for s in self.stages]
        try:
            curr_idx = stage_names.index(current_stage)
            next_idx = stage_names.index(next_stage)
            return next_idx == curr_idx + 1
        except ValueError:
            return False


class WorkflowStage:
    """A single stage in a workflow, with required capabilities."""

    def __init__(
        self,
        name: str,
        description: str,
        required_capabilities: list[AgentCapability],
    ) -> None:
        self.name = name
        self.description = description
        self.required_capabilities = required_capabilities


# ── Built-in Workflow Templates ──────────────────────────────────────────────


class SoftwareLifecycleWorkflow(IWorkflowTemplate):
    """
    Full software development lifecycle workflow.

    Stages: Requirements → Analysis → Prototype Design → UI Design
            → Frontend Code → Backend Code → Testing → Deployment

    This mirrors a real enterprise software development process.
    """

    name = "software_lifecycle"
    description = "Complete software development lifecycle from requirements to deployment"

    stages = [
        WorkflowStage(
            "需求确认",
            "Clarify and confirm project requirements with the user",
            [AgentCapability.GENERAL_PURPOSE],
        ),
        WorkflowStage(
            "需求分析",
            "Analyze requirements and produce a technical specification",
            [AgentCapability.ARCHITECTURE_DESIGN, AgentCapability.DOCUMENTATION],
        ),
        WorkflowStage(
            "原型设计",
            "Design UI/UX prototypes and wireframes",
            [AgentCapability.PROTOTYPE_DESIGN, AgentCapability.UI_DESIGN],
        ),
        WorkflowStage(
            "前端开发",
            "Implement the frontend UI based on prototypes",
            [AgentCapability.CODE_GENERATION, AgentCapability.UI_DESIGN],
        ),
        WorkflowStage(
            "后端开发",
            "Implement backend APIs and business logic",
            [AgentCapability.CODE_GENERATION, AgentCapability.ARCHITECTURE_DESIGN],
        ),
        WorkflowStage(
            "测试",
            "Write and execute tests, perform code review",
            [AgentCapability.TESTING, AgentCapability.CODE_REVIEW],
        ),
        WorkflowStage(
            "部署上线",
            "Deploy to staging, verify, then deploy to production",
            [AgentCapability.DEPLOYMENT],
        ),
    ]


class VideoProductionWorkflow(IWorkflowTemplate):
    """
    Video production workflow.

    Stages: Script → Footage Collection → Editing → Audio → Transitions → Review → Export
    """

    name = "video_production"
    description = "End-to-end video production pipeline"

    stages = [
        WorkflowStage(
            "文案脚本",
            "Write video script and storyboard",
            [AgentCapability.COPYWRITING],
        ),
        WorkflowStage(
            "素材准备",
            "Collect and organize raw footage and assets",
            [AgentCapability.GENERAL_PURPOSE],
        ),
        WorkflowStage(
            "视频剪辑",
            "Edit video timeline, arrange clips",
            [AgentCapability.VIDEO_EDITING],
        ),
        WorkflowStage(
            "音频制作",
            "Voice generation, background music, sound effects",
            [AgentCapability.AUDIO_PRODUCTION],
        ),
        WorkflowStage(
            "转场特效",
            "Add transitions, effects, and visual polish",
            [AgentCapability.VIDEO_EDITING],
        ),
        WorkflowStage(
            "审阅修改",
            "Review the video and apply revisions",
            [AgentCapability.GENERAL_PURPOSE],
        ),
        WorkflowStage(
            "导出发布",
            "Export final video in required formats",
            [AgentCapability.VIDEO_EDITING],
        ),
    ]


class DocumentWritingWorkflow(IWorkflowTemplate):
    """Document writing workflow: Outline → Draft → Review → Finalize."""

    name = "document_writing"
    description = "Structured document creation pipeline"

    stages = [
        WorkflowStage(
            "大纲规划",
            "Create detailed document outline and structure",
            [AgentCapability.COPYWRITING],
        ),
        WorkflowStage(
            "初稿撰写",
            "Write the first draft",
            [AgentCapability.COPYWRITING],
        ),
        WorkflowStage(
            "审阅修订",
            "Review, fact-check, and revise content",
            [AgentCapability.COPYWRITING, AgentCapability.DOCUMENTATION],
        ),
        WorkflowStage(
            "定稿发布",
            "Final formatting and publication",
            [AgentCapability.DOCUMENTATION],
        ),
    ]


# ── Workflow Registry ───────────────────────────────────────────────────────


class WorkflowRegistry:
    """Registry for workflow templates, extensible with custom workflows."""

    _instance: WorkflowRegistry | None = None
    _workflows: dict[str, IWorkflowTemplate] = {}

    def __new__(cls) -> WorkflowRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._register_builtins()
        return cls._instance

    def _register_builtins(self) -> None:
        for wf in [
            SoftwareLifecycleWorkflow(),
            VideoProductionWorkflow(),
            DocumentWritingWorkflow(),
        ]:
            self._workflows[wf.name] = wf

    def register(self, workflow: IWorkflowTemplate) -> None:
        """Register a custom workflow template."""
        self._workflows[workflow.name] = workflow

    def get(self, name: str) -> IWorkflowTemplate | None:
        """Get a workflow template by name."""
        return self._workflows.get(name)

    def list_all(self) -> list[str]:
        """List all registered workflow names."""
        return list(self._workflows.keys())
