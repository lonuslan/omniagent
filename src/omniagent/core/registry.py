"""
Agent Registry & Discovery Service.

Manages the lifecycle of all agents: registration, discovery, capability matching,
and marketplace integration. This is the "yellow pages" of the OmniAgent ecosystem.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable

from ..protocol import AgentCapability, AgentDescriptor, AgentRole, IAgent

# ── Scoring ──────────────────────────────────────────────────────────────────


def capability_match_score(
    required: list[AgentCapability],
    offered: list[AgentCapability],
) -> float:
    """
    Calculate how well an agent's capabilities match the requirements.

    Returns a score 0.0-1.0. Exact matches score higher; extra capabilities
    are a bonus but not required.
    """
    if not required:
        return 0.5  # neutral score for no requirements

    offered_set = set(offered)
    required_set = set(required)

    matched = required_set & offered_set
    precision = len(matched) / len(required_set) if required_set else 0
    # Small bonus for additional capabilities beyond what's required
    extra = len(offered_set - required_set) * 0.02
    return precision + extra


# ── Registry ─────────────────────────────────────────────────────────────────


class AgentRegistry:
    """
    Central registry for all agents available in the system.

    Supports three agent sources:
      1. builtin  - shipped with OmniAgent
      2. custom   - user-defined agents
      3. marketplace - discovered from community/remote registries
    """

    def __init__(self) -> None:
        self._agents: dict[str, tuple[AgentDescriptor, type[IAgent] | None]] = {}
        self._by_capability: dict[AgentCapability, list[str]] = defaultdict(list)
        self._by_role: dict[AgentRole, list[str]] = defaultdict(list)
        self._marketplace_adapters: list[MarketplaceAdapter] = []
        self._on_register_hooks: list[Callable[[AgentDescriptor], None]] = []

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        descriptor: AgentDescriptor,
        agent_cls: type[IAgent] | None = None,
    ) -> None:
        """Register an agent with the system."""
        self._agents[descriptor.id] = (descriptor, agent_cls)

        for cap in descriptor.capabilities:
            self._by_capability[cap].append(descriptor.id)
        self._by_role[descriptor.role].append(descriptor.id)

        for hook in self._on_register_hooks:
            hook(descriptor)

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        if agent_id not in self._agents:
            return
        descriptor, _ = self._agents.pop(agent_id)
        for cap in descriptor.capabilities:
            self._by_capability[cap].remove(agent_id)
        self._by_role[descriptor.role].remove(agent_id)

    def on_register(self, hook: Callable[[AgentDescriptor], None]) -> None:
        """Subscribe to agent registration events."""
        self._on_register_hooks.append(hook)

    # ── Discovery ─────────────────────────────────────────────────────────

    def find_by_capability(
        self,
        capabilities: list[AgentCapability],
        role: AgentRole | None = None,
        min_score: float = 0.5,
    ) -> list[tuple[AgentDescriptor, float]]:
        """
        Find agents matching the required capabilities, ranked by match score.
        """
        results: list[tuple[AgentDescriptor, float]] = []
        for agent_id, (desc, _) in self._agents.items():
            if role is not None and desc.role != role:
                continue
            score = capability_match_score(capabilities, desc.capabilities)
            if score >= min_score:
                results.append((desc, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def find_best(
        self,
        capabilities: list[AgentCapability],
        role: AgentRole | None = None,
    ) -> AgentDescriptor | None:
        """Return the single best-matching agent, or None."""
        candidates = self.find_by_capability(capabilities, role)
        return candidates[0][0] if candidates else None

    def get(self, agent_id: str) -> AgentDescriptor | None:
        """Get an agent descriptor by ID."""
        entry = self._agents.get(agent_id)
        return entry[0] if entry else None

    def list_all(self) -> list[AgentDescriptor]:
        """List all registered agents."""
        return [desc for desc, _ in self._agents.values()]

    def list_by_source(self, source: str) -> list[AgentDescriptor]:
        """List agents by source (builtin, custom, marketplace)."""
        return [
            desc for desc, _ in self._agents.values() if desc.provider == source
        ]

    # ── Marketplace ───────────────────────────────────────────────────────

    def register_marketplace_adapter(self, adapter: MarketplaceAdapter) -> None:
        """Register a marketplace adapter for remote agent discovery."""
        self._marketplace_adapters.append(adapter)

    async def search_marketplace(
        self,
        query: str,
        capabilities: list[AgentCapability] | None = None,
    ) -> list[AgentDescriptor]:
        """Search all connected marketplaces for matching agents."""
        results: list[AgentDescriptor] = []
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(adapter.search(query, capabilities))
                for adapter in self._marketplace_adapters
            ]
        for task in tasks:
            results.extend(task.result())
        return results


# ── Marketplace Adapter ──────────────────────────────────────────────────────


class MarketplaceAdapter:
    """
    Adapter for connecting to external agent/skill marketplaces.

    Implementations could support:
      - GitHub agent repositories
      - Community skill registries
      - Enterprise agent catalogs
    """

    def __init__(self, name: str, base_url: str) -> None:
        self.name = name
        self.base_url = base_url

    async def search(
        self,
        query: str,
        capabilities: list[AgentCapability] | None = None,
    ) -> list[AgentDescriptor]:
        """Search this marketplace for agents."""
        # TODO: Implement HTTP search against marketplace API
        return []

    async def fetch(self, agent_id: str) -> AgentDescriptor | None:
        """Fetch a specific agent from this marketplace."""
        return None
