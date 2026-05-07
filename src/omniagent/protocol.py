"""
OmniAgent Protocol - Core type definitions for the multi-agent collaboration system.

Defines the universal communication protocol that all agents, tools, and skills
must implement. This is the foundation of the entire system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable

# ── Enums ────────────────────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"        # Orchestrator is analyzing the task
    ROUTING = "routing"             # Selecting suitable agents
    DELEGATED = "delegated"         # Assigned to specific agent(s)
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(str, Enum):
    """Categories of capabilities an agent can declare."""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    ARCHITECTURE_DESIGN = "architecture_design"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    UI_DESIGN = "ui_design"
    PROTOTYPE_DESIGN = "prototype_design"
    VIDEO_EDITING = "video_editing"
    AUDIO_PRODUCTION = "audio_production"
    COPYWRITING = "copywriting"
    DATA_ANALYSIS = "data_analysis"
    IMAGE_GENERATION = "image_generation"
    GENERAL_PURPOSE = "general_purpose"


class AgentRole(str, Enum):
    """The role an agent plays in a collaboration session."""
    ORCHESTRATOR = "orchestrator"      # Routes tasks, manages workflow
    EXECUTOR = "executor"              # Executes assigned sub-tasks
    REVIEWER = "reviewer"              # Reviews outputs from executors
    OBSERVER = "observer"              # Monitors progress, provides feedback
    COORDINATOR = "coordinator"        # Coordinates between multiple executors


# ── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class AgentDescriptor:
    """Self-description of an agent, used for registration and capability matching."""
    id: str
    name: str
    version: str
    capabilities: list[AgentCapability]
    role: AgentRole = AgentRole.EXECUTOR
    description: str = ""
    provider: str = "builtin"           # builtin, marketplace, custom
    model_requirements: list[str] = field(default_factory=list)
    tool_dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubTask:
    """A unit of work delegated to a specific agent."""
    id: str
    parent_task_id: str
    title: str
    description: str
    required_capabilities: list[AgentCapability]
    assigned_agent: str | None = None   # agent.id
    status: TaskStatus = TaskStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)   # output file/asset paths
    dependencies: list[str] = field(default_factory=list) # sub-task IDs this depends on


@dataclass
class Task:
    """Top-level task submitted by the user."""
    id: str
    title: str
    description: str
    domain: str = "general"             # software, video, document, etc.
    status: TaskStatus = TaskStatus.PENDING
    sub_tasks: list[SubTask] = field(default_factory=list)
    workflow_template: str | None = None  # workflow template name
    created_at: float = 0.0
    completed_at: float | None = None


@dataclass
class CollaborationMessage:
    """Message passed between agents on the collaboration bus."""
    id: str
    sender_id: str
    receiver_id: str | None = None      # None = broadcast
    message_type: str = "info"          # info, request, response, artifact, error
    payload: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None         # message.id being replied to
    timestamp: float = 0.0


@dataclass
class AgentEvent:
    """Event emitted by an agent during execution."""
    agent_id: str
    task_id: str
    event_type: str                     # started, progress, artifact_created, error, completed
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


# ── Runtime Protocols ────────────────────────────────────────────────────────


@runtime_checkable
class IAgent(Protocol):
    """Protocol that every agent (builtin, custom, marketplace) must implement."""

    descriptor: AgentDescriptor

    async def initialize(self) -> None:
        """Called once when the agent is loaded into the runtime."""
        ...

    async def execute(self, task: SubTask) -> list[AgentEvent]:
        """Execute an assigned sub-task and emit progress events."""
        ...

    async def review(self, artifact: Any) -> dict[str, Any]:
        """Review another agent's output and provide feedback."""
        ...

    async def cleanup(self) -> None:
        """Called when the agent is being unloaded."""
        ...


@runtime_checkable
class ITool(Protocol):
    """Protocol that every tool must implement."""

    name: str
    description: str

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given parameters."""
        ...

    def validate_params(self, **kwargs: Any) -> bool:
        """Validate input parameters before execution."""
        ...


@runtime_checkable
class IWorkflow(Protocol):
    """Protocol for workflow templates."""

    name: str
    description: str
    stages: list[str]

    def generate_sub_tasks(self, task: Task) -> list[SubTask]:
        """Decompose a top-level task into sub-tasks based on workflow stages."""
        ...

    def validate_transition(self, from_stage: str, to_stage: str) -> bool:
        """Check if a stage transition is valid."""
        ...
