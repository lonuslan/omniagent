"""
CLI entry point for OmniAgent Studio.

Provides commands for:
  - omniagent gui    : Launch the Windows desktop application (default)
  - omniagent tui    : Launch the TUI terminal dashboard
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

# ── GUI ──────────────────────────────────────────────────────────────────────


@app.command()
def gui() -> None:
    """Launch the OmniAgent Studio Windows desktop application."""
    from .gui.app import launch_gui
    launch_gui()


# ── TUI ──────────────────────────────────────────────────────────────────────


@app.command()
def tui(
    dry_run: bool = typer.Option(True, help="Run with simulated agents (no API keys needed)"),
) -> None:
    """Launch the OmniAgent TUI dashboard with multi-agent orchestration visualization."""
    from .tui.demo import main as tui_main
    if dry_run:
        typer.echo("Launching OmniAgent Studio TUI (dry-run mode)...")
    tui_main()


# ── Start ────────────────────────────────────────────────────────────────────


@app.command()
def start(
    gui_mode: bool = typer.Option(True, help="Launch GUI desktop mode"),
    port: int = typer.Option(7860, help="Port for the web UI"),
) -> None:
    """Launch OmniAgent Studio (GUI desktop by default)."""
    if gui_mode:
        from .gui.app import launch_gui
        launch_gui()
    else:
        typer.echo(f"Starting OmniAgent Studio on http://localhost:{port}")
        typer.echo("(Web UI: planned for Electron + React)")


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
