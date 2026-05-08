"""
DeepSeek Provider — OpenAI-compatible API with reasoning extensions.

Supports:
  - deepseek-v4-pro  (1M context, premium reasoning)
  - deepseek-v4-flash (1M context, fast/cheap)
  - deepseek-reasoner (dedicated reasoning model)
  - Fill-in-the-Middle (FIM) for code editing
  - Thinking mode streaming (reasoning_content in chunks)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..provider import (
    AuthenticationError,
    ContextOverflowError,
    LLMProvider,
    ProviderError,
    RateLimitError,
)
from ..types import (
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
)


class DeepSeekProvider(LLMProvider):
    """Provider for DeepSeek API (OpenAI-compatible with extensions)."""

    capabilities = ProviderCapabilities(
        streaming=True,
        tool_calling=True,
        thinking=True,
        prompt_caching=True,
        max_context=1_000_000,
        concurrent_requests=10,
    )

    model_info = {
        "deepseek-v4-pro": ModelInfo(
            id="deepseek-v4-pro",
            provider="deepseek",
            max_context_tokens=1_000_000,
            max_output_tokens=32_000,
            supports_tool_calling=True,
            supports_streaming=True,
            supports_thinking=True,
            cost_per_1m_input=0.435,
            cost_per_1m_output=0.87,
        ),
        "deepseek-v4-flash": ModelInfo(
            id="deepseek-v4-flash",
            provider="deepseek",
            max_context_tokens=1_000_000,
            max_output_tokens=32_000,
            supports_tool_calling=True,
            supports_streaming=True,
            cost_per_1m_input=0.14,
            cost_per_1m_output=0.28,
        ),
    }

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        timeout: float = 120.0,
    ) -> None:
        super().__init__(api_key, base_url or self.DEFAULT_BASE_URL, timeout)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    # ── Message Conversion ───────────────────────────────────────────────

    def _convert_message(self, message: Message) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self._map_role(message.role)}

        if message.content:
            if isinstance(message.content, str):
                msg["content"] = message.content
            else:
                # Multi-modal content blocks
                msg["content"] = [
                    {"type": b.type, b.type: b.text or b.image_url}
                    for b in message.content
                ]

        if message.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in message.tool_calls
            ]

        if message.tool_result:
            msg["role"] = "tool"
            msg["tool_call_id"] = message.tool_result.tool_call_id
            msg["content"] = message.tool_result.content

        return msg

    def _map_role(self, role: MessageRole) -> str:
        mapping = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.TOOL: "tool",
        }
        return mapping[role]

    # ── Tool Conversion ──────────────────────────────────────────────────

    def _convert_tool_def(self, tool: ToolDef) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    # ── Request ──────────────────────────────────────────────────────────

    async def _make_request(self, request: LLMRequest) -> dict[str, Any]:
        client = await self._get_client()

        body: dict[str, Any] = {
            "model": request.model or "deepseek-v4-pro",
            "messages": [self._convert_message(m) for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.system:
            body["messages"].insert(0, {"role": "system", "content": request.system})

        if request.tools:
            body["tools"] = [
                self._convert_tool_def(t) for t in request.tools
            ]
            body["tool_choice"] = "auto"

        if request.stop_sequences:
            body["stop"] = request.stop_sequences

        stream = getattr(request, "stream", False)
        body["stream"] = stream

        try:
            response = await client.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            raise ProviderError("Request timed out", provider="deepseek")
        except httpx.ConnectError as e:
            raise ProviderError(f"Connection failed: {e}", provider="deepseek")

        if not stream:
            return self._handle_response(response)
        return {"_stream": response, "body": body}

    async def _stream_raw(
        self, request: LLMRequest
    ) -> AsyncIterator[dict[str, Any]]:
        client = await self._get_client()

        body: dict[str, Any] = {
            "model": request.model or "deepseek-v4-pro",
            "messages": [self._convert_message(m) for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.system:
            body["messages"].insert(0, {"role": "system", "content": request.system})

        if request.tools:
            body["tools"] = [self._convert_tool_def(t) for t in request.tools]
            body["tool_choice"] = "auto"

        try:
            async with client.stream("POST", "/chat/completions", json=body) as resp:
                self._handle_response(resp)
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        yield json.loads(data)
        except httpx.TimeoutException:
            raise ProviderError("Stream timed out", provider="deepseek")

    # ── Response Handling ────────────────────────────────────────────────

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise AuthenticationError("Invalid DeepSeek API key", 401, "deepseek")
        elif response.status_code == 429:
            raise RateLimitError("DeepSeek rate limit exceeded", 429, "deepseek")
        elif response.status_code == 400:
            body = response.json()
            msg = body.get("error", {}).get("message", str(body))
            if "context" in msg.lower() or "token" in msg.lower():
                raise ContextOverflowError(msg, 400, "deepseek")
            raise ProviderError(msg, 400, "deepseek")
        else:
            raise ProviderError(
                f"DeepSeek API error ({response.status_code}): {response.text[:500]}",
                response.status_code,
                "deepseek",
            )

    def _parse_response(self, raw: dict[str, Any]) -> Completion:
        choice = raw["choices"][0]
        message = choice.get("message", {})

        # Tool calls
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                )
                for tc in message["tool_calls"]
            ]

        # Usage
        usage = None
        if "usage" in raw:
            u = raw["usage"]
            usage = TokenUsage(
                input_tokens=u.get("prompt_tokens", 0),
                output_tokens=u.get("completion_tokens", 0),
                cache_read_tokens=u.get("prompt_cache_hit_tokens", 0),
                reasoning_tokens=u.get("reasoning_tokens", 0),
            )

        return Completion(
            id=raw["id"],
            model=raw["model"],
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=self._map_finish_reason(choice.get("finish_reason", "stop")),
            usage=usage,
            raw_response=raw,
        )

    def _parse_streaming_chunk(self, raw: dict[str, Any]) -> StreamingChunk:
        choice = raw.get("choices", [{}])[0]
        delta = choice.get("delta", {})

        tool_delta = None
        if delta.get("tool_calls"):
            tc = delta["tool_calls"][0]
            tool_delta = ToolCall(
                id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", ""),
            )

        usage = None
        if "usage" in raw:
            u = raw["usage"]
            usage = TokenUsage(
                input_tokens=u.get("prompt_tokens", 0),
                output_tokens=u.get("completion_tokens", 0),
                cache_read_tokens=u.get("prompt_cache_hit_tokens", 0),
            )

        finish = (
            self._map_finish_reason(choice.get("finish_reason"))
            if choice.get("finish_reason")
            else None
        )

        return StreamingChunk(
            content=delta.get("content", ""),
            tool_call_delta=tool_delta,
            finish_reason=finish,
            usage=usage,
            thinking=delta.get("reasoning_content", ""),
        )

    def _map_finish_reason(self, reason: str | None) -> FinishReason:
        mapping = {
            "stop": FinishReason.STOP,
            "length": FinishReason.LENGTH,
            "tool_calls": FinishReason.TOOL_CALLS,
        }
        return mapping.get(reason or "", FinishReason.STOP)

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
