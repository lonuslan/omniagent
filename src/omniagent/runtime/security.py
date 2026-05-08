"""
Permission system & execution modes for Agent operations.

Three execution modes (inspired by Claude Code / DeepSeek-TUI):
  - PLAN:   Read-only exploration, no files modified
  - AGENT:  Interactive, each tool call requires user approval
  - AUTO:   Full automation, no approval prompts

Permission levels per tool category:
  - read:    Always allowed (read files, glob, grep)
  - write:   Requires approval in AGENT mode (write, edit)
  - shell:   Requires approval in AGENT mode (bash commands)
  - delete:  Always requires approval (delete files)
  - network: Requires approval in AGENT mode (web fetch)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ExecutionMode(str, Enum):
    PLAN = "plan"      # Read-only, no modifications
    AGENT = "agent"    # Interactive, confirm each action
    AUTO = "auto"      # Full automation


class PermissionLevel(str, Enum):
    """Permission level for tool categories."""
    READ = "read"         # Always allowed
    WRITE = "write"       # Approval in AGENT mode
    SHELL = "shell"       # Approval in AGENT mode
    DELETE = "delete"     # Always requires approval
    NETWORK = "network"   # Approval in AGENT mode
    AGENT_CTRL = "agent_control"  # Spawning sub-agents, always requires approval


# Tool category → permission level mapping
TOOL_PERMISSIONS: dict[str, PermissionLevel] = {
    "read": PermissionLevel.READ,
    "write": PermissionLevel.WRITE,
    "edit": PermissionLevel.WRITE,
    "glob": PermissionLevel.READ,
    "grep": PermissionLevel.READ,
    "bash": PermissionLevel.SHELL,
    "shell": PermissionLevel.SHELL,
    "delete": PermissionLevel.DELETE,
    "web_fetch": PermissionLevel.NETWORK,
    "web_search": PermissionLevel.NETWORK,
    "spawn_agent": PermissionLevel.AGENT_CTRL,
    "handoff": PermissionLevel.AGENT_CTRL,
}


@dataclass
class PermissionRequest:
    """A request for permission to execute a tool."""
    tool_name: str
    tool_args: dict[str, Any]
    permission_level: PermissionLevel
    agent_id: str
    reason: str = ""

    def describe(self) -> str:
        args_str = " ".join(f"{k}={v}" for k, v in self.tool_args.items())
        return f"{self.tool_name}({args_str}) by {self.agent_id}"


class PermissionHandler:
    """
    Decides whether a tool call is allowed based on execution mode
    and permission level.

    In PLAN mode:  only READ operations allowed
    In AGENT mode: READ auto-approved, others need user confirmation
    In AUTO mode:  everything auto-approved (except AGENT_CTRL)
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.AGENT) -> None:
        self.mode = mode
        self._pending: list[PermissionRequest] = []
        self._approved: set[str] = set()  # tool_name → pre-approved
        self._denied: set[str] = set()

    def check(self, tool_name: str, tool_args: dict[str, Any], agent_id: str) -> PermissionRequest | None:
        """
        Check if a tool call needs approval. Returns None if auto-approved,
        or a PermissionRequest if approval is needed.
        """
        level = TOOL_PERMISSIONS.get(tool_name, PermissionLevel.SHELL)

        if self.mode == ExecutionMode.PLAN:
            if level != PermissionLevel.READ:
                return PermissionRequest(tool_name, tool_args, level, agent_id,
                                         reason="PLAN mode: only read operations allowed")
            return None

        if self.mode == ExecutionMode.AUTO:
            if level == PermissionLevel.AGENT_CTRL:
                return PermissionRequest(tool_name, tool_args, level, agent_id,
                                         reason="Agent control always requires approval")
            return None

        # AGENT mode: READ auto-approved, others need confirmation
        if level == PermissionLevel.READ:
            return None

        return PermissionRequest(tool_name, tool_args, level, agent_id)

    def approve(self, request: PermissionRequest) -> None:
        self._approved.add(request.tool_name)

    def deny(self, request: PermissionRequest) -> None:
        self._denied.add(request.tool_name)

    def reset(self) -> None:
        self._pending.clear()

    def set_mode(self, mode: ExecutionMode) -> None:
        self.mode = mode
        self._approved.clear()


@dataclass
class WorkspacePolicy:
    """
    Defines the workspace boundaries for Agent execution.

    Agents can only access files within allowed directories,
    preventing unintended modifications outside the project scope.
    """

    allowed_paths: list[str] = field(default_factory=lambda: ["."])
    denied_paths: list[str] = field(default_factory=list)
    max_file_size_mb: int = 50
    max_shell_timeout_sec: int = 300
    allow_network: bool = True
    allow_subprocess: bool = True

    def is_path_allowed(self, path: str) -> bool:
        """Check if a file path is within allowed directories."""
        import os
        abs_path = os.path.abspath(path)
        for denied in self.denied_paths:
            if abs_path.startswith(os.path.abspath(denied)):
                return False
        for allowed in self.allowed_paths:
            if abs_path.startswith(os.path.abspath(allowed)):
                return True
        return False
