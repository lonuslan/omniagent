"""
LLM Bridge — connects GUI model configs to real LLM providers.

When a user configures a model in the GUI (api_key + base_url),
this bridge creates the corresponding provider instance and injects
it into the orchestrator's analyzer for real LLM-powered task analysis.
"""

from __future__ import annotations

from typing import Any

from ..llm.providers.claude import ClaudeProvider
from ..llm.providers.deepseek import DeepSeekProvider
from ..llm.providers.mimo import MiMoProvider
from ..llm.providers.openai import OpenAIProvider
from ..llm.provider import ProviderRegistry


class LLMBridge:
    """
    Manages the lifecycle of LLM provider instances based on GUI configs.

    - Creates real provider instances when API keys are configured
    - Registers them in a ProviderRegistry for the orchestrator to use
    - Provides model-aware task analysis via the configured provider
    """

    def __init__(self) -> None:
        self._registry = ProviderRegistry()
        self._active_provider: Any = None
        self._active_model: str = ""

    def configure(self, model_id: str, api_key: str, base_url: str = "") -> Any:
        """Create or update a provider instance from model config."""
        model = self._get_model_info(model_id)
        if not model:
            raise ValueError(f"Unknown model: {model_id}")

        provider_name = model["provider"]
        url = base_url or model["base_url"]

        provider = None
        if provider_name == "deepseek":
            provider = DeepSeekProvider(api_key=api_key, base_url=url)
        elif provider_name == "mimo":
            provider = MiMoProvider(api_key=api_key, base_url=url)
        elif provider_name == "anthropic":
            provider = ClaudeProvider(api_key=api_key, base_url=url)
        elif provider_name in ("openai", "qwen"):
            provider = OpenAIProvider(api_key=api_key, base_url=url)

        if provider:
            name = f"{provider_name}_{model_id}"
            self._registry.register(name, provider)
            self._active_provider = provider
            self._active_model = model_id
            return provider
        return None

    def get_provider(self, model_id: str | None = None) -> Any:
        """Get a provider instance for the given model."""
        if model_id:
            return self._registry.get_provider_for_model(model_id)
        return self._active_provider

    def get_registry(self) -> ProviderRegistry:
        return self._registry

    def is_configured(self) -> bool:
        return self._active_provider is not None

    @staticmethod
    def _get_model_info(model_id: str) -> dict | None:
        from ..gui.app import BUILTIN_MODELS
        for m in BUILTIN_MODELS:
            if m["id"] == model_id:
                return m
        return None

    def list_configured(self) -> list[dict]:
        """List all configured models with their providers."""
        result = []
        for name, provider in self._registry._providers.items():
            result.append({
                "name": name,
                "models": list(provider.model_info.keys()),
            })
        return result
