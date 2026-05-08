"""
Event log widget — real-time scrolling event stream.

Displays all agent events (started, progress, completed, error) with
timestamps and color-coded severity levels.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class EventLog(VerticalScroll):
    """Auto-scrolling event log with color-coded entries."""

    MAX_LINES = 100

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="event-content")

    def add_event(self, source: str, message: str, level: str = "info") -> None:
        """Add an event to the log. Level: info, success, warning, error, thinking."""
        now = time.strftime("%H:%M:%S")

        icons = {
            "system": "⚙️",
            "orchestrator": "🎯",
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "thinking": "🧠",
        }

        # Map source to icon
        if source.startswith("code-gen"):
            icon = "💻"
        elif source.startswith("code-review"):
            icon = "🔍"
        elif source.startswith("doc-writer"):
            icon = "📝"
        elif source.startswith("test"):
            icon = "🧪"
        elif source.startswith("general"):
            icon = "🤖"
        else:
            icon = icons.get(level, "•")

        colors = {
            "info": "dim white",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "thinking": "italic cyan",
            "system": "bold blue",
        }
        color = colors.get(level, "white")

        line = f"[{color}]{icon} [{now}] {message}[/]"

        self._lines.append(line)
        if len(self._lines) > self.MAX_LINES:
            self._lines = self._lines[-self.MAX_LINES:]

        content = self.query_one("#event-content", Static)
        content.update("\n".join(self._lines))

        # Auto-scroll to bottom
        self.scroll_end(animate=False)

    def clear(self) -> None:
        self._lines.clear()
        content = self.query_one("#event-content", Static)
        content.update("")
