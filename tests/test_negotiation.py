"""Tests for NegotiationProtocol."""

import pytest

from omniagent.core.negotiation import (
    DebateProposal,
    DebateRound,
    NegotiationProtocol,
)


class TestDebateProposal:
    def test_basic_creation(self):
        p = DebateProposal(
            agent_id="a1", agent_name="Agent A",
            position="Use React", reasoning="Better ecosystem",
        )
        assert p.agent_id == "a1"
        assert p.evidence == []


class TestNegotiationResult:
    def test_single_proposal_wins_by_default(self):
        protocol = NegotiationProtocol()
        p = DebateProposal(
            agent_id="a1", agent_name="Agent A",
            position="Use React", reasoning="Better ecosystem",
        )
        result = protocol.negotiate("Frontend framework", [p])
        assert result.arbitration.winner_id == "a1"
        assert result.arbitration.confidence == 1.0
        assert result.rounds == []

    def test_no_proposals_default(self):
        protocol = NegotiationProtocol()
        result = protocol.negotiate("Empty topic", [])
        assert result.arbitration.winner_id == "default"
        assert result.arbitration.confidence == 1.0


class TestNegotiationProtocolNoLLM:
    """Tests when no LLM bridge is configured."""

    @pytest.fixture
    def protocol(self):
        return NegotiationProtocol(llm_bridge=None)

    def test_rebuttal_fallback(self, protocol):
        a = DebateProposal("a1", "Agent A", "Use React", "Large ecosystem")
        b = DebateProposal("a2", "Agent B", "Use Vue", "Easier learning curve")
        rebuttal = protocol._generate_rebuttal("Frontend", a, b, "")
        assert "disagrees" in rebuttal.lower() or "Agent A" in rebuttal

    def test_arbitration_fallback_first_wins(self, protocol):
        a = DebateProposal("a1", "Agent A", "Use React", "Large ecosystem")
        b = DebateProposal("a2", "Agent B", "Use Vue", "Easier learning curve")
        rounds = [
            DebateRound(proposal=a, rebuttal="A critiques B"),
            DebateRound(proposal=b, rebuttal="B critiques A"),
        ]
        result = protocol._arbitrate("Frontend", rounds, "")
        assert result.winner_id == "a1"
        assert result.confidence == 0.5
        assert "No LLM" in result.reasoning

    def test_full_negotiate_no_llm(self, protocol):
        a = DebateProposal("a1", "Agent A", "Use React", "Large ecosystem")
        b = DebateProposal("a2", "Agent B", "Use Vue", "Easier learning curve")
        result = protocol.negotiate("Frontend", [a, b], "Building a web app")
        assert result.arbitration.winner_id == "a1"
        assert len(result.rounds) == 2
        assert result.rounds[0].proposal.agent_id == "a1"
        assert result.rounds[1].proposal.agent_id == "a2"

    def test_more_than_two_proposals_uses_first_two(self, protocol):
        proposals = [
            DebateProposal(f"a{i}", f"Agent {i}", f"Approach {i}", f"Reason {i}")
            for i in range(5)
        ]
        result = protocol.negotiate("Topic", proposals)
        assert len(result.rounds) == 2
        assert result.rounds[0].proposal.agent_id == "a0"
        assert result.rounds[1].proposal.agent_id == "a1"
        assert len(result.all_proposals) == 5
