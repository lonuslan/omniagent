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

market_app = typer.Typer(help="Search, install, and manage marketplace agents")
app.add_typer(market_app, name="market")


@market_app.command("search")
def market_search(
    query: str = typer.Argument(..., help="Search query for agents"),
    capabilities: str = typer.Option("", help="Comma-separated capability filters"),
) -> None:
    """Search the agent marketplace for available agents."""
    from .marketplace.registry import GitHubRegistry

    cap_list = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else None
    registry = GitHubRegistry()
    results = registry.search(query, cap_list)
    if not results:
        typer.echo("No agents found.")
        return
    typer.echo(f"Found {len(results)} agent(s):\n")
    for e in results:
        rating = f" ({e.rating:.1f}/5)" if e.rating_count > 0 else ""
        typer.echo(f"  {e.id} v{e.version}{rating}")
        typer.echo(f"    {e.description}")
        typer.echo(f"    capabilities: {', '.join(e.capabilities)}")
        typer.echo()


@market_app.command("list")
def market_list() -> None:
    """List all installed marketplace agents."""
    from .marketplace.installer import list_installed

    packages = list_installed()
    if not packages:
        typer.echo("No marketplace agents installed.")
        return
    typer.echo(f"Installed agents ({len(packages)}):\n")
    for pkg in packages:
        typer.echo(f"  {pkg.id} v{pkg.version} — {pkg.name}")
        typer.echo(f"    {pkg.description}")
        typer.echo()


@market_app.command("info")
def market_info(
    agent_id: str = typer.Argument(..., help="Agent ID to inspect"),
) -> None:
    """Show detailed information about a marketplace agent."""
    from .marketplace.installer import is_installed
    from .marketplace.registry import GitHubRegistry

    registry = GitHubRegistry()
    entry = registry.get(agent_id)
    if not entry:
        typer.echo(f"Agent not found: {agent_id}")
        raise typer.Exit(code=1)

    typer.echo(f"Agent: {entry.name} (v{entry.version})")
    typer.echo(f"ID: {entry.id}")
    typer.echo(f"Author: {entry.author}")
    typer.echo(f"Description: {entry.description}")
    typer.echo(f"Capabilities: {', '.join(entry.capabilities)}")
    typer.echo(f"Tags: {', '.join(entry.tags) if entry.tags else 'none'}")
    if entry.rating_count > 0:
        typer.echo(f"Rating: {entry.rating:.1f}/5 ({entry.rating_count} reviews)")
    if entry.git_url:
        typer.echo(f"Git URL: {entry.git_url}")
    installed = "Yes" if is_installed(agent_id) else "No"
    typer.echo(f"Installed: {installed}")


@market_app.command("install")
def market_install(
    agent_id: str = typer.Argument(..., help="Agent ID or git URL to install"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing installation"),
) -> None:
    """Install an agent from the marketplace or a git URL."""
    from .marketplace.installer import install_from_git, is_installed
    from .marketplace.registry import GitHubRegistry

    # Check if it's a git URL
    if agent_id.startswith("http") or agent_id.startswith("git@"):
        typer.echo(f"Installing from git: {agent_id}")
        try:
            pkg = install_from_git(agent_id, force=force)
            typer.echo(f"Installed {pkg.id} v{pkg.version}")
        except Exception as e:
            typer.echo(f"Install failed: {e}")
            raise typer.Exit(code=1)
        return

    # Look up in registry
    registry = GitHubRegistry()
    entry = registry.get(agent_id)
    if not entry:
        typer.echo(f"Agent not found in marketplace: {agent_id}")
        raise typer.Exit(code=1)
    if not entry.git_url:
        typer.echo(f"Agent has no git_url: {agent_id}")
        raise typer.Exit(code=1)
    if is_installed(agent_id) and not force:
        typer.echo(f"Already installed: {agent_id}. Use --force to reinstall.")
        return

    typer.echo(f"Installing {entry.name} from {entry.git_url}...")
    try:
        pkg = install_from_git(entry.git_url, agent_id=agent_id, force=force)
        typer.echo(f"Installed {pkg.id} v{pkg.version}")
    except Exception as e:
        typer.echo(f"Install failed: {e}")
        raise typer.Exit(code=1)


@market_app.command("uninstall")
def market_uninstall(
    agent_id: str = typer.Argument(..., help="Agent ID to uninstall"),
) -> None:
    """Uninstall a marketplace agent."""
    from .marketplace.installer import uninstall

    if uninstall(agent_id):
        typer.echo(f"Uninstalled: {agent_id}")
    else:
        typer.echo(f"Agent not installed: {agent_id}")
        raise typer.Exit(code=1)


@market_app.command("rate")
def market_rate(
    agent_id: str = typer.Argument(..., help="Agent ID to rate"),
    score: int = typer.Argument(..., help="Rating score (1-5)"),
    comment: str = typer.Option("", "--comment", "-c", help="Review comment"),
) -> None:
    """Rate a marketplace agent (1-5)."""
    import time

    from .marketplace.models import Review
    from .marketplace.registry import LocalRegistry

    if score < 1 or score > 5:
        typer.echo("Score must be between 1 and 5.")
        raise typer.Exit(code=1)

    local = LocalRegistry()
    review = Review(
        agent_id=agent_id,
        user="cli-user",
        score=score,
        comment=comment,
        timestamp=time.time(),
    )
    local.add_review(review)
    avg, count = local.get_rating(agent_id)
    typer.echo(f"Rated {agent_id}: {score}/5")
    typer.echo(f"Average: {avg:.1f}/5 ({count} reviews)")


# ── Internals ────────────────────────────────────────────────────────────────


async def _execute_task(task: Task) -> None:
    """Internal: execute a task through the orchestrator."""
    from .core.orchestrator import Orchestrator
    from .core.registry import AgentRegistry

    registry = AgentRegistry()
    _register_builtins(registry)

    orch = Orchestrator(registry)
    task, analysis = await orch.submit(task)
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
