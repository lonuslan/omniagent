"""
Claude Provider — Anthropic API.

Anthropic uses a different message format than OpenAI (no "assistant" role
for tool calls, different tool definition format, XML-style tool use blocks).
This provider handles all format conversions transparently.
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
    ContentBlock,
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


class ClaudeProvider(LLMProvider):
    """Provider for Anthropic Claude API."""

    capabilities = ProviderCapabilities(
        streaming=True,
        tool_calling=True,
        vision=True,
        thinking=True,
        prompt_caching=True,
        max_context=200_000,
        concurrent_requests=5,
    )

    model_info = {
        "claude-sonnet-4-6": ModelInfo(
            id="claude-sonnet-4-6",
            provider="anthropic",
            max_context_tokens=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_tool_calling=True,
            supports_streaming=True,
            supports_thinking=True,
            cost_per_1m_input=3.0,
            cost_per_1m_output=15.0,
        ),
        "claude-opus-4-7": ModelInfo(
            id="claude-opus-4-7",
            provider="anthropic",
            max_context_tokens=200_000,
            max_output_tokens=32_000,
            supports_vision=True,
            supports_tool_calling=True,
            supports_streaming=True,
            supports_thinking=True,
            cost_per_1m_input=15.0,
            cost_per_1m_output=75.0,
        ),
        "claude-haiku-4-5": ModelInfo(
            id="claude-haiku-4-5",
            provider="anthropic",
            max_context_tokens=200_000,
            max_output_tokens=8_192,
            supports_vision=True,
            supports_tool_calling=True,
            supports_streaming=True,
            cost_per_1m_input=1.0,
            cost_per_1m_output=5.0,
        ),
    }

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    ANTHROPIC_VERSION = "2023-06-01"

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
                    "x-api-key": self.api_key,
                    "anthropic-version": self.ANTHROPIC_VERSION,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    # ── Message Conversion ───────────────────────────────────────────────

    def _convert_message(self, message: Message) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self._map_role(message.role)}

        # Build Anthropic content blocks
        content: list[dict[str, Any]] = []

        if isinstance(message.content, str) and message.content:
            content.append({"type": "text", "text": message.content})
        elif isinstance(message.content, list):
            for block in message.content:
                if block.type == "text" and block.text:
                    content.append({"type": "text", "text": block.text})
                elif block.type == "image_url" and block.image_url:
                    content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": block.image_url,
                            },
                        }
                    )

        if message.tool_calls:
            # Anthropic: assistant content blocks with tool_use type
            for tc in message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )

        if message.tool_result:
            content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_result.tool_call_id,
                    "content": message.tool_result.content,
                    "is_error": message.tool_result.is_error,
                }
            )

        msg["content"] = content or [{"type": "text", "text": ""}]
        return msg

    def _map_role(self, role: MessageRole) -> str:
        mapping = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.TOOL: "user",  # Anthropic merges tool results into user
        }
        return mapping[role]

    # ── Tool Conversion ──────────────────────────────────────────────────

    def _convert_tool_def(self, tool: ToolDef) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }

    # ── Request ──────────────────────────────────────────────────────────

    async def _make_request(self, request: LLMRequest) -> dict[str, Any]:
        client = await self._get_client()

        # Separate system message from others (Anthropic convention)
        system_content = request.system or ""
        messages_data: list[dict[str, Any]] = []
        for m in request.messages:
            converted = self._convert_message(m)
            if converted["role"] == "system":
                system_content += ("\n" + converted["content"][0].get("text", ""))
            else:
                messages_data.append(converted)

        body: dict[str, Any] = {
            "model": request.model or "claude-sonnet-4-6",
            "messages": messages_data,
            "max_tokens": request.max_tokens,
        }

        if system_content.strip():
            body["system"] = system_content.strip()

        if request.temperature > 0:
            body["temperature"] = request.temperature

        if request.tools:
            body["tools"] = [self._convert_tool_def(t) for t in request.tools]

        if request.stop_sequences:
            body["stop_sequences"] = request.stop_sequences

        stream = getattr(request, "stream", False)
        body["stream"] = stream

        try:
            response = await client.post("/messages", json=body)
        except httpx.TimeoutException:
            raise ProviderError("Request timed out", provider="anthropic")
        except httpx.ConnectError as e:
            raise ProviderError(f"Connection failed: {e}", provider="anthropic")

        if not stream:
            return self._handle_response(response)
        return {"_stream": response, "body": body}

    async def _stream_raw(
        self, request: LLMRequest
    ) -> AsyncIterator[dict[str, Any]]:
        client = await self._get_client()

        system_content = request.system or ""
        messages_data: list[dict[str, Any]] = []
        for m in request.messages:
            converted = self._convert_message(m)
            if converted["role"] == "system":
                system_content += ("\n" + converted["content"][0].get("text", ""))
            else:
                messages_data.append(converted)

        body: dict[str, Any] = {
            "model": request.model or "claude-sonnet-4-6",
            "messages": messages_data,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if system_content.strip():
            body["system"] = system_content.strip()

        if request.temperature > 0:
            body["temperature"] = request.temperature

        if request.tools:
            body["tools"] = [self._convert_tool_def(t) for t in request.tools]

        try:
            async with client.stream("POST", "/messages", json=body) as resp:
                self._handle_response(resp)
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        yield data
                        if data.get("type") == "message_stop":
                            break
        except httpx.TimeoutException:
            raise ProviderError("Stream timed out", provider="anthropic")

    # ── Response Handling ────────────────────────────────────────────────

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise AuthenticationError("Invalid Anthropic API key", 401, "anthropic")
        elif response.status_code == 429:
            raise RateLimitError("Anthropic rate limit exceeded", 429, "anthropic")
        elif response.status_code == 400:
            body = response.json()
            msg = body.get("error", {}).get("message", str(body))
            if "context" in msg.lower() or "token" in msg.lower():
                raise ContextOverflowError(msg, 400, "anthropic")
            raise ProviderError(msg, 400, "anthropic")
        else:
            raise ProviderError(
                f"Anthropic API error ({response.status_code}): {response.text[:500]}",
                response.status_code,
                "anthropic",
            )

    def _parse_response(self, raw: dict[str, Any]) -> Completion:
        content_blocks = raw.get("content", [])

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            if block["type"] == "text":
                text_parts.append(block.get("text", ""))
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block.get("input", {}),
                    )
                )

        usage = None
        if "usage" in raw:
            u = raw["usage"]
            usage = TokenUsage(
                input_tokens=u.get("input_tokens", 0),
                output_tokens=u.get("output_tokens", 0),
                cache_read_tokens=u.get("cache_read_input_tokens", 0),
                cache_write_tokens=u.get("cache_creation_input_tokens", 0),
            )

        finish = FinishReason.STOP
        if raw.get("stop_reason") == "tool_use":
            finish = FinishReason.TOOL_CALLS
        elif raw.get("stop_reason") == "max_tokens":
            finish = FinishReason.LENGTH

        return Completion(
            id=raw["id"],
            model=raw["model"],
            content="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=finish,
            usage=usage,
            raw_response=raw,
        )

    def _parse_streaming_chunk(self, raw: dict[str, Any]) -> StreamingChunk:
        event_type = raw.get("type", "")

        if event_type == "content_block_delta":
            delta = raw.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                return StreamingChunk(
                    content=delta.get("text", ""),
                )
            elif delta_type == "input_json_delta":
                return StreamingChunk(
                    content=delta.get("partial_json", ""),
                )
            elif delta_type == "thinking_delta":
                return StreamingChunk(
                    thinking=delta.get("thinking", ""),
                )

        elif event_type == "content_block_start":
            block = raw.get("content_block", {})
            if block.get("type") == "tool_use":
                return StreamingChunk(
                    tool_call_delta=ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments={},
                    )
                )

        elif event_type == "message_delta":
            usage_raw = raw.get("usage", {})
            stop_reason = raw.get("delta", {}).get("stop_reason")
            finish = None
            if stop_reason == "tool_use":
                finish = FinishReason.TOOL_CALLS
            elif stop_reason == "end_turn":
                finish = FinishReason.STOP

            return StreamingChunk(
                finish_reason=finish,
                usage=TokenUsage(
                    output_tokens=usage_raw.get("output_tokens", 0),
                ),
            )

        return StreamingChunk()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
