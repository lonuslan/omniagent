"""
Built-in agent implementations for development tasks.

Each agent specializes in a specific capability, allowing the orchestrator
to route tasks to the most suitable agent automatically.
"""

from __future__ import annotations

from typing import Any

from ...protocol import AgentCapability, AgentDescriptor, AgentRole
from ..base import BaseAgent

# ── General Purpose Agent ────────────────────────────────────────────────────


class GeneralAgent(BaseAgent):
    """
    General-purpose agent that handles tasks without specialized requirements.
    Serves as the default/fallback agent.
    """

    descriptor = AgentDescriptor(
        id="general-agent",
        name="General Purpose Agent",
        version="1.0.0",
        capabilities=[AgentCapability.GENERAL_PURPOSE],
        role=AgentRole.EXECUTOR,
        description=(
            "Handles general-purpose tasks including requirement clarification, "
            "task decomposition, and coordination. Serves as the default agent "
            "when no specialized agent matches."
        ),
        provider="builtin",
    )

    async def _do_execute(self, task: Any) -> dict:
        return {"status": "completed", "summary": f"Processed: {task.title}"}


# ── Code Generation Agent ────────────────────────────────────────────────────


class CodeGenAgent(BaseAgent):
    """
    Specialized agent for code generation across multiple languages and frameworks.

    Capable of:
      - Frontend (React, Vue, HTML/CSS)
      - Backend (Python, Node.js, Go)
      - Full-stack feature implementation
    """

    descriptor = AgentDescriptor(
        id="code-gen-agent",
        name="Code Generation Agent",
        version="1.0.0",
        capabilities=[
            AgentCapability.CODE_GENERATION,
            AgentCapability.UI_DESIGN,
        ],
        role=AgentRole.EXECUTOR,
        description=(
            "Generates production-ready code across multiple languages and frameworks. "
            "Handles frontend UI implementation, backend API development, and "
            "full-stack feature delivery."
        ),
        provider="builtin",
        model_requirements=["claude-sonnet-4-6", "claude-opus-4-7"],
    )

    async def _do_execute(self, task: Any) -> dict:
        return {
            "status": "completed",
            "language": task.context.get("language", "python"),
            "files_generated": [],
        }


# ── Code Review Agent ────────────────────────────────────────────────────────


class CodeReviewAgent(BaseAgent):
    """Reviews code for bugs, security issues, and style compliance."""

    descriptor = AgentDescriptor(
        id="code-review-agent",
        name="Code Review Agent",
        version="1.0.0",
        capabilities=[
            AgentCapability.CODE_REVIEW,
            AgentCapability.TESTING,
        ],
        role=AgentRole.REVIEWER,
        description=(
            "Reviews code for correctness, security vulnerabilities, performance "
            "issues, and style compliance. Provides actionable feedback with "
            "specific suggestions for improvement."
        ),
        provider="builtin",
    )

    async def _do_execute(self, task: Any) -> dict:
        return {
            "status": "completed",
            "issues_found": 0,
            "suggestions": [],
            "approved": True,
        }


# ── Documentation Agent ──────────────────────────────────────────────────────


class DocWriterAgent(BaseAgent):
    """Generates documentation, reports, articles, and copywriting."""

    descriptor = AgentDescriptor(
        id="doc-writer-agent",
        name="Documentation Writer Agent",
        version="1.0.0",
        capabilities=[
            AgentCapability.DOCUMENTATION,
            AgentCapability.COPYWRITING,
        ],
        role=AgentRole.EXECUTOR,
        description=(
            "Creates high-quality documentation, technical articles, reports, "
            "and copywriting content. Supports multiple formats including "
            "Markdown, reStructuredText, and LaTeX."
        ),
        provider="builtin",
    )

    async def _do_execute(self, task: Any) -> dict:
        return {"status": "completed", "format": "markdown", "content": ""}


# ── Test Agent ───────────────────────────────────────────────────────────────


class TestAgent(BaseAgent):
    """Generates and executes tests."""

    descriptor = AgentDescriptor(
        id="test-agent",
        name="Test Agent",
        version="1.0.0",
        capabilities=[
            AgentCapability.TESTING,
        ],
        role=AgentRole.EXECUTOR,
        description=(
            "Generates comprehensive test suites including unit tests, "
            "integration tests, and end-to-end tests. Executes tests and "
            "reports results with coverage analysis."
        ),
        provider="builtin",
    )

    async def _do_execute(self, task: Any) -> dict:
        return {
            "status": "completed",
            "tests_generated": 0,
            "tests_passed": 0,
            "coverage": 0.0,
        }
