"""
Unified type system for LLM interactions.

Normalizes differences between Anthropic, OpenAI, DeepSeek, and MiMo APIs
into a single consistent interface for OmniAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Literal


# ── Message Types ───────────────────────────────────────────────────────────


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Unified tool call representation."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from executing a tool."""
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """Unified chat message across all providers."""
    role: MessageRole
    content: str | list[ContentBlock] = ""
    tool_calls: list[ToolCall] | None = None
    tool_result: ToolResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentBlock:
    """Multi-modal content block (text or image)."""
    type: Literal["text", "image_url"]
    text: str | None = None
    image_url: str | None = None


# ── Completion Types ────────────────────────────────────────────────────────


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


@dataclass
class TokenUsage:
    """Unified token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Completion:
    """Unified completion response from any LLM."""
    id: str
    model: str
    content: str
    tool_calls: list[ToolCall] | None = None
    finish_reason: FinishReason = FinishReason.STOP
    usage: TokenUsage | None = None
    raw_response: Any = None


@dataclass
class StreamingChunk:
    """A single chunk in a streaming response."""
    content: str = ""
    tool_call_delta: ToolCall | None = None
    finish_reason: FinishReason | None = None
    usage: TokenUsage | None = None
    thinking: str = ""          # For models that expose reasoning


# ── Request Types ───────────────────────────────────────────────────────────


@dataclass
class LLMRequest:
    """Unified request to any LLM provider."""
    messages: list[Message]
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    tools: list[ToolDef] | None = None
    system: str | None = None       # Provider will convert to appropriate format
    stop_sequences: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDef:
    """Unified tool/function definition for LLM function calling."""
    name: str
    description: str
    parameters: dict[str, Any]   # JSON Schema object
    strict: bool = False


# ── Provider Info ───────────────────────────────────────────────────────────


@dataclass
class ModelInfo:
    """Information about a specific model."""
    id: str
    provider: str
    max_context_tokens: int
    max_output_tokens: int
    supports_vision: bool = False
    supports_tool_calling: bool = True
    supports_streaming: bool = True
    supports_thinking: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


# ── Provider Capabilities ───────────────────────────────────────────────────


@dataclass
class ProviderCapabilities:
    """What a provider supports."""
    streaming: bool = True
    tool_calling: bool = True
    vision: bool = False
    thinking: bool = False
    prompt_caching: bool = False
    max_context: int = 128_000
    concurrent_requests: int = 5
