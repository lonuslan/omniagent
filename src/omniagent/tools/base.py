"""
Tool System - The extensible tool framework for agents.

Inspired by Claude Code's tool system, this provides a universal interface
for tools that any agent can use. Tools are the "hands" of agents — they
allow agents to interact with the file system, run commands, search the web,
and more.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


class ToolParam(BaseModel):
    """Parameter definition for a tool."""
    name: str
    description: str
    type: str = "string"
    required: bool = True
    default: Any = None


class ToolDescriptor(BaseModel):
    """Metadata describing a tool."""
    name: str
    description: str
    parameters: list[ToolParam] = []
    category: str = "general"            # file, shell, web, agent, custom
    requires_sandbox: bool = False
    requires_approval: bool = False      # Whether user approval is needed


class BaseTool(ABC):
    """Base class for all tools."""

    descriptor: ToolDescriptor

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given parameters."""
        ...

    def validate(self, **kwargs: Any) -> bool:
        """Validate that required params are present and correctly typed."""
        required = {p.name for p in self.descriptor.parameters if p.required}
        return required.issubset(kwargs.keys())


# ── Tool Registry ────────────────────────────────────────────────────────────


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._by_category: dict[str, list[str]] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the system."""
        self._tools[tool.descriptor.name] = tool
        cat = tool.descriptor.category
        self._by_category.setdefault(cat, []).append(tool.descriptor.name)

    def unregister(self, name: str) -> None:
        """Remove a tool."""
        if name not in self._tools:
            return
        cat = self._tools[name].descriptor.category
        self._by_category[cat].remove(name)
        del self._tools[name]

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_descriptors(self) -> list[ToolDescriptor]:
        """Return descriptors for all registered tools (for LLM function calling)."""
        return [t.descriptor for t in self._tools.values()]

    def list_by_category(self, category: str) -> list[ToolDescriptor]:
        return [self._tools[n].descriptor for n in self._by_category.get(category, [])]


# ── Tool Decorator ───────────────────────────────────────────────────────────


def tool(
    name: str,
    description: str,
    parameters: list[ToolParam] | None = None,
    category: str = "general",
    requires_approval: bool = False,
) -> Callable:
    """
    Decorator to easily create tools from functions.
    """
    def decorator(func: Callable) -> type[BaseTool]:
        tool_desc = ToolDescriptor(
            name=name,
            description=description,
            parameters=parameters or [],
            category=category,
            requires_approval=requires_approval,
        )

        class FunctionTool(BaseTool):
            descriptor = tool_desc

            async def execute(self, **kwargs: Any) -> Any:
                result = func(**kwargs)
                if hasattr(result, "__await__"):
                    return await result
                return result

        FunctionTool.__name__ = f"{name}Tool"
        return FunctionTool

    return decorator
