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
        super().__init__()
        self._refresh()

    def _refresh(self) -> None:
        icons = {"idle": "○", "running": "◉", "done": "●", "error": "✕"}
        icon = icons.get(self._status, "○")
        caps = ", ".join(self.capabilities[:2])
        self.update(f" {icon} [bold]{self.agent_name}[/]\n   {caps}")

    def set_status(self, status: str) -> None:
        self._status = status
        self._refresh()


class AgentsPanel(VerticalScroll):
    """Scrollable panel displaying all registered agents."""

    _AGENTS = [
        ("orchestrator", "🎯 Orchestrator", ["Task Analysis", "Agent Routing"]),
        ("general-agent", "🤖 General Agent", ["General Purpose"]),
        ("code-gen-agent", "💻 CodeGen Agent", ["Code Gen", "UI Design"]),
        ("code-review-agent", "🔍 Review Agent", ["Code Review", "Testing"]),
        ("doc-writer-agent", "📝 Doc Writer", ["Docs", "Copywriting"]),
        ("test-agent", "🧪 Test Agent", ["Unit Tests", "E2E Tests"]),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._agents: dict[str, AgentRow] = {}

    def compose(self) -> ComposeResult:
        for agent_id, name, caps in self._AGENTS:
            status = "running" if agent_id == "orchestrator" else "idle"
            row = AgentRow(agent_id, name, caps, status)
            self._agents[agent_id] = row
            yield row

    def set_agent_status(self, agent_id: str, status: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].set_status(status)

    def toggle_expand(self) -> None:
        self._expanded = not getattr(self, "_expanded", False)
