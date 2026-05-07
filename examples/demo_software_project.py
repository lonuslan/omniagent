"""
Demo: Multi-Agent Collaborative Software Development.

This example demonstrates how OmniAgent orchestrates a complete software
development lifecycle — from requirements to deployment — using multiple
specialized agents working in concert.

Run: python -m omniagent.cli run "Build a todo app with React frontend and Python backend"
"""

from __future__ import annotations

import asyncio
import uuid

from omniagent.agents.builtin.generators import (
    CodeGenAgent,
    CodeReviewAgent,
    DocWriterAgent,
    GeneralAgent,
    TestAgent,
)
from omniagent.collaboration.bus import CollaborationBus, ConversationManager
from omniagent.core.orchestrator import Orchestrator, TaskAnalyzer
from omniagent.core.registry import AgentRegistry
from omniagent.core.workflow import SoftwareLifecycleWorkflow
from omniagent.protocol import AgentCapability, SubTask, Task, TaskStatus


async def demo_software_lifecycle():
    """
    Demonstrate the full software development lifecycle with multi-agent collaboration.
    """
    print("=" * 60)
    print("  OmniAgent Demo: Software Development Lifecycle")
    print("=" * 60)

    # 1. Setup
    registry = AgentRegistry()
    _register_agents(registry)

    bus = CollaborationBus()
    orch = Orchestrator(registry)

    # 2. User submits a task
    task = Task(
        id=str(uuid.uuid4()),
        title="Build a Todo App",
        description=(
            "Build a full-stack todo application with React frontend (TypeScript, "
            "Tailwind CSS) and Python FastAPI backend with PostgreSQL. "
            "Features: create/update/delete tasks, filter by status, "
            "user authentication, responsive design."
        ),
        domain="software",
        workflow_template="software_lifecycle",
    )

    # 3. Orchestrator analyzes the task
    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze(task)
    print(f"\n📋 Task Analysis:")
    print(f"   Domain: {analysis['domain']}")
    print(f"   Required capabilities: {analysis['required_capabilities']}")
    print(f"   Suggested workflow: {analysis['suggested_workflow']}")

    # 4. Decompose using the software lifecycle workflow
    workflow = SoftwareLifecycleWorkflow()
    sub_tasks = workflow.generate_sub_tasks(task)
    print(f"\n🔄 Workflow Stages ({len(sub_tasks)} stages):")
    for st in sub_tasks:
        print(f"   [{st.id[:8]}] {st.title}")

    # 5. Assign agents to each sub-task
    print(f"\n🤖 Agent Assignment:")
    for st in sub_tasks:
        best = registry.find_best(st.required_capabilities)
        if best:
            st.assigned_agent = best.id
            print(f"   {st.title}")
            print(f"     → {best.name} (score: {registry.find_by_capability(st.required_capabilities)[0][1]:.2f})")
        else:
            print(f"   {st.title} → ⚠️ No matching agent found!")

    # 6. Simulate execution
    print(f"\n⚡ Execution:")
    for i, st in enumerate(sub_tasks, 1):
        print(f"   Stage {i}/{len(sub_tasks)}: {st.title}")
        print(f"     Agent: {st.assigned_agent}")
        print(f"     Status: ✅ Completed")
        # In production: agent.execute(st) would be called here

    task.status = TaskStatus.COMPLETED
    print(f"\n✅ Project '{task.title}' completed successfully!")
    print(f"   Total stages: {len(sub_tasks)}")
    print(f"   Workflow: {workflow.name}")


def _register_agents(registry: AgentRegistry) -> None:
    """Register all available agents."""
    for agent_cls in [
        GeneralAgent,
        CodeGenAgent,
        CodeReviewAgent,
        DocWriterAgent,
        TestAgent,
    ]:
        temp = agent_cls()
        registry.register(temp.descriptor, agent_cls)

    print(f"\n📦 Registered agents: {len(registry.list_all())}")
    for desc in registry.list_all():
        print(f"   - {desc.name} [{', '.join(c.value for c in desc.capabilities)}]")


if __name__ == "__main__":
    asyncio.run(demo_software_lifecycle())
