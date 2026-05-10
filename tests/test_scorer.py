"""Tests for AgentScorer."""

import json
from pathlib import Path

import pytest

from omniagent.core.scorer import AgentScorer, AgentStatsEntry, ScoreBreakdown
from omniagent.protocol import AgentCapability, AgentDescriptor


def _make_agent(agent_id: str, caps: list[AgentCapability], name: str = "", desc: str = "") -> AgentDescriptor:
    return AgentDescriptor(
        id=agent_id,
        name=name or agent_id,
        version="1.0",
        capabilities=caps,
        description=desc or f"{agent_id} agent",
    )


class TestAgentStatsEntry:
    def test_success_rate_no_data(self):
        entry = AgentStatsEntry(agent_id="a1")
        assert entry.success_rate == 0.5

    def test_success_rate_with_data(self):
        entry = AgentStatsEntry(agent_id="a1", total_tasks=10, successful=7)
        assert entry.success_rate == 0.7

    def test_round_trip(self):
        entry = AgentStatsEntry(agent_id="a1", total_tasks=5, successful=3, failed=2)
        d = entry.to_dict()
        restored = AgentStatsEntry.from_dict(d)
        assert restored.agent_id == "a1"
        assert restored.total_tasks == 5
        assert restored.successful == 3


class TestScoreBreakdown:
    def test_to_dict(self):
        sb = ScoreBreakdown(
            agent_id="a1", agent_name="Agent 1",
            capability_score=0.8, llm_score=0.7, reputation_score=0.6,
            composite_score=0.72, llm_reasoning="good fit",
        )
        d = sb.to_dict()
        assert d["agent_id"] == "a1"
        assert d["composite"] == 0.72
        assert d["reasoning"] == "good fit"


class TestAgentScorer:
    @pytest.fixture
    def scorer(self, tmp_path):
        return AgentScorer(stats_path=tmp_path / "stats.json")

    def test_capability_score_exact(self, scorer):
        caps = [AgentCapability.CODE_GENERATION]
        assert scorer.capability_score(caps, caps) == 1.0

    def test_capability_score_partial(self, scorer):
        required = [AgentCapability.CODE_GENERATION, AgentCapability.TESTING]
        offered = [AgentCapability.CODE_GENERATION]
        score = scorer.capability_score(required, offered)
        assert 0.4 < score < 0.6

    def test_capability_score_empty(self, scorer):
        assert scorer.capability_score([], [AgentCapability.CODE_GENERATION]) == 0.5

    def test_llm_score_no_bridge(self, scorer):
        agent = _make_agent("a1", [AgentCapability.CODE_GENERATION])
        score, reason = scorer.llm_score("write code", agent)
        assert score == 0.5
        assert "No LLM" in reason

    def test_reputation_score_no_data(self, scorer):
        assert scorer.reputation_score("nonexistent") == 0.5

    def test_record_success(self, scorer):
        scorer.record_success("a1", 100.0)
        scorer.record_success("a1", 200.0)
        scorer.record_failure("a1", 50.0)
        stats = scorer.get_stats("a1")
        assert stats.total_tasks == 3
        assert stats.successful == 2
        assert stats.failed == 1
        assert stats.success_rate == pytest.approx(2/3)

    def test_reputation_with_history(self, scorer):
        for _ in range(8):
            scorer.record_success("a1")
        for _ in range(2):
            scorer.record_failure("a1")
        rep = scorer.reputation_score("a1")
        assert rep == pytest.approx(0.8)

    def test_marketplace_rating(self, scorer):
        scorer.update_marketplace_rating("a1", 4.0)
        rep = scorer.reputation_score("a1")
        assert rep == pytest.approx(0.8)  # 4.0/5.0

    def test_composite_score(self, scorer):
        agent = _make_agent("a1", [AgentCapability.CODE_GENERATION], "CodeGen")
        breakdown = scorer.composite_score(
            "write code", agent, [AgentCapability.CODE_GENERATION], use_llm=False,
        )
        assert breakdown.agent_id == "a1"
        assert breakdown.capability_score == 1.0
        assert breakdown.llm_score == 0.5  # no LLM
        assert breakdown.reputation_score == 0.5  # no data
        # composite = 1.0*0.4 + 0.5*0.35 + 0.5*0.25 = 0.4 + 0.175 + 0.125 = 0.7
        assert breakdown.composite_score == pytest.approx(0.7)

    def test_rank_agents(self, scorer):
        agents = [
            _make_agent("a1", [AgentCapability.CODE_GENERATION], "CodeGen"),
            _make_agent("a2", [AgentCapability.DOCUMENTATION], "DocWriter"),
            _make_agent("a3", [AgentCapability.GENERAL_PURPOSE], "General"),
        ]
        rankings = scorer.rank_agents(
            "write code", agents, [AgentCapability.CODE_GENERATION], use_llm=False,
        )
        assert len(rankings) == 3
        assert rankings[0].agent_id == "a1"  # best match
        assert rankings[0].composite_score >= rankings[1].composite_score

    def test_stats_persistence(self, tmp_path):
        stats_path = tmp_path / "stats.json"
        s1 = AgentScorer(stats_path=stats_path)
        s1.record_success("a1")
        s1.record_success("a1")

        # New instance should load from file
        s2 = AgentScorer(stats_path=stats_path)
        assert s2.get_stats("a1").total_tasks == 2
        assert s2.get_stats("a1").successful == 2

    def test_marketplace_rating_clamped(self, scorer):
        scorer.update_marketplace_rating("a1", 10.0)  # over max
        assert scorer.get_stats("a1").marketplace_rating == 5.0
        scorer.update_marketplace_rating("a1", -1.0)  # under min
        assert scorer.get_stats("a1").marketplace_rating == 0.0
