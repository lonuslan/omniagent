"""Tests for LLM Provider layer."""

import pytest

from omniagent.llm.provider import ProviderRegistry
from omniagent.llm.providers.claude import ClaudeProvider
from omniagent.llm.providers.deepseek import DeepSeekProvider
from omniagent.llm.providers.mimo import MiMoProvider
from omniagent.llm.providers.openai import OpenAIProvider
from omniagent.llm.types import (
    Completion,
    FinishReason,
    LLMRequest,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDef,
)


class TestUnifiedTypes:
    def test_message_creation(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

    def test_tool_call_creation(self):
        tc = ToolCall(id="call_1", name="read", arguments={"path": "/tmp"})
        assert tc.name == "read"
        assert tc.arguments["path"] == "/tmp"

    def test_completion_with_usage(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_request_with_tools(self):
        tool = ToolDef(
            name="read",
            description="Read a file",
            parameters={"type": "object", "properties": {}},
        )
        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="Read /tmp/test")],
            model="deepseek-v4-pro",
            tools=[tool],
        )
        assert len(request.tools) == 1
        assert request.tools[0].name == "read"


class TestProviderRegistry:
    @pytest.fixture
    def registry(self):
        reg = ProviderRegistry()
        reg.register("deepseek", DeepSeekProvider(api_key="test-ds-key"))
        reg.register("mimo", MiMoProvider(api_key="test-mimo-key"))
        reg.register("claude", ClaudeProvider(api_key="test-claude-key"))
        reg.register("openai", OpenAIProvider(api_key="test-openai-key"))
        return reg

    def test_list_providers(self, registry):
        names = registry.list_providers()
        assert "deepseek" in names
        assert "mimo" in names
        assert "claude" in names
        assert "openai" in names

    def test_get_provider(self, registry):
        provider = registry.get_provider("deepseek")
        assert isinstance(provider, DeepSeekProvider)

    def test_get_provider_for_model(self, registry):
        provider = registry.get_provider_for_model("deepseek-v4-pro")
        assert isinstance(provider, DeepSeekProvider)

        provider = registry.get_provider_for_model("claude-opus-4-7")
        assert isinstance(provider, ClaudeProvider)

    def test_list_models(self, registry):
        models = registry.list_models()
        assert "deepseek-v4-pro" in models.get("deepseek", [])
        assert "mimo-general-v2" in models.get("mimo", [])
        assert "claude-sonnet-4-6" in models.get("claude", [])
        assert "gpt-4o" in models.get("openai", [])


class TestDeepSeekProvider:
    def test_message_conversion_simple(self):
        provider = DeepSeekProvider(api_key="test-key")
        msg = Message(role=MessageRole.USER, content="Hello")
        result = provider._convert_message(msg)
        assert result["role"] == "user"
        assert result["content"] == "Hello"

    def test_message_conversion_with_tool_calls(self):
        provider = DeepSeekProvider(api_key="test-key")
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "/x"})],
        )
        result = provider._convert_message(msg)
        assert result["role"] == "assistant"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "read"

    def test_tool_def_conversion(self):
        provider = DeepSeekProvider(api_key="test-key")
        tool = ToolDef(
            name="search",
            description="Search the web",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        result = provider._convert_tool_def(tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "search"

    def test_finish_reason_mapping(self):
        provider = DeepSeekProvider(api_key="test-key")
        assert provider._map_finish_reason("stop") == FinishReason.STOP
        assert provider._map_finish_reason("tool_calls") == FinishReason.TOOL_CALLS
        assert provider._map_finish_reason("length") == FinishReason.LENGTH

    def test_model_info(self):
        provider = DeepSeekProvider(api_key="test-key")
        info = provider.get_model_info("deepseek-v4-pro")
        assert info is not None
        assert info.max_context_tokens == 1_000_000
        assert info.supports_thinking is True


class TestClaudeProvider:
    def test_message_conversion_text(self):
        provider = ClaudeProvider(api_key="test-key")
        msg = Message(role=MessageRole.USER, content="Hello")
        result = provider._convert_message(msg)
        assert result["role"] == "user"
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello"

    def test_tool_def_conversion(self):
        provider = ClaudeProvider(api_key="test-key")
        tool = ToolDef(
            name="bash",
            description="Run a command",
            parameters={"type": "object", "properties": {}},
        )
        result = provider._convert_tool_def(tool)
        # Anthropic format: no "type": "function" wrapper
        assert result["name"] == "bash"
        assert "input_schema" in result

    def test_model_info_opus(self):
        provider = ClaudeProvider(api_key="test-key")
        info = provider.get_model_info("claude-opus-4-7")
        assert info is not None
        assert info.max_context_tokens == 200_000
        assert info.cost_per_1m_input == 15.0
        assert info.cost_per_1m_output == 75.0
