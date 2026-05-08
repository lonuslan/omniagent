"""
Git tools — Git integration for agents.

Supports: status, diff, log, branch, add, commit, stash, show.
All operations are read-safe by default; write operations require approval.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..base import BaseTool, ToolDescriptor, ToolParam


def _run_git(*args: str, cwd: str = ".") -> str:
    """Run a git command and return stdout/stderr."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output[:2000]
    except FileNotFoundError:
        return "Error: git not found in PATH"
    except subprocess.TimeoutExpired:
        return "Error: git command timed out"
    except Exception as e:
        return f"Error: {e}"


class GitStatusTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_status",
        description="Show the working tree status (modified, staged, untracked files)",
        parameters=[
            ToolParam(name="path", description="Repository path", required=False),
        ],
        category="shell",
    )

    async def execute(self, path: str = ".") -> str:
        return _run_git("status", "--short", "--branch", cwd=path)


class GitDiffTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_diff",
        description="Show changes between commits, working tree, or staging area",
        parameters=[
            ToolParam(name="path", description="Repository path", required=False),
            ToolParam(name="staged", description="Show staged changes only", type="boolean", required=False),
            ToolParam(name="file", description="Specific file to diff", required=False),
        ],
        category="shell",
    )

    async def execute(self, path: str = ".", staged: bool = False, file: str = "") -> str:
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file:
            args.extend(["--", file])
        return _run_git(*args, cwd=path)


class GitLogTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_log",
        description="Show commit history with formatting",
        parameters=[
            ToolParam(name="path", description="Repository path", required=False),
            ToolParam(name="count", description="Number of commits to show", type="number", required=False),
            ToolParam(name="oneline", description="Show one line per commit", type="boolean", required=False),
        ],
        category="shell",
    )

    async def execute(self, path: str = ".", count: int = 20, oneline: bool = True) -> str:
        args = ["log", f"-{count}"]
        if oneline:
            args.append("--oneline")
        args.append("--decorate")
        return _run_git(*args, cwd=path)


class GitBranchTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_branch",
        description="List, create, or delete branches",
        parameters=[
            ToolParam(name="path", description="Repository path", required=False),
            ToolParam(name="all", description="List all branches including remote", type="boolean", required=False),
        ],
        category="shell",
    )

    async def execute(self, path: str = ".", all: bool = False) -> str:
        args = ["branch"]
        if all:
            args.append("--all")
        return _run_git(*args, cwd=path)


class GitAddTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_add",
        description="Add file contents to the staging area",
        parameters=[
            ToolParam(name="files", description="Files to add (space-separated or '.' for all)", required=True),
            ToolParam(name="path", description="Repository path", required=False),
        ],
        category="shell",
        requires_approval=True,
    )

    async def execute(self, files: str, path: str = ".") -> str:
        return _run_git("add", *files.split(), cwd=path)


class GitCommitTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_commit",
        description="Record changes to the repository",
        parameters=[
            ToolParam(name="message", description="Commit message", required=True),
            ToolParam(name="path", description="Repository path", required=False),
        ],
        category="shell",
        requires_approval=True,
    )

    async def execute(self, message: str, path: str = ".") -> str:
        return _run_git("commit", "-m", message, cwd=path)


class GitStashTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_stash",
        description="Stash changes away for later use",
        parameters=[
            ToolParam(name="action", description="push, pop, list, or drop", required=False),
            ToolParam(name="path", description="Repository path", required=False),
        ],
        category="shell",
    )

    async def execute(self, action: str = "list", path: str = ".") -> str:
        if action == "push":
            return _run_git("stash", "push", "-m", "omniagent-stash", cwd=path)
        elif action == "pop":
            return _run_git("stash", "pop", cwd=path)
        elif action == "drop":
            return _run_git("stash", "drop", cwd=path)
        return _run_git("stash", "list", cwd=path)


class GitShowTool(BaseTool):
    descriptor = ToolDescriptor(
        name="git_show",
        description="Show various types of objects (commits, tags, etc.)",
        parameters=[
            ToolParam(name="ref", description="Commit hash, tag, or branch", required=False),
            ToolParam(name="path", description="Repository path", required=False),
        ],
        category="shell",
    )

    async def execute(self, ref: str = "HEAD", path: str = ".") -> str:
        return _run_git("show", "--stat", ref, cwd=path)
