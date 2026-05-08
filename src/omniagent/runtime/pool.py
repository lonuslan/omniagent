"""
LLMPool — Shared model connection pool for concurrent Agent execution.

Multiple agents can share a limited number of LLM connections,
with automatic queueing when all connections are busy.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ..llm.types import Completion, LLMRequest, StreamingChunk, TokenUsage


@dataclass
class PoolConfig:
    """Configuration for the LLM connection pool."""
    max_connections: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0
    request_timeout: float = 120.0
    cooldown_on_error: float = 5.0


@dataclass
class PoolStats:
    """Runtime statistics for the connection pool."""
    total_requests: int = 0
    active_connections: int = 0
    queued_requests: int = 0
    total_tokens: TokenUsage = field(default_factory=TokenUsage)
    errors: int = 0
    last_error: str = ""


class LLMPool:
    """
    Managed pool of LLM provider connections.

    Agents acquire connections from the pool, use them, then release them.
    If all connections are busy, requests are queued automatically.

    Usage:
        pool = LLMPool(provider, config)
        async with pool.acquire() as conn:
            completion = await conn.complete(request)
    """

    def __init__(self, config: PoolConfig | None = None) -> None:
        self.config = config or PoolConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_connections)
        self._stats = PoolStats()
        self._providers: dict[str, Any] = {}  # model_id → provider instance
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, model_id: str, provider: Any) -> None:
        """Register a provider for a specific model."""
        self._providers[model_id] = provider
        self._locks[model_id] = asyncio.Lock()

    async def complete(self, model_id: str, request: LLMRequest) -> Completion:
        """Execute a completion request through the pool."""
        provider = self._providers.get(model_id)
        if not provider:
            # Try to find by prefix match
            for mid, p in self._providers.items():
                if model_id.startswith(mid):
                    provider = p
                    break
        if not provider:
            raise ValueError(f"No provider registered for model: {model_id}")

        self._stats.total_requests += 1

        async with self._semaphore:
            self._stats.active_connections += 1
            try:
                result = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=self.config.request_timeout,
                )
                if result.usage:
                    self._stats.total_tokens.input_tokens += result.usage.input_tokens
                    self._stats.total_tokens.output_tokens += result.usage.output_tokens
                return result
            except Exception as e:
                self._stats.errors += 1
                self._stats.last_error = str(e)
                raise
            finally:
                self._stats.active_connections -= 1

    async def stream(
        self, model_id: str, request: LLMRequest
    ) -> AsyncIterator[StreamingChunk]:
        """Stream a completion through the pool."""
        provider = self._providers.get(model_id)
        if not provider:
            raise ValueError(f"No provider registered for model: {model_id}")

        async with self._semaphore:
            async for chunk in provider.stream(request):
                yield chunk

    def get_stats(self) -> PoolStats:
        """Get current pool statistics."""
        return self._stats

    def reset_stats(self) -> None:
        self._stats = PoolStats()

    async def close(self) -> None:
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()
        self._providers.clear()
