"""
Demo: Multi-Agent Orchestration visual walkthrough.

Connects the OmniAgent orchestrator to the TUI dashboard and runs
a complete software development lifecycle demo with real-time visualization.

Usage:
    python -m omniagent.tui.demo
    or
    omniagent start --tui
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from ..agents.builtin.generators import (
    CodeGenAgent,
    CodeReviewAgent,
    DocWriterAgent,
    GeneralAgent,
    TestAgent,
)
from ..core.orchestrator import Orchestrator
from ..core.analyzer import TaskAnalyzer
from ..core.registry import AgentRegistry
from ..core.workflow import SoftwareLifecycleWorkflow
from ..protocol import AgentCapability, AgentEvent, Task, TaskStatus
from .widgets.pipeline import StageStatus

if TYPE_CHECKING:
    from .app import OmniAgentTUI
    from .widgets.agents_panel import AgentsPanel
    from .widgets.event_log import EventLog
    from .widgets.pipeline import PipelinePanel


async def run_orchestration_demo(app: OmniAgentTUI) -> None:
    """
    Run the full multi-agent orchestration demo inside the TUI.

    1. Set up registry with 5 agents
    2. Submit a task (Build a Todo App)
    3. Visualize: analysis → decomposition → agent assignment → execution
    """

    panels = _get_panels(app)
    pipeline: PipelinePanel = panels["pipeline"]
    event_log: EventLog = panels["event_log"]
    agents_panel: AgentsPanel = panels["agents"]

    event_log.clear()
    pipeline.init_stages()

    # ── Phase 1: Setup ──────────────────────────────────────────────────
    event_log.add_event("system", "Initializing OmniAgent orchestrator...", "system")
    await asyncio.sleep(0.3)

    registry = AgentRegistry()
    _register_all_agents(registry, event_log)
    await asyncio.sleep(0.3)

    orch = Orchestrator(registry)
    event_log.add_event("system", "Orchestrator ready. 6 agents registered.", "success")
    await asyncio.sleep(0.5)

    # ── Phase 2: Task Submission ─────────────────────────────────────────
    event_log.add_event("system", "─" * 30, "info")
    event_log.add_event("orchestrator", "Task received: 'Build a Full-Stack Todo App'", "info")
    await asyncio.sleep(0.3)

    task = Task(
        id=str(uuid.uuid4()),
        title="Build a Full-Stack Todo App",
        description=(
            "Build a full-stack todo application with React (TypeScript + Tailwind) "
            "frontend and Python FastAPI backend with PostgreSQL. Features: "
            "create/update/delete tasks, filter by status, user authentication, "
            "responsive design."
        ),
        domain="software",
        workflow_template="software_lifecycle",
    )

    # ── Phase 3: Task Analysis ───────────────────────────────────────────
    agents_panel.set_agent_status("orchestrator", "running")
    event_log.add_event("orchestrator", "🔬 Analyzing task description...", "thinking")
    await asyncio.sleep(0.6)

    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze(task)
    event_log.add_event(
        "orchestrator",
        f"Domain: {analysis['domain']} | Suggested workflow: {analysis['suggested_workflow']}",
        "info",
    )
    await asyncio.sleep(0.4)

    # ── Phase 4: Decomposition ───────────────────────────────────────────
    event_log.add_event("orchestrator", "🔄 Decomposing into sub-tasks...", "thinking")
    await asyncio.sleep(0.5)

    workflow = SoftwareLifecycleWorkflow()
    sub_tasks = workflow.generate_sub_tasks(task)
    event_log.add_event(
        "orchestrator",
        f"Decomposed into {len(sub_tasks)} stages",
        "success",
    )
    await asyncio.sleep(0.3)

    # ── Phase 5: Agent Assignment ────────────────────────────────────────
    event_log.add_event("orchestrator", "🎯 Selecting optimal agents for each stage...", "thinking")
    await asyncio.sleep(0.5)

    agent_map = {
        0: "general-agent",
        1: "doc-writer-agent",
        2: "code-gen-agent",
        3: "code-gen-agent",
        4: "code-gen-agent",
        5: "test-agent",
        6: "general-agent",
    }

    for i, st in enumerate(sub_tasks):
        best_id = agent_map.get(i, "general-agent")
        best = registry.get(best_id)
        if best:
            st.assigned_agent = best.id
            event_log.add_event(
                "orchestrator",
                f"Stage {i + 1} '[bold]{st.title.split('] ')[1]}[/]' → {best.name}",
                "info",
            )
            await asyncio.sleep(0.15)

    event_log.add_event("orchestrator", "All stages assigned. Beginning execution.", "success")
    agents_panel.set_agent_status("orchestrator", "done")
    await asyncio.sleep(0.4)

    # ── Phase 6: Execution ───────────────────────────────────────────────
    event_log.add_event("system", "─" * 30, "info")
    event_log.add_event("system", "⚡ Starting pipeline execution...", "system")

    stage_names = [s.name for s in workflow.stages]

    for i, st in enumerate(sub_tasks):
        agent_id = st.assigned_agent or "general-agent"
        agents_panel.set_agent_status(agent_id, "running")
        pipeline.set_stage(i, StageStatus.RUNNING, agent_id)

        event_log.add_event(
            agent_id,
            f"Starting: {stage_names[i]}",
            "thinking",
        )
        await asyncio.sleep(0.8)  # Simulate work

        # Simulate agent output
        outputs = [
            f"Analyzed project scope and feature requirements",
            f"Generated technical specification document",
            f"Designed UI wireframes and component tree",
            f"Created React components with TypeScript types",
            f"Built FastAPI endpoints with PostgreSQL schema",
            f"Wrote test suites — 24 unit tests, 8 integration tests",
            f"Generated Docker deployment configs",
        ]
        event_log.add_event(agent_id, outputs[i], "success")

        pipeline.set_stage(i, StageStatus.COMPLETED)
        agents_panel.set_agent_status(agent_id, "done")
        await asyncio.sleep(0.3)

    # ── Phase 7: Completion ──────────────────────────────────────────────
    task.status = TaskStatus.COMPLETED
    done, total = pipeline.get_progress()

    event_log.add_event("system", "─" * 30, "info")
    event_log.add_event(
        "system",
        f"🎉 Project completed! {done}/{total} stages done. Workflow: software_lifecycle",
        "success",
    )
    event_log.add_event(
        "system",
        "Total agents involved: 4 | Total stages: 7 | All tests passing",
        "system",
    )

    # Reset all agent statuses
    for agent_id in ["general-agent", "code-gen-agent", "code-review-agent", "doc-writer-agent", "test-agent"]:
        agents_panel.set_agent_status(agent_id, "idle")


def _register_all_agents(registry: AgentRegistry, event_log: EventLog) -> None:
    for agent_cls in [GeneralAgent, CodeGenAgent, CodeReviewAgent, DocWriterAgent, TestAgent]:
        temp = agent_cls()
        registry.register(temp.descriptor, agent_cls)
        caps = [c.value for c in temp.descriptor.capabilities]
        event_log.add_event("system", f"Registered: {temp.descriptor.name} [{', '.join(caps[:2])}]", "info")


def _get_panels(app: OmniAgentTUI) -> dict:
    from .widgets.agents_panel import AgentsPanel
    from .widgets.event_log import EventLog
    from .widgets.pipeline import PipelinePanel

    return {
        "pipeline": app.query_one("#pipeline-panel", PipelinePanel),
        "event_log": app.query_one("#event-log", EventLog),
        "agents": app.query_one("#agents-panel", AgentsPanel),
    }


def main() -> None:
    """Entry point: launch OmniAgent TUI with demo capability."""
    from .app import OmniAgentTUI

    app = OmniAgentTUI()

    async def demo_runner() -> None:
        await run_orchestration_demo(app)

    app.demo_runner = demo_runner
    app.run()


if __name__ == "__main__":
    main()
