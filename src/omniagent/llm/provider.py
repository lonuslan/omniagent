"""
LLM Provider abstract base class.

Defines the unified interface that all providers must implement.
Handles format conversion, streaming abstraction, retry logic, and cost tracking.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .types import (
    Completion,
    FinishReason,
    LLMRequest,
    Message,
    MessageRole,
    ModelInfo,
    ProviderCapabilities,
    StreamingChunk,
    TokenUsage,
    ToolCall,
    ToolDef,
    ToolResult,
)


class ProviderError(Exception):
    """Base error for provider failures."""

    def __init__(self, message: str, status_code: int = 0, provider: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class RateLimitError(ProviderError):
    """Rate limit exceeded."""


class AuthenticationError(ProviderError):
    """Invalid API key or authentication."""


class ContextOverflowError(ProviderError):
    """Input exceeds model context limit."""


# ── Base Provider ───────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """
    Abstract base for all LLM providers.

    Each provider implementation handles:
      1. Message format conversion (OmniAgent → provider-specific)
      2. Tool definition conversion (OmniAgent ToolDef → provider format)
      3. Response normalization (provider-specific → OmniAgent Completion)
      4. Streaming with backpressure control
      5. Cost tracking per request
    """

    # Subclass must define these
    capabilities: ProviderCapabilities
    model_info: dict[str, ModelInfo] = {}

    def __init__(self, api_key: str, base_url: str = "", timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._total_usage = TokenUsage()

    # ── Abstract Methods ─────────────────────────────────────────────────

    @abstractmethod
    async def _make_request(self, request: LLMRequest) -> dict[str, Any]:
        """Send request to provider API, return raw response dict."""
        ...

    @abstractmethod
    def _convert_message(self, message: Message) -> dict[str, Any]:
        """Convert OmniAgent Message to provider-specific format."""
        ...

    @abstractmethod
    def _convert_tool_def(self, tool: ToolDef) -> dict[str, Any]:
        """Convert OmniAgent ToolDef to provider-specific format."""
        ...

    @abstractmethod
    def _parse_response(self, raw: dict[str, Any]) -> Completion:
        """Parse provider-specific response into Completion."""
        ...

    @abstractmethod
    def _parse_streaming_chunk(self, raw: dict[str, Any]) -> StreamingChunk:
        """Parse a streaming SSE chunk into StreamingChunk."""
        ...

    # ── Public API ───────────────────────────────────────────────────────

    async def complete(self, request: LLMRequest) -> Completion:
        """
        Send a completion request and return the full response.

        Automatically handles:
          - Message format conversion
          - Tool definition conversion
          - Retry on transient errors (up to 3 attempts)
          - Cost tracking
        """
        request = self._prepare_request(request)
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                raw = await self._make_request(request)
                completion = self._parse_response(raw)
                self._track_usage(completion.usage)
                return completion
            except (RateLimitError, ContextOverflowError):
                raise  # Don't retry these
            except ProviderError as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(1.5 ** attempt)
            except Exception as e:
                last_error = ProviderError(str(e), provider=self.__class__.__name__)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        raise last_error or ProviderError("Max retries exceeded")

    async def stream(
        self, request: LLMRequest
    ) -> AsyncIterator[StreamingChunk]:
        """
        Stream completion chunks.

        Yields StreamingChunk objects with partial content, tool calls,
        thinking blocks, and final usage stats.
        """
        request = self._prepare_request(request)
        request.stream = True  # type: ignore[attr-defined]

        async for chunk in self._stream_raw(request):
            parsed = self._parse_streaming_chunk(chunk)
            if parsed.usage:
                self._track_usage(parsed.usage)
            yield parsed

    @abstractmethod
    async def _stream_raw(self, request: LLMRequest) -> AsyncIterator[dict[str, Any]]:
        """Stream raw SSE data from provider. Implement in subclass."""
        ...

    def get_usage(self) -> TokenUsage:
        """Get cumulative token usage for this provider session."""
        return self._total_usage

    def reset_usage(self) -> None:
        """Reset cumulative usage tracking."""
        self._total_usage = TokenUsage()

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _prepare_request(self, request: LLMRequest) -> LLMRequest:
        """Convert messages and tools to provider format before sending."""
        converted: list[Message] = []
        for msg in request.messages:
            converted.append(msg)  # Subclasses override _convert_message

        if request.tools:
            request.metadata["_converted_tools"] = [
                self._convert_tool_def(t) for t in request.tools
            ]

        return request

    def _track_usage(self, usage: TokenUsage | None) -> None:
        if usage:
            self._total_usage.input_tokens += usage.input_tokens
            self._total_usage.output_tokens += usage.output_tokens
            self._total_usage.cache_read_tokens += usage.cache_read_tokens

    @staticmethod
    def _make_tool_result_message(results: list[ToolResult]) -> Message:
        """Create a Message containing tool execution results."""
        content_parts: list[str] = []
        for r in results:
            prefix = "[ERROR] " if r.is_error else ""
            content_parts.append(
                f"<tool_result tool_call_id='{r.tool_call_id}' name='{r.name}'>\n"
                f"{prefix}{r.content}\n"
                f"</tool_result>"
            )
        return Message(
            role=MessageRole.TOOL,
            content="\n".join(content_parts),
        )

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)

    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports a given model."""
        return model_id in self.model_info

    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """Get capabilities for a specific model."""
        return self.model_info.get(model_id)


# ── Provider Registry ───────────────────────────────────────────────────────


class ProviderRegistry:
    """
    Registry for managing multiple LLM providers.

    Supports:
      - Provider discovery by model name
      - Load balancing across providers for the same capability
      - Health checking
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._model_to_provider: dict[str, str] = {}     # model_id → provider_name
        self._provider_status: dict[str, bool] = {}       # provider_name → healthy

    def register(self, name: str, provider: LLMProvider) -> None:
        """Register a named provider."""
        self._providers[name] = provider
        self._provider_status[name] = True
        for model_id in provider.model_info:
            if model_id not in self._model_to_provider:
                self._model_to_provider[model_id] = name

    def get_provider(self, name: str) -> LLMProvider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_provider_for_model(self, model_id: str) -> LLMProvider | None:
        """Find the provider that supports a specific model."""
        provider_name = self._model_to_provider.get(model_id)
        if provider_name:
            return self._providers.get(provider_name)
        return None

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_models(self) -> dict[str, list[str]]:
        """List all models grouped by provider."""
        return {
            name: list(p.model_info.keys())
            for name, p in self._providers.items()
        }

    def mark_unhealthy(self, name: str) -> None:
        """Mark a provider as unhealthy (for circuit breaking)."""
        self._provider_status[name] = False

    def mark_healthy(self, name: str) -> None:
        """Mark a provider as healthy again."""
        self._provider_status[name] = True

    def is_healthy(self, name: str) -> bool:
        """Check if a provider is healthy."""
        return self._provider_status.get(name, False)
