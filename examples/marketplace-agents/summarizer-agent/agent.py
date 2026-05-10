"""
Example marketplace agent: Text Summarizer.

A simple agent that summarizes text content. This demonstrates the
agent package format for the OmniAgent marketplace.
"""

from omniagent.agents.base import BaseAgent
from omniagent.protocol import AgentDescriptor, AgentCapability, AgentRole


class SummarizerAgent(BaseAgent):
    """Summarizes long documents into concise overviews."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptor = AgentDescriptor(
            id="summarizer-agent",
            name="Text Summarizer Agent",
            version="1.0.0",
            capabilities=[AgentCapability.DOCUMENTATION, AgentCapability.GENERAL_PURPOSE],
            role=AgentRole.EXECUTOR,
            description="Summarizes long documents into concise overviews",
            provider="marketplace",
        )

    async def _do_execute(self, task):
        text = task.description
        # Simple extractive summary: first 2 sentences
        sentences = text.replace("\n", " ").split(". ")
        summary = ". ".join(sentences[:2])
        if len(sentences) > 2:
            summary += "..."
        return summary
