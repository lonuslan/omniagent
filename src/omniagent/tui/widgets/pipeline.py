"""
Task pipeline visualization — 7-stage software development lifecycle.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class StageStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelinePanel(VerticalScroll):
    """Scrollable panel showing the 7-stage task pipeline."""

    STAGES = [
        ("需求确认", "📋"),
        ("需求分析", "🔬"),
        ("原型设计", "🎨"),
        ("前端开发", "💻"),
        ("后端开发", "⚙️"),
        ("测试", "🧪"),
        ("部署上线", "🚀"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stage_statuses: list[str] = [StageStatus.PENDING] * 7
        self._stage_agents: list[str] = [""] * 7
        self._initialized = False

    def compose(self) -> ComposeResult:
        for i in range(len(self.STAGES)):
            yield Static(self._render_stage(i), id=f"stage-{i}")

    def on_mount(self) -> None:
        self._initialized = True

    def init_stages(self) -> None:
        """Reset all stages to pending."""
        self._stage_statuses = [StageStatus.PENDING] * 7
        self._stage_agents = [""] * 7
        for i in range(7):
            w = self.query_one(f"#stage-{i}", Static)
            w.update(self._render_stage(i))

    def set_stage(self, index: int, status: str, agent: str = "") -> None:
        """Update a stage's status and assigned agent."""
        if 0 <= index < 7:
            self._stage_statuses[index] = status
            if agent:
                self._stage_agents[index] = agent
            w = self.query_one(f"#stage-{index}", Static)
            w.update(self._render_stage(index))

    def get_progress(self) -> tuple[int, int]:
        done = sum(1 for s in self._stage_statuses if s == StageStatus.COMPLETED)
        return done, 7

    def _render_stage(self, index: int) -> str:
        name, emoji = self.STAGES[index]
        status = self._stage_statuses[index]

        icons = {
            StageStatus.PENDING: "⬜",
            StageStatus.RUNNING: "⚡",
            StageStatus.COMPLETED: "✅",
            StageStatus.FAILED: "❌",
        }
        icon = icons.get(status, "⬜")

        line = f" {icon} {emoji} [bold]{name}[/]"
        agent = self._stage_agents[index]
        if agent:
            line += f"\n    → {agent}"
        return line
