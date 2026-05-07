"""
CLI entry point for OmniAgent Studio.

Provides commands for:
  - omniagent start  : Launch the desktop UI
  - omniagent run    : Run a task from the command line
  - omniagent agent  : Manage agents (list, install, create)
  - omniagent market : Search the agent marketplace
"""

from __future__ import annotations

import asyncio
import uuid

import typer

from .protocol import Task

app = typer.Typer(
    name="omniagent",
    help="OmniAgent Studio - Autonomous Multi-Agent Collaborative Platform",
)

# ── Start ────────────────────────────────────────────────────────────────────


@app.command()
def start(
    port: int = typer.Option(7860, help="Port for the web UI"),
    headless: bool = typer.Option(False, help="Run without UI"),
) -> None:
    """Launch the OmniAgent Studio desktop application."""
    if headless:
        typer.echo("Starting OmniAgent in headless mode...")
        asyncio.run(_run_headless())
    else:
        typer.echo(f"Starting OmniAgent Studio on http://localhost:{port}")
        typer.echo("(UI module: planned for Electron + React)")


# ── Run ─────────────────────────────────────────────────────────────────────


@app.command()
def run(
    task: str = typer.Argument(..., help="Task description to execute"),
    workflow: str = typer.Option("auto", help="Workflow template to use"),
) -> None:
    """Execute a task using the multi-agent orchestrator."""
    typer.echo(f"Task: {task}")
    typer.echo(f"Workflow: {workflow}")
    typer.echo("Orchestrator analyzing task...")

    t = Task(
        id=str(uuid.uuid4()),
        title=task[:80],
        description=task,
        workflow_template=workflow if workflow != "auto" else None,
    )

    asyncio.run(_execute_task(t))


# ── Agent Management ────────────────────────────────────────────────────────

agent_app = typer.Typer(help="Manage agents")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def list_agents(
    source: str = typer.Option("all", help="Filter by source: builtin, custom, marketplace, all"),
) -> None:
    """List all registered agents."""
    typer.echo("Registered agents:")
    typer.echo("  - general-agent (General Purpose)")
    typer.echo("  - code-gen-agent (Code Generation)")
    typer.echo("  - code-review-agent (Code Review)")
    typer.echo("  - doc-writer-agent (Documentation)")
    typer.echo("  - test-agent (Testing)")


@agent_app.command("create")
def create_agent(
    name: str = typer.Option(..., prompt="Agent name"),
    capability: str = typer.Option(..., prompt="Primary capability"),
) -> None:
    """Create a custom agent."""
    typer.echo(f"Creating custom agent: {name} with capability: {capability}")
    typer.echo("(Custom agent builder UI planned)")


# ── Marketplace ──────────────────────────────────────────────────────────────

market_app = typer.Typer(help="Search the agent marketplace")
app.add_typer(market_app, name="market")


@market_app.command("search")
def market_search(
    query: str = typer.Argument(..., help="Search query for agents/skills"),
) -> None:
    """Search the agent marketplace for available agents and skills."""
    typer.echo(f"Searching marketplace for: {query}")
    typer.echo("(Marketplace integration planned)")


# ── Internals ────────────────────────────────────────────────────────────────


async def _execute_task(task: Task) -> None:
    """Internal: execute a task through the orchestrator."""
    from .core.orchestrator import Orchestrator
    from .core.registry import AgentRegistry

    registry = AgentRegistry()
    _register_builtins(registry)

    orch = Orchestrator(registry)
    task = await orch.submit(task)
    events = await orch.execute(task)

    for event in events:
        typer.echo(f"  [{event.agent_id}] {event.event_type}: {event.data}")


async def _run_headless() -> None:
    """Run in headless mode for API/CLI usage."""
    typer.echo("OmniAgent headless mode active. Waiting for tasks...")


def _register_builtins(registry: AgentRegistry) -> None:
    """Register all built-in agents with the registry."""
    from .agents.builtin.generators import (
        CodeGenAgent,
        CodeReviewAgent,
        DocWriterAgent,
        GeneralAgent,
        TestAgent,
    )

    for agent_cls in [
        GeneralAgent,
        CodeGenAgent,
        CodeReviewAgent,
        DocWriterAgent,
        TestAgent,
    ]:
        temp = agent_cls()
        registry.register(temp.descriptor, agent_cls)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
