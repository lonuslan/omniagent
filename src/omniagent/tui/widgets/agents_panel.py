"""
Agent list panel — shows registered agents with capabilities and status.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class AgentRow(Static):
    """A single agent row with status icon, name, and capabilities."""

    def __init__(self, agent_id: str, name: str, capabilities: list[str], status: str = "idle") -> None:
        self.agent_id = agent_id
        self.agent_name = name
        self.capabilities = capabilities
        self._status = status
        super().__init__(self._render())

    def _render(self) -> str:
        icons = {"idle": "○", "running": "◉", "done": "●", "error": "✕"}
        icon = icons.get(self._status, "○")
        caps = ", ".join(self.capabilities[:2])
        return f" {icon} [bold]{self.agent_name}[/]\n   {caps}"

    def set_status(self, status: str) -> None:
        self._status = status
        self.update(self._render())


class AgentsPanel(VerticalScroll):
    """Scrollable panel displaying all registered agents."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._agents: dict[str, AgentRow] = {}
        self._expanded = False

    def compose(self) -> ComposeResult:
        yield Static(" Loading...", id="agents-loading")

    def on_mount(self) -> None:
        self._register_builtins()

    def _register_builtins(self) -> None:
        loading = self.query_one("#agents-loading", Static)
        loading.remove()

        builtins = [
            ("orchestrator", "🎯 Orchestrator", ["Task Analysis", "Agent Routing"], "running"),
            ("general-agent", "🤖 General Agent", ["General Purpose"], "idle"),
            ("code-gen-agent", "💻 CodeGen Agent", ["Code Gen", "UI Design"], "idle"),
            ("code-review-agent", "🔍 Review Agent", ["Code Review", "Testing"], "idle"),
            ("doc-writer-agent", "📝 Doc Writer", ["Docs", "Copywriting"], "idle"),
            ("test-agent", "🧪 Test Agent", ["Unit Tests", "E2E Tests"], "idle"),
        ]

        for agent_id, name, caps, status in builtins:
            row = AgentRow(agent_id, name, caps, status)
            self._agents[agent_id] = row
            self.mount(row)

    def set_agent_status(self, agent_id: str, status: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].set_status(status)

    def toggle_expand(self) -> None:
        self._expanded = not self._expanded
