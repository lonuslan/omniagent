"""Tests for Agent Registry."""

import pytest

from omniagent.core.registry import AgentRegistry, capability_match_score
from omniagent.protocol import AgentCapability, AgentDescriptor


class TestCapabilityMatchScore:
    def test_exact_match(self):
        assert capability_match_score(
            [AgentCapability.CODE_GENERATION],
            [AgentCapability.CODE_GENERATION],
        ) == 1.0

    def test_partial_match(self):
        score = capability_match_score(
            [AgentCapability.CODE_GENERATION, AgentCapability.TESTING],
            [AgentCapability.CODE_GENERATION],
        )
        assert 0.4 < score < 0.6

    def test_no_requirements(self):
        assert capability_match_score([], [AgentCapability.CODE_GENERATION]) == 0.5


class TestAgentRegistry:
    @pytest.fixture
    def registry(self):
        r = AgentRegistry()
        r.register(AgentDescriptor(
            id="test-1", name="Test Agent 1", version="1.0",
            capabilities=[AgentCapability.CODE_GENERATION],
        ))
        r.register(AgentDescriptor(
            id="test-2", name="Test Agent 2", version="1.0",
            capabilities=[AgentCapability.CODE_GENERATION, AgentCapability.TESTING],
        ))
        return r

    def test_find_by_capability(self, registry):
        results = registry.find_by_capability([AgentCapability.CODE_GENERATION])
        assert len(results) == 2
        # test-2 should rank higher (has more capabilities)
        assert results[0][0].id == "test-2"
        assert results[0][1] > results[1][1]

    def test_find_best(self, registry):
        best = registry.find_best([AgentCapability.TESTING])
        assert best is not None
        assert best.id == "test-2"

    def test_list_all(self, registry):
        assert len(registry.list_all()) == 2
