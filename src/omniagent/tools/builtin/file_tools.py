"""
File system tools — Read, Write, Edit, Glob, Grep.

Mirrors Claude Code's file manipulation toolset, giving agents the ability
to work with project files.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from ..base import BaseTool, ToolDescriptor, ToolParam

# ── Read Tool ────────────────────────────────────────────────────────────────


class ReadTool(BaseTool):
    descriptor = ToolDescriptor(
        name="read",
        description="Read a file from the filesystem. Supports text, images, and PDFs.",
        parameters=[
            ToolParam(name="file_path", description="Absolute path to the file", required=True),
            ToolParam(name="offset", description="Line offset to start reading from", type="number", required=False),
            ToolParam(name="limit", description="Max lines to read", type="number", required=False),
        ],
        category="file",
    )

    async def execute(self, file_path: str, offset: int = 0, limit: int | None = None) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading file: {e}"


# ── Write Tool ───────────────────────────────────────────────────────────────


class WriteTool(BaseTool):
    descriptor = ToolDescriptor(
        name="write",
        description="Write content to a file, overwriting if it exists.",
        parameters=[
            ToolParam(name="file_path", description="Absolute path to write to", required=True),
            ToolParam(name="content", description="Content to write", required=True),
        ],
        category="file",
    )

    async def execute(self, file_path: str, content: str) -> str:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"File written: {file_path}"


# ── Edit Tool ────────────────────────────────────────────────────────────────


class EditTool(BaseTool):
    descriptor = ToolDescriptor(
        name="edit",
        description="Perform exact string replacement in a file.",
        parameters=[
            ToolParam(name="file_path", description="Absolute path to the file", required=True),
            ToolParam(name="old_string", description="Text to replace", required=True),
            ToolParam(name="new_string", description="Replacement text", required=True),
        ],
        category="file",
    )

    async def execute(self, file_path: str, old_string: str, new_string: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        content = path.read_text(encoding="utf-8")
        if old_string not in content:
            return f"Error: old_string not found in {file_path}"
        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"Edit applied to: {file_path}"


# ── Glob Tool ────────────────────────────────────────────────────────────────


class GlobTool(BaseTool):
    descriptor = ToolDescriptor(
        name="glob",
        description="Find files matching a glob pattern.",
        parameters=[
            ToolParam(name="pattern", description="Glob pattern (e.g., **/*.py)", required=True),
            ToolParam(name="path", description="Directory to search in", required=False),
        ],
        category="file",
    )

    async def execute(self, pattern: str, path: str = ".") -> str:
        base = Path(path)
        matches = sorted(base.glob(pattern))
        return "\n".join(str(m) for m in matches[:200])


# ── Grep Tool ────────────────────────────────────────────────────────────────


class GrepTool(BaseTool):
    descriptor = ToolDescriptor(
        name="grep",
        description="Search file contents using regex patterns.",
        parameters=[
            ToolParam(name="pattern", description="Regex pattern to search for", required=True),
            ToolParam(name="path", description="Directory or file to search", required=False),
            ToolParam(name="glob", description="File filter glob", required=False),
        ],
        category="file",
    )

    async def execute(self, pattern: str, path: str = ".", glob: str | None = None) -> str:
        results: list[str] = []
        base = Path(path)
        files = base.rglob("*") if base.is_dir() else [base]

        compiled = re.compile(pattern)
        for f in files:
            if not f.is_file():
                continue
            if glob and not fnmatch.fnmatch(f.name, glob):
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
                    if compiled.search(line):
                        results.append(f"{f}:{i}: {line.strip()}")
            except Exception:
                pass

        return "\n".join(results[:200])
