"""
OmniAgent TUI — Main application.

A terminal dashboard that visualizes multi-agent collaboration in real-time:
  - Left panel: Agent list with status indicators
  - Center panel: Task pipeline with 7-stage progress
  - Right panel: Event stream with auto-scroll
  - Footer: Status bar with keyboard shortcuts

Run: python -m omniagent.tui.demo
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Header, Static

from .widgets.agents_panel import AgentsPanel
from .widgets.event_log import EventLog
from .widgets.pipeline import PipelinePanel


class OmniAgentTUI(App):
    """
    OmniAgent Studio Terminal Dashboard.

    Displays the multi-agent orchestration process in real-time:
    agent discovery → task analysis → decomposition → assignment → execution.
    """

    CSS = """
    Header {
        background: $accent;
        color: $text;
        text-style: bold;
    }

    Horizontal {
        height: 1fr;
    }

    #left-panel {
        width: 28;
        border: solid $primary;
        background: $surface;
    }

    #center-panel {
        width: 1fr;
        border: solid $primary;
        background: $surface;
    }

    #right-panel {
        width: 40;
        border: solid $primary;
        background: $surface;
    }

    .panel-title {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    Footer {
        background: $accent;
        color: $text;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "run_demo", "Run Demo"),
        ("p", "pause_resume", "Pause/Resume"),
        ("a", "show_agents", "Agents"),
        ("t", "show_tasks", "Tasks"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._on_quit_callbacks: list[Callable] = []
        self.demo_runner: Callable | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Container(
                Static("🤖 Agents", classes="panel-title"),
                AgentsPanel(id="agents-panel"),
                id="left-panel",
            ),
            Container(
                Static("🔄 Task Pipeline", classes="panel-title"),
                PipelinePanel(id="pipeline-panel"),
                id="center-panel",
            ),
            Container(
                Static("📋 Event Stream", classes="panel-title"),
                EventLog(id="event-log"),
                id="right-panel",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted and ready."""
        self.title = "OmniAgent Studio"
        self.sub_title = "Multi-Agent Orchestration Dashboard"

        # Banner
        event_log = self.query_one("#event-log", EventLog)
        event_log.add_event("system", "OmniAgent Studio v0.2.0-dev starting...")
        event_log.add_event("system", "Loading agent registry...")
        event_log.add_event("system", "Ready. Press 'r' to run demo or 'q' to quit.")

    def action_run_demo(self) -> None:
        """Run the multi-agent orchestration demo."""
        if self.demo_runner:
            asyncio.create_task(self.demo_runner())

    def action_pause_resume(self) -> None:
        pass

    def action_show_agents(self) -> None:
        panel = self.query_one("#agents-panel", AgentsPanel)
        panel.toggle_expand()

    def action_show_tasks(self) -> None:
        pass

    def on_unmount(self) -> None:
        for cb in self._on_quit_callbacks:
            cb()


def run_app(demo_callback: Callable | None = None) -> None:
    """Entry point to launch the TUI."""
    app = OmniAgentTUI()
    app.demo_runner = demo_callback
    app.run()
