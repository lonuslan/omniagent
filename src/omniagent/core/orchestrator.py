"""
Task Orchestrator - The "brain" of OmniAgent.

Analyzes incoming user tasks, decomposes them into sub-tasks, selects the most
suitable agents via capability matching, and coordinates parallel/sequential execution.

This is the core innovation: autonomous agent selection based on task semantics.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

from ..protocol import (
    AgentCapability,
    AgentEvent,
    AgentRole,
    CollaborationMessage,
    SubTask,
    Task,
    TaskStatus,
)
from .registry import AgentRegistry


class TaskAnalyzer:
    """
    Analyzes a user's task description and determines:
      1. Domain (software, video, document, etc.)
      2. Required capabilities
      3. Suggested workflow template
      4. Sub-task decomposition strategy
    """

    # Domain detection patterns — expanded over time
    DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "software": [
            "代码", "开发", "前端", "后端", "API", "bug", "部署",
            "code", "develop", "frontend", "backend", "api",
            "test", "build", "deploy", "react", "python", "database",
        ],
        "video": [
            "视频", "剪辑", "转场", "字幕", "配音", "画面",
            "video", "edit", "transition", "subtitle", "clip",
        ],
        "document": [
            "文档", "报告", "PPT", "文案", "写作",
            "document", "report", "presentation", "article",
        ],
        "data": [
            "数据", "分析", "报表", "统计", "图表",
            "data", "analysis", "report", "statistics", "chart",
        ],
    }

    def analyze(self, task: Task) -> dict[str, object]:
        """Analyze a task and return structured analysis."""
        domain = self._detect_domain(task.description)
        capabilities = self._infer_capabilities(task.description, domain)
        workflow = self._suggest_workflow(domain)
        return {
            "domain": domain,
            "required_capabilities": capabilities,
            "suggested_workflow": workflow,
        }

    def _detect_domain(self, description: str) -> str:
        text = description.lower()
        scores: dict[str, int] = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            scores[domain] = sum(1 for kw in keywords if kw in text)
        return max(scores, key=scores.get) if max(scores.values()) > 0 else "general"

    def _infer_capabilities(
        self, _description: str, domain: str
    ) -> list[AgentCapability]:
        """Infer required capabilities based on domain and description."""
        defaults = {
            "software": [
                AgentCapability.ARCHITECTURE_DESIGN,
                AgentCapability.CODE_GENERATION,
                AgentCapability.CODE_REVIEW,
                AgentCapability.TESTING,
                AgentCapability.DEPLOYMENT,
            ],
            "video": [
                AgentCapability.VIDEO_EDITING,
                AgentCapability.AUDIO_PRODUCTION,
                AgentCapability.COPYWRITING,
            ],
            "document": [AgentCapability.COPYWRITING, AgentCapability.DOCUMENTATION],
            "data": [AgentCapability.DATA_ANALYSIS],
        }
        return defaults.get(domain, [AgentCapability.GENERAL_PURPOSE])

    def _suggest_workflow(self, domain: str) -> str:
        workflows = {
            "software": "software_lifecycle",      # 需求→设计→编码→测试→部署
            "video": "video_production",            # 脚本→素材→剪辑→音频→导出
            "document": "document_writing",         # 大纲→草稿→审阅→定稿
            "data": "data_pipeline",                # 采集→清洗→分析→可视化
        }
        return workflows.get(domain, "generic")


# ── Orchestrator ─────────────────────────────────────────────────────────────


class Orchestrator:
    """
    Central orchestrator that coordinates the entire multi-agent workflow.

    Responsibilities:
      1. Analyze incoming tasks (via TaskAnalyzer)
      2. Decompose into sub-tasks (via Workflow templates)
      3. Select optimal agents for each sub-task
      4. Manage execution order (respecting dependencies)
      5. Handle inter-agent communication
      6. Aggregate results back to the user
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.analyzer = TaskAnalyzer()
        self._event_handlers: list[AgentEventCallback] = []
        self._active_tasks: dict[str, Task] = {}

    # ── Event System ──────────────────────────────────────────────────────

    def on_event(self, handler: AgentEventCallback) -> None:
        """Register a callback for agent events."""
        self._event_handlers.append(handler)

    async def _emit(self, event: AgentEvent) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers:
            await handler(event)

    # ── Task Processing ───────────────────────────────────────────────────

    async def submit(self, task: Task) -> Task:
        """Submit a new task for orchestration."""
        task.status = TaskStatus.ANALYZING
        self._active_tasks[task.id] = task

        # Phase 1: Analyze
        analysis = self.analyzer.analyze(task)
        task.status = TaskStatus.ROUTING

        # Phase 2: Route to workflow for decomposition
        sub_tasks = await self._decompose(task, analysis)

        # Phase 3: Select and assign agents
        await self._assign_agents(sub_tasks)

        task.sub_tasks = sub_tasks
        task.status = TaskStatus.DELEGATED
        return task

    async def execute(self, task: Task) -> Sequence[AgentEvent]:
        """Execute all sub-tasks respecting dependency order, return all events."""
        all_events: list[AgentEvent] = []
        task.status = TaskStatus.IN_PROGRESS

        # Topological execution respecting dependencies
        completed: set[str] = set()
        remaining = list(task.sub_tasks)

        while remaining:
            # Find tasks whose dependencies are all satisfied
            ready = [
                st
                for st in remaining
                if all(dep in completed for dep in st.dependencies)
            ]
            if not ready:
                # Circular dependency or all remaining tasks have unmet deps
                break

            # Execute ready tasks in parallel
            results = await asyncio.gather(
                *[self._execute_sub_task(st) for st in ready],
                return_exceptions=True,
            )

            for st, events in zip(ready, results):
                if isinstance(events, Exception):
                    st.status = TaskStatus.FAILED
                    all_events.append(
                        AgentEvent(
                            agent_id=st.assigned_agent or "orchestrator",
                            task_id=st.id,
                            event_type="error",
                            data={"error": str(events)},
                        )
                    )
                else:
                    st.status = TaskStatus.COMPLETED
                    all_events.extend(events)
                completed.add(st.id)

            remaining = [st for st in remaining if st.id not in completed]

        task.status = TaskStatus.COMPLETED
        return all_events

    async def _decompose(self, task: Task, analysis: dict[str, object]) -> list[SubTask]:
        """Decompose a task into sub-tasks using the appropriate workflow template."""
        from .workflow import WorkflowRegistry

        wf_name = str(analysis.get("suggested_workflow", "generic"))
        try:
            workflow = WorkflowRegistry().get(wf_name)
            if workflow:
                return workflow.generate_sub_tasks(task)
        except Exception:
            pass

        # Fallback: single sub-task
        return [
            SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                title=task.title,
                description=task.description,
                required_capabilities=analysis["required_capabilities"],  # type: ignore
            )
        ]

    async def _assign_agents(self, sub_tasks: list[SubTask]) -> None:
        """Select the best agent for each sub-task."""
        for st in sub_tasks:
            best = self.registry.find_best(st.required_capabilities)
            if best:
                st.assigned_agent = best.id
            else:
                # No matching agent — the orchestrator may prompt user to
                # install or create one via marketplace
                st.assigned_agent = None

    async def _execute_sub_task(self, sub_task: SubTask) -> list[AgentEvent]:
        """Execute a single sub-task through its assigned agent."""
        if not sub_task.assigned_agent:
            return [
                AgentEvent(
                    agent_id="orchestrator",
                    task_id=sub_task.id,
                    event_type="error",
                    data={
                        "error": f"No agent found for capabilities: {sub_task.required_capabilities}"
                    },
                )
            ]

        descriptor = self.registry.get(sub_task.assigned_agent)
        if not descriptor:
            return [
                AgentEvent(
                    agent_id="orchestrator",
                    task_id=sub_task.id,
                    event_type="error",
                    data={"error": f"Agent not found: {sub_task.assigned_agent}"},
                )
            ]

        # In production, this loads the agent into the Runtime sandbox
        # and invokes agent.execute(sub_task)
        await self._emit(
            AgentEvent(
                agent_id=sub_task.assigned_agent,
                task_id=sub_task.id,
                event_type="started",
                data={"agent_name": descriptor.name},
            )
        )
        return []

    # ── Collaboration ─────────────────────────────────────────────────────

    async def route_message(self, message: CollaborationMessage) -> None:
        """Route an inter-agent message through the collaboration bus."""
        # If receiver is specified, deliver directly.
        # If broadcast, deliver to all agents in the same task context.
        pass


AgentEventCallback = object  # real type: Callable[[AgentEvent], Awaitable[None]]
