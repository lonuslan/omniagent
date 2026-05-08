"""
Task pipeline visualization — shows the 7-stage software development lifecycle.

Each stage shows: status icon, stage name, assigned agent, and progress.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineStage:
    index: int
    name: str
    emoji: str
    capabilities: list[str]
    assigned_agent: str = ""
    status: StageStatus = StageStatus.PENDING


class PipelinePanel(VerticalScroll):
    """Scrollable panel showing the 7-stage task pipeline."""

    STAGES = [
        ("需求确认", "📋", ["general_purpose"]),
        ("需求分析", "🔬", ["architecture_design", "documentation"]),
        ("原型设计", "🎨", ["prototype_design", "ui_design"]),
        ("前端开发", "💻", ["code_generation", "ui_design"]),
        ("后端开发", "⚙️", ["code_generation", "architecture_design"]),
        ("测试", "🧪", ["testing", "code_review"]),
        ("部署上线", "🚀", ["deployment"]),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stages: list[PipelineStage] = []
        self._stage_widgets: dict[int, Static] = {}
        self._start_time: float | None = None

    def compose(self) -> ComposeResult:
        yield Static(" Press 'r' to run demo", id="pipeline-placeholder")

    def on_mount(self) -> None:
        pass

    def init_stages(self) -> None:
        placeholder = self.query("#pipeline-placeholder")
        if placeholder:
            placeholder.remove()

        self._stages.clear()
        self._stage_widgets.clear()

        for i, (name, emoji, caps) in enumerate(self.STAGES):
            stage = PipelineStage(
                index=i,
                name=name,
                emoji=emoji,
                capabilities=caps,
            )
            self._stages.append(stage)
            widget = Static(self._render_stage(stage), id=f"stage-{i}")
            self._stage_widgets[i] = widget
            self.mount(widget)

    def set_stage(self, index: int, status: StageStatus, agent: str = "") -> None:
        if 0 <= index < len(self._stages):
            stage = self._stages[index]
            stage.status = status
            if agent:
                stage.assigned_agent = agent
            if index in self._stage_widgets:
                self._stage_widgets[index].update(self._render_stage(stage))

    def set_all_pending(self) -> None:
        for stage in self._stages:
            stage.status = StageStatus.PENDING
            stage.assigned_agent = ""
        for i, w in self._stage_widgets.items():
            w.update(self._render_stage(self._stages[i]))

    def _render_stage(self, stage: PipelineStage) -> str:
        icons = {
            StageStatus.PENDING: "⬜",
            StageStatus.RUNNING: "⚡",
            StageStatus.COMPLETED: "✅",
            StageStatus.FAILED: "❌",
        }
        icon = icons[stage.status]

        line = f" {icon} {stage.emoji} [bold]{stage.name}[/]"
        if stage.assigned_agent:
            line += f"\n    → {stage.assigned_agent}"
        return line

    def get_progress(self) -> tuple[int, int]:
        total = len(self._stages)
        done = sum(1 for s in self._stages if s.status == StageStatus.COMPLETED)
        return done, total
